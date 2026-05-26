"""Shared RTSP readers + fused canvas for group pipeline preview and recording."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any, Optional

import cv2

from app.services import pipeline_preview
from app.services.ai.background_model import BackgroundModelRegistry
from app.services.ai.boat_tracker import TrackedBoat
from app.core.config import settings
from app.services.ai.frame_fusion import (
    DEFAULT_FUSED_MAX_HEIGHT,
    DEFAULT_FUSED_MAX_WIDTH,
    FrameFuser,
    FusionMember,
    build_fusion_config_from_group,
)
from app.services.ai.frame_synchronizer import FrameSynchronizer
from app.services.ai.multi_frame_reader import (
    CameraSource,
    LatestFrameBuffer,
    MultiFrameReaderThread,
    TimedFrame,
)
from app.services.ai.seam_anchor_verifier import SeamAnchorVerifier
from app.utils.ai.fused_track_overlay import draw_fused_track_overlay
from app.utils.ai.pipeline_utils import put_queue_drop_oldest

_log = logging.getLogger(__name__)

TrackProvider = Callable[[], list[TrackedBoat]]


class GroupFrameHub:
    """
    One RTSP reader per camera, fuse into layout canvas for dashboard preview and video.
    Hybrid mode also fans raw camera frames into per-camera AI queues.
    """

    def __init__(
        self,
        *,
        group: Any,
        enabled_members: list[Any],
        runtime_cfg: dict[str, Any],
        stop_event: threading.Event,
        video_queue: queue.Queue | None = None,
        yolo_frame_queue: queue.Queue | None = None,
        distribute_per_camera: bool = False,
        bg_registry: BackgroundModelRegistry | None = None,
        seam_anchor_verifier: SeamAnchorVerifier | None = None,
        on_fused_media_sample: Optional[Callable[[Any, list[Any]], None]] = None,
    ) -> None:
        self._stop_event = stop_event
        self._video_queue = video_queue
        self._yolo_frame_queue = yolo_frame_queue
        self._distribute_per_camera = distribute_per_camera
        self._bg_registry = bg_registry
        self._seam_anchor_verifier = seam_anchor_verifier
        self._on_fused_media_sample = on_fused_media_sample
        self._track_providers: list[TrackProvider] = []
        self._frame_buffer = LatestFrameBuffer()
        self._per_camera_queues: dict[int, queue.Queue] = {}
        if distribute_per_camera:
            for member in enabled_members:
                camera_id = int(member.camera_id)
                self._per_camera_queues[camera_id] = queue.Queue(maxsize=3)

        fusion_config = build_fusion_config_from_group(
            group,
            max_width=runtime_cfg['fused_frame_max_width'],
            max_height=runtime_cfg['fused_frame_max_height'],
        )
        self._fuser = FrameFuser(fusion_config)
        self._overlay_members_record: dict[int, FusionMember] = {
            int(m.camera_id): m for m in fusion_config.members if m.enabled
        }
        preview_max_w = min(
            int(runtime_cfg['fused_frame_max_width']),
            int(getattr(settings, 'PREVIEW_MAX_WIDTH', DEFAULT_FUSED_MAX_WIDTH)),
        )
        preview_max_h = min(
            int(runtime_cfg['fused_frame_max_height']),
            int(getattr(settings, 'PREVIEW_MAX_HEIGHT', DEFAULT_FUSED_MAX_HEIGHT)),
        )
        preview_fusion_config = build_fusion_config_from_group(
            group,
            max_width=preview_max_w,
            max_height=preview_max_h,
        )
        # Dashboard WS preview = resize of the same fused frame (avoids a 2nd fuse+overlay thread).
        self._preview_canvas_size: tuple[int, int] = (
            int(preview_fusion_config.canvas_width),
            int(preview_fusion_config.canvas_height),
        )
        camera_ids = [int(member.camera_id) for member in enabled_members]
        self._synchronizer = FrameSynchronizer(
            self._frame_buffer,
            camera_ids,
            tolerance_ms=runtime_cfg['sync_tolerance_ms'],
        )
        raw_fps = float(runtime_cfg['record_fps'])
        record_fps = raw_fps if raw_fps > 0 else float(settings.RECORD_FPS)
        self._readers = [
            MultiFrameReaderThread(
                CameraSource(
                    camera_id=int(member.camera_id),
                    source=member.camera.rtsp_url,
                ),
                self._frame_buffer,
                stop_event,
                target_fps=record_fps,
            )
            for member in enabled_members
        ]
        self._interval = 1.0 / record_fps
        self._coordinator = threading.Thread(target=self._run_coordinator, daemon=True)
        self._seam_anchor_queue: queue.Queue[dict[int, TimedFrame] | None] = queue.Queue(
            maxsize=1
        )
        self._seam_anchor_thread = threading.Thread(
            target=self._seam_anchor_loop,
            daemon=True,
            name='GroupFrameHubSeamAnchor',
        )

    @property
    def frame_buffer(self) -> LatestFrameBuffer:
        return self._frame_buffer

    def _overlay_fused(
        self,
        fused: Any,
        batch: dict[int, TimedFrame],
        members_by_camera: dict[int, FusionMember],
    ) -> Any:
        if not self._distribute_per_camera or fused is None or fused.size == 0:
            return fused
        return draw_fused_track_overlay(
            fused,
            members_by_camera=members_by_camera,
            batch=batch,
            track_providers=self._track_providers,
        )

    def queue_for_camera(self, camera_id: int) -> queue.Queue:
        camera_key = int(camera_id)
        if camera_key not in self._per_camera_queues:
            raise KeyError(f'No per-camera queue for camera_id={camera_key}')
        return self._per_camera_queues[camera_key]

    def set_track_providers(self, providers: list[TrackProvider]) -> None:
        self._track_providers = list(providers)

    def is_alive(self) -> bool:
        return self._coordinator.is_alive()

    def start(self) -> None:
        for reader in self._readers:
            reader.start()
        self._seam_anchor_thread.start()
        self._coordinator.start()

    def join(self, timeout: float | None = None) -> None:
        self._coordinator.join(timeout=timeout)
        try:
            self._seam_anchor_queue.put_nowait(None)
        except queue.Full:
            pass
        self._seam_anchor_thread.join(timeout=timeout)
        for reader in self._readers:
            reader.join(timeout=timeout)

    def _aggregate_confirmed_tracks(self) -> list[TrackedBoat]:
        merged: list[TrackedBoat] = []
        for provider in self._track_providers:
            try:
                merged.extend(provider())
            except Exception:
                _log.exception('GroupFrameHub track provider failed')
        return merged

    def _run_coordinator(self) -> None:
        next_emit = time.monotonic()
        try:
            while not self._stop_event.is_set():
                now = time.monotonic()
                if now < next_emit:
                    time.sleep(min(0.02, next_emit - now))
                    continue

                scheduled = next_emit
                next_emit = scheduled + self._interval
                if next_emit <= now:
                    next_emit = now + self._interval

                batch = self._synchronizer.next_batch()
                if not batch:
                    continue

                if self._distribute_per_camera:
                    for camera_id, timed_frame in batch.items():
                        camera_queue = self._per_camera_queues.get(int(camera_id))
                        if camera_queue is None:
                            continue
                        put_queue_drop_oldest(camera_queue, timed_frame.frame.copy())

                self._enqueue_seam_anchor(batch)

                fused = self._fuser.fuse(batch)
                if fused is None or fused.size == 0:
                    continue
                fused = self._overlay_fused(fused, batch, self._overlay_members_record)

                self._push_dashboard_preview(fused)

                need_tracks = (
                    self._video_queue is not None or self._on_fused_media_sample is not None
                )
                tracks = self._aggregate_confirmed_tracks() if need_tracks else []
                if self._on_fused_media_sample is not None and fused is not None:
                    try:
                        self._on_fused_media_sample(fused, tracks)
                    except Exception:
                        _log.exception('on_fused_media_sample failed')

                if self._yolo_frame_queue is not None:
                    put_queue_drop_oldest(self._yolo_frame_queue, fused.copy())

                if self._video_queue is not None:
                    put_queue_drop_oldest(self._video_queue, (fused.copy(), tracks))
        except Exception:
            _log.exception('GroupFrameHub coordinator crashed')
        finally:
            self._stop_event.set()

    def _enqueue_seam_anchor(self, batch: dict[int, TimedFrame]) -> None:
        if self._bg_registry is None and self._seam_anchor_verifier is None:
            return
        try:
            self._seam_anchor_queue.put_nowait(batch)
        except queue.Full:
            try:
                self._seam_anchor_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._seam_anchor_queue.put_nowait(batch)
            except queue.Full:
                pass

    def _seam_anchor_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                batch = self._seam_anchor_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if batch is None:
                return
            try:
                self._update_seam_anchor(batch)
            except Exception:
                _log.exception('GroupFrameHub seam anchor update failed')

    def _push_dashboard_preview(self, fused: Any) -> None:
        """Downscale fused output for WS preview (same pixels as old preview_fuser path, one resize)."""
        if fused is None or fused.size == 0:
            return
        try:
            pw, ph = self._preview_canvas_size
            h, w = fused.shape[:2]
            if w == pw and h == ph:
                pipeline_preview.push_bgr_frame(fused)
            else:
                small = cv2.resize(fused, (pw, ph), interpolation=cv2.INTER_AREA)
                pipeline_preview.push_bgr_frame(small)
        except Exception:
            _log.exception('pipeline_preview.push_bgr_frame failed')

    def _update_seam_anchor(self, batch: dict[int, Any]) -> None:
        if self._bg_registry is None and self._seam_anchor_verifier is None:
            return

        raw_frames: dict[int, Any] = {}
        for camera_id, timed_frame in batch.items():
            camera_key = int(camera_id)
            frame = timed_frame.frame
            if frame is None or frame.size == 0:
                continue
            raw_frames[camera_key] = frame
            if self._bg_registry is not None:
                self._bg_registry.update(camera_key, frame)
            if self._seam_anchor_verifier is not None:
                height, width = frame.shape[:2]
                self._seam_anchor_verifier.set_frame_shape(camera_key, height, width)

        if self._seam_anchor_verifier is not None and raw_frames:
            self._seam_anchor_verifier.update_frames(raw_frames)
