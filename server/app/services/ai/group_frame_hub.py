"""Shared RTSP readers + fused canvas for group pipeline preview and recording."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from app.services import pipeline_preview
from app.services.ai.boat_tracker import TrackedBoat
from app.services.ai.frame_fusion import FrameFuser, build_fusion_config_from_group
from app.services.ai.frame_synchronizer import FrameSynchronizer
from app.services.ai.multi_frame_reader import CameraSource, LatestFrameBuffer, MultiFrameReaderThread
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
    ) -> None:
        self._stop_event = stop_event
        self._video_queue = video_queue
        self._yolo_frame_queue = yolo_frame_queue
        self._distribute_per_camera = distribute_per_camera
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
        camera_ids = [int(member.camera_id) for member in enabled_members]
        self._synchronizer = FrameSynchronizer(
            self._frame_buffer,
            camera_ids,
            tolerance_ms=runtime_cfg['sync_tolerance_ms'],
        )
        record_fps = runtime_cfg['record_fps']
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
        self._coordinator.start()

    def join(self, timeout: float | None = None) -> None:
        self._coordinator.join(timeout=timeout)
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

                fused = self._fuser.fuse(batch)
                if fused is None or fused.size == 0:
                    continue

                pipeline_preview.push_bgr_frame(fused)

                if self._yolo_frame_queue is not None:
                    put_queue_drop_oldest(self._yolo_frame_queue, fused.copy())

                if self._video_queue is not None:
                    tracks = self._aggregate_confirmed_tracks()
                    put_queue_drop_oldest(self._video_queue, (fused.copy(), tracks))
        except Exception:
            _log.exception('GroupFrameHub coordinator crashed')
        finally:
            self._stop_event.set()
