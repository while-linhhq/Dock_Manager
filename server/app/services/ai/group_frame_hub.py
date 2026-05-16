"""Shared RTSP readers + fused canvas for group pipeline preview and recording."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from app.services import pipeline_preview
from app.services.ai.background_model import BackgroundModelRegistry
from app.services.ai.boat_tracker import TrackedBoat
from app.core.config import settings
from app.services.ai.frame_fusion import (
    DEFAULT_FUSED_MAX_HEIGHT,
    DEFAULT_FUSED_MAX_WIDTH,
    FrameFuser,
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
    ) -> None:
        self._stop_event = stop_event
        self._video_queue = video_queue
        self._yolo_frame_queue = yolo_frame_queue
        self._distribute_per_camera = distribute_per_camera
        self._bg_registry = bg_registry
        self._seam_anchor_verifier = seam_anchor_verifier
        self._track_providers: list[TrackProvider] = []
        self._members_by_camera = {
            int(member.camera_id): member for member in enabled_members
        }
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
        self._preview_fuser = FrameFuser(preview_fusion_config)
        camera_ids = [int(member.camera_id) for member in enabled_members]
        self._synchronizer = FrameSynchronizer(
            self._frame_buffer,
            camera_ids,
            tolerance_ms=runtime_cfg['sync_tolerance_ms'],
        )
        record_fps = max(1, int(runtime_cfg['record_fps']))
        self._preview_interval = 1.0 / float(record_fps)
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
        self._interval = 1.0 / max(1.0, float(record_fps))
        self._coordinator = threading.Thread(target=self._run_coordinator, daemon=True)
        self._preview_emitter = threading.Thread(
            target=self._run_preview_emitter,
            name='GroupFrameHub-preview',
            daemon=True,
        )

    @property
    def frame_buffer(self) -> LatestFrameBuffer:
        return self._frame_buffer

    def _overlay_fused(
        self,
        fused: Any,
        batch: dict[int, TimedFrame],
    ) -> Any:
        if not self._distribute_per_camera or fused is None or fused.size == 0:
            return fused
        return draw_fused_track_overlay(
            fused,
            members_by_camera=self._members_by_camera,
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
        return self._coordinator.is_alive() or self._preview_emitter.is_alive()

    def start(self) -> None:
        for reader in self._readers:
            reader.start()
        self._coordinator.start()
        self._preview_emitter.start()

    def join(self, timeout: float | None = None) -> None:
        self._coordinator.join(timeout=timeout)
        self._preview_emitter.join(timeout=timeout)
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

                self._update_seam_anchor(batch)

                fused = self._fuser.fuse(batch)
                if fused is None or fused.size == 0:
                    continue
                fused = self._overlay_fused(fused, batch)

                if self._yolo_frame_queue is not None:
                    put_queue_drop_oldest(self._yolo_frame_queue, fused.copy())

                if self._video_queue is not None:
                    tracks = self._aggregate_confirmed_tracks()
                    put_queue_drop_oldest(self._video_queue, (fused.copy(), tracks))
        except Exception:
            _log.exception('GroupFrameHub coordinator crashed')
        finally:
            self._stop_event.set()

    def _run_preview_emitter(self) -> None:
        """Dedicated fused preview for dashboard WS — not blocked by seam-anchor / AI."""
        next_emit = time.monotonic()
        try:
            while not self._stop_event.is_set():
                now = time.monotonic()
                if now < next_emit:
                    time.sleep(min(0.01, next_emit - now))
                    continue
                next_emit = now + self._preview_interval

                batch = self._synchronizer.next_batch()
                if not batch:
                    continue

                fused = self._preview_fuser.fuse(batch)
                if fused is None or fused.size == 0:
                    continue
                fused = self._overlay_fused(fused, batch)
                pipeline_preview.push_bgr_frame(fused)
        except Exception:
            _log.exception('GroupFrameHub preview emitter crashed')

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
