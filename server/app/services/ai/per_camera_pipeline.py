from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.services import pipeline_preview
from app.services.ai.boat_tracker import BoatTracker, TrackState, TrackedBoat
from app.services.ai.boundary_crossing import (
    BoundaryConfig,
    BoundaryCrossingTracker,
    resolve_bbox_cross_threshold,
)
from app.services.ai.visual_ship_matching import aggregate_visual_hits
from app.services.ai.clahe_preprocessor import ClahePreprocessConfig, preprocess_frame_clahe
from app.utils.ai.box_scale import pad_box, scale_boxes
from app.utils.ai.letterbox import Letterbox, letterbox_frame, unletterbox_boxes
from app.services.ai.cross_camera_reid import CrossCameraReIdManager
from app.services.ai.detection_filter import (
    dedup_overlapping_boxes,
    filter_boxes_by_min_size,
    parse_min_bbox_from_detection_settings,
)
from app.services.ai.embedding_extractor import EmbeddingExtractor
from app.services.ai.frame_reader import FrameReaderThread
from app.services.ai.frame_stats import FrameStats
from app.services.ai.multi_frame_reader import TimedFrame
from app.services.ai.motion_classifier import MOTION_STATIC, MotionClassifier
from app.services.ai.seam_anchor_color import extract_dominant_hsv
from app.services.ai.ship_id_lock import is_track_identity_locked, tracks_open_for_recognition
from app.services.ai.ship_id_catalog import ShipIdCatalog
from app.services.ai.ocr_worker import OcrQueueItem, OcrWorkerThread
from app.services.ai.training_snapshot_collector import (
    TrainingSnapshotCollector,
    TrainingSnapshotConfig,
)
from app.services.ai.visual_id_worker import VisualQueueItem
from app.utils.ai.overlay import draw_berth_state_bbox_overlays, draw_ship_detection_overlay
from app.utils.ai.pipeline_utils import (
    clamp_box,
    drain_queue_latest,
    ocr_cache_key_track,
    put_queue_drop_oldest,
)
from app.utils.ai.ship_id_recognizer import create_ship_id_recognizer

_COLOR_TENTATIVE = (128, 128, 128)
_COLOR_CONFIRMED = (0, 255, 0)
_COLOR_LOST = (0, 165, 255)


logger = logging.getLogger(__name__)

# Nhịp ghi log fps/frame mỗi camera (giây) — rẻ vì chỉ đọc bộ đếm.
FRAME_STATS_LOG_INTERVAL_SEC = 30.0


@dataclass(frozen=True)
class PerCameraPipelineConfig:
    camera_id: int
    source: str | int
    record_fps: float
    enable_ocr: bool
    ocr_interval_sec: float
    ocr_label_ttl_sec: float
    save_min_interval_sec: float
    ocr_audit_save_frames: bool
    resize_scale: float
    track_iou_threshold: float
    track_reid_window_sec: float
    track_reid_max_dist: float
    track_min_confirm_sec: float
    track_max_tentative_sec: float
    track_max_lost_sec: float
    clahe_clip_limit: float
    clahe_tile_size: int
    clahe_enable_gray_world: bool
    edge_zone_ratio: float
    clahe_fast: bool = True
    detect_scale: float = 1.0
    crop_pad_ratio: float = 0.05
    #: Chạy CLAHE ở kích thước detector (letterbox trước) thay vì full-res.
    clahe_after_letterbox: bool = True
    #: Hệ số letterbox trước CLAHE (1.0 = đúng imgsz; 1.5 giữ đủ box, xem CLAHE_LETTERBOX_SCALE).
    clahe_letterbox_scale: float = 1.5
    enable_visual_id: bool = False
    visual_interval_sec: float = 1.0
    visual_min_crop_area: int = 4096
    enable_training_snapshot: bool = False
    training_snapshot_interval_sec: float = 5.0
    enable_preview_stream: bool = False
    boundary_lines: dict | None = None
    detection_settings: dict | None = None
    ship_id_lock_stable_sec: float = 60.0
    visual_match_threshold: float = 0.55
    visual_no_ocr_match_threshold: float = 0.55
    visual_conflict_threshold: float = 0.96
    ocr_confidence_threshold: float = 0.0
    track_dedup_iomin_threshold: float = 0.0
    berth_out_grace_sec: float = 0.0


class PerCameraPipeline(threading.Thread):
    def __init__(
        self,
        *,
        config: PerCameraPipelineConfig,
        detector: Any,
        detector_lock: threading.Lock,
        reid_manager: CrossCameraReIdManager,
        embedding_extractor: EmbeddingExtractor,
        video_queue: queue.Queue | None,
        stop_event: threading.Event,
        ocr_cache: dict,
        ocr_lock: threading.RLock,
        runs_base: str,
        on_image_captured=None,
        on_overlay_media_sample=None,
        on_boundary_media_sample=None,
        input_frame_queue: queue.Queue | None = None,
        shared_ocr_queue: queue.Queue | None = None,
        shared_visual_queue: queue.Queue | None = None,
        single_camera_video_queue: queue.Queue | None = None,
        training_snapshot_collector: TrainingSnapshotCollector | None = None,
        rule_engine=None,
        ship_id_catalog=None,
        frame_stats: FrameStats | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self.config = config
        self._detector = detector
        self._detector_lock = detector_lock
        self._reid_manager = reid_manager
        self._embedding_extractor = embedding_extractor
        self._video_queue = video_queue
        self._single_camera_video_queue = single_camera_video_queue
        self._stop_event = stop_event
        self._ocr_cache = ocr_cache
        self._ocr_lock = ocr_lock
        self._runs_base = runs_base
        self._on_overlay_media_sample = on_overlay_media_sample
        self._on_boundary_media_sample = on_boundary_media_sample
        self._uses_external_frames = input_frame_queue is not None
        self._frame_queue = input_frame_queue or queue.Queue(maxsize=3)
        self._reader: FrameReaderThread | None = None
        if not self._uses_external_frames:
            self._reader = FrameReaderThread(
                config.source,
                self._frame_queue,
                stop_event,
                target_fps=config.record_fps,
            )
        self._tracker = BoatTracker(
            min_hits=1,
            max_tentative_misses=1,
            max_lost_frames=1,
            iou_threshold=config.track_iou_threshold,
            reid_window_sec=config.track_reid_window_sec,
            reid_max_centroid_dist=config.track_reid_max_dist,
            on_track_removed=self._on_local_track_removed,
            camera_id=config.camera_id,
            min_confirm_sec=config.track_min_confirm_sec,
            max_tentative_sec=config.track_max_tentative_sec,
            max_lost_sec=config.track_max_lost_sec,
            visual_match_threshold=config.visual_match_threshold,
            visual_no_ocr_match_threshold=config.visual_no_ocr_match_threshold,
            visual_conflict_threshold=config.visual_conflict_threshold,
            ocr_confidence_threshold=config.ocr_confidence_threshold,
        )
        self._boundary_lines_payload: dict | None = config.boundary_lines
        self._berth_out_grace_sec = float(config.berth_out_grace_sec)
        self._boundary_tracker = self._build_boundary_tracker(self._boundary_lines_payload)
        self._detection_settings_payload: dict | None = config.detection_settings
        self._det_min_bbox_width, self._det_min_bbox_height = parse_min_bbox_from_detection_settings(
            self._detection_settings_payload
        )
        self._motion_classifier = MotionClassifier()
        self._clahe_config = ClahePreprocessConfig(
            clip_limit=config.clahe_clip_limit,
            tile_grid_size=config.clahe_tile_size,
            enable_gray_world=config.clahe_enable_gray_world,
            fast=config.clahe_fast,
        )
        self._shared_ocr_queue = shared_ocr_queue
        self._ocr_queue: queue.Queue | None = None
        self._visual_queue: queue.Queue | None = shared_visual_queue
        self._ocr_worker: OcrWorkerThread | None = None
        self._ship_id_catalog: ShipIdCatalog | None = ship_id_catalog
        if config.enable_ocr:
            if shared_ocr_queue is not None:
                self._ocr_queue = shared_ocr_queue
            else:
                self._ocr_queue = queue.Queue(maxsize=5)
                self._ocr_worker = OcrWorkerThread(
                    create_ship_id_recognizer(rule_engine=rule_engine),
                    self._ocr_queue,
                    self._ocr_cache,
                    self._ocr_lock,
                    self._stop_event,
                    config.ocr_label_ttl_sec,
                    config.save_min_interval_sec,
                    boat_tracker=self._tracker,
                    runs_base=runs_base,
                    save_ocr_audit_frames=config.ocr_audit_save_frames,
                    on_image_captured=on_image_captured,
                    on_ocr_result=self._on_ocr_result,
                    is_known_ship_id=(
                        self._ship_id_catalog.is_known if self._ship_id_catalog else None
                    ),
                )
        self._frame_count = 0
        self._fps_started_at: float | None = None
        self._frame_stats: FrameStats | None = frame_stats
        self._frame_stats_logged_at = 0.0
        self._detect_scale = float(config.detect_scale or 1.0)
        self._crop_pad_ratio = float(config.crop_pad_ratio or 0.0)
        self._clahe_after_letterbox = bool(config.clahe_after_letterbox)
        self._clahe_letterbox_scale = max(1.0, min(2.0, float(config.clahe_letterbox_scale or 1.0)))
        self._detector_imgsz = int(getattr(self._detector, 'imgsz', 0) or 640)
        self._last_ocr_ts = 0.0
        self._last_visual_ts = 0.0
        self._training_snapshot: TrainingSnapshotCollector | None = training_snapshot_collector
        if self._training_snapshot is None and config.enable_training_snapshot:
            base = Path(runs_base).resolve().parents[2] / 'snapshot'
            self._training_snapshot = TrainingSnapshotCollector(
                TrainingSnapshotConfig(
                    enabled=True,
                    interval_sec=float(config.training_snapshot_interval_sec),
                    base_dir=base,
                )
            )

        self._overlay_tracks_lock = threading.Lock()
        self._overlay_tracks: list[TrackedBoat] = []

    @property
    def tracker(self) -> BoatTracker:
        return self._tracker

    def latest_tracks_for_overlay(self) -> list[TrackedBoat]:
        """Tracks + berth state from the last processed frame (for fused hub overlay)."""
        with self._overlay_tracks_lock:
            return [track.copy_public() for track in self._overlay_tracks]

    def _build_boundary_tracker(self, payload: dict | None) -> BoundaryCrossingTracker | None:
        bcfg = BoundaryConfig.from_dict(payload)
        if bcfg is None:
            return None
        # out_grace_sec là knob toàn cục (port_config), không nằm trong
        # boundary_lines JSON per-camera → tiêm vào sau khi parse geometry.
        bcfg.out_grace_sec = self._berth_out_grace_sec
        return BoundaryCrossingTracker(bcfg)

    def update_boundary_lines(self, payload: dict | None) -> None:
        self._boundary_lines_payload = dict(payload) if isinstance(payload, dict) else None
        self._boundary_tracker = self._build_boundary_tracker(self._boundary_lines_payload)

    def update_detection_settings(self, payload: dict | None) -> None:
        self._detection_settings_payload = payload
        self._det_min_bbox_width, self._det_min_bbox_height = parse_min_bbox_from_detection_settings(
            payload
        )

    def start(self) -> None:
        if self._reader is not None:
            self._reader.start()
        if self._ocr_worker is not None:
            self._ocr_worker.start()
        super().start()

    def run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    item = drain_queue_latest(
                        self._frame_queue,
                        self._frame_queue.get(timeout=0.5),
                    )
                except queue.Empty:
                    continue

                if isinstance(item, TimedFrame):
                    raw_frame = item.frame
                    captured_mono = item.captured_at
                else:
                    raw_frame = item
                    captured_mono = time.monotonic()

                self._frame_count += 1
                if self._fps_started_at is None:
                    self._fps_started_at = time.time()
                fps_est = self._frame_count / max(1e-6, time.time() - self._fps_started_at)
                started = time.perf_counter()
                self._process_frame(raw_frame, fps_est, captured_mono=captured_mono)
                self._record_frame_stats((time.perf_counter() - started) * 1000.0)
        except Exception:
            logger.exception(
                'PerCameraPipeline crashed for camera_id=%s',
                self.config.camera_id,
            )
        finally:
            self._stop_event.set()

    def _detect_frame(self, raw_frame: np.ndarray) -> np.ndarray:
        """Frame đưa vào CLAHE + detector; `detect_scale=1.0` thì dùng nguyên frame gốc."""
        if self._detect_scale == 1.0:
            return raw_frame
        return cv2.resize(
            raw_frame,
            None,
            fx=self._detect_scale,
            fy=self._detect_scale,
            interpolation=cv2.INTER_AREA,
        )

    def _queue_boxes(
        self,
        tracks: list[TrackedBoat],
        width: int,
        height: int,
    ) -> list[tuple[str, np.ndarray]]:
        """Box đưa sang OCR/visual, khớp hệ toạ độ crop của embedding.

        Khi `detect_scale < 1.0` box bị lệch vài px nên crop được nới thêm
        `crop_pad_ratio` — nếu chỉ nới ở `_enrich_track` thì embedding trong pipeline
        và embedding của visual worker sẽ khác nhau.
        """
        return [
            (
                track.track_id,
                np.asarray(
                    self._crop_box_for_track(track.box, width, height),
                    dtype=np.float32,
                ),
            )
            for track in tracks
        ]

    def _crop_box_for_track(
        self,
        box: Any,
        width: int,
        height: int,
    ) -> tuple[int, int, int, int]:
        """Box crop cho OCR/embedding; nới thêm khi detection chạy ở tỉ lệ nhỏ."""
        if self._detect_scale != 1.0:
            return pad_box(box, self._crop_pad_ratio, width, height)
        return clamp_box(box, width, height)

    def _record_frame_stats(self, duration_ms: float | None = None) -> None:
        """Ghi nhận 1 frame (kèm ms xử lý) và log định kỳ."""
        stats = self._frame_stats
        if stats is None:
            return
        camera_id = int(self.config.camera_id)
        stats.record(camera_id, duration_ms)
        now = time.time()
        if now - self._frame_stats_logged_at < FRAME_STATS_LOG_INTERVAL_SEC:
            return
        self._frame_stats_logged_at = now
        fps = stats.fps(camera_id)
        avg_ms = stats.avg_ms(camera_id)
        logger.info(
            'camera %s: %s fps · %s ms/frame · %s frame đã xử lý (trung bình từ lúc chạy %.2f fps)',
            camera_id,
            f'{fps:.1f}' if fps is not None else 'n/a',
            f'{avg_ms:.1f}' if avg_ms is not None else 'n/a',
            stats.totals().get(camera_id, 0),
            self._frame_count / max(1e-6, now - (self._fps_started_at or now)),
        )

    def join(self, timeout: float | None = None) -> None:
        if self._reader is not None:
            self._reader.join(timeout=timeout)
        if self._ocr_worker is not None:
            self._ocr_worker.join(timeout=timeout)
        super().join(timeout=timeout)

    def flush_shutdown_logs(self) -> None:
        self._tracker.flush_shutdown_logs()

    def _process_frame(
        self,
        raw_frame: np.ndarray,
        fps_est: float,
        *,
        captured_mono: float | None = None,
    ) -> None:
        detect_frame = self._detect_frame(raw_frame)
        letterbox: Letterbox | None = None
        if self._clahe_after_letterbox:
            # CLAHE ở đúng kích thước detector: resize nội dung trước, tiền xử lý ở đó,
            # rồi mới pad viền — chi tiết CLAHE tạo ra không bị bước letterbox xoá đi.
            letterbox_size = int(round(self._detector_imgsz * self._clahe_letterbox_scale))
            letterbox = letterbox_frame(raw_frame, letterbox_size)
            detect_content = preprocess_frame_clahe(letterbox.content, self._clahe_config)
            processed = letterbox.padded(detect_content)
        else:
            processed = preprocess_frame_clahe(detect_frame, self._clahe_config)
        with self._detector_lock:
            boxes_list, det_confs = self._detector.predict_boxes(processed)
        if letterbox is not None:
            height, width = raw_frame.shape[:2]
            boxes_list = [
                [float(value) for value in box]
                for box in unletterbox_boxes(
                    boxes_list,
                    letterbox.scale,
                    letterbox.pad_x,
                    letterbox.pad_y,
                    width=width,
                    height=height,
                )
            ]
        elif self._detect_scale != 1.0 and detect_frame.shape[1]:
            # Điểm quy đổi DUY NHẤT từ hệ toạ độ detect về hệ full-res. Dùng tỉ lệ thật
            # (cv2 làm tròn khi cạnh lẻ) thay vì hệ số danh nghĩa để mép ảnh không lệch px.
            ratio = raw_frame.shape[1] / detect_frame.shape[1]
            boxes_list = [
                [float(value) for value in box] for box in scale_boxes(boxes_list, ratio)
            ]
        boxes_list, det_confs = filter_boxes_by_min_size(
            boxes_list,
            det_confs,
            self._det_min_bbox_width,
            self._det_min_bbox_height,
        )
        boxes_list, det_confs = dedup_overlapping_boxes(
            boxes_list,
            det_confs,
            self.config.track_dedup_iomin_threshold,
        )
        tracked_boats = self._tracker.update(boxes_list, det_confs)
        catalog_known = (
            self._ship_id_catalog.is_known if self._ship_id_catalog is not None else None
        )
        tracked_boats = self._tracker.update_ship_id_stability(
            lock_sec=float(self.config.ship_id_lock_stable_sec),
            now=time.time(),
            catalog_is_known=catalog_known,
        )

        for track in tracked_boats:
            self._enrich_track(raw_frame, track)

        active_ids = {str(track.track_id) for track in tracked_boats}
        self._motion_classifier.forget_missing(active_ids)
        boundary_crossings: list[tuple[str, str]] = []
        if self._boundary_tracker is not None:
            h, w = raw_frame.shape[:2]
            now_ts = time.time()
            threshold = resolve_bbox_cross_threshold(self._boundary_lines_payload)
            for track in tracked_boats:
                if track.state not in (TrackState.CONFIRMED, TrackState.LOST):
                    track.berth_zone_overlap = None
                    track.berth_zone_threshold = None
                    continue
                box = track.box
                track.berth_zone_overlap = self._boundary_tracker.zone_overlap_ratio(
                    (float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                    w,
                    h,
                )
                track.berth_zone_threshold = threshold
                direction = self._boundary_tracker.update(
                    str(track.track_id),
                    (float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                    now_ts,
                    w,
                    h,
                )
                if direction == 'in':
                    track.berth_in_ts = now_ts
                    crossing_ts = now_ts
                elif direction == 'out':
                    # Mốc OUT là lúc tàu RỜI VÙNG THẬT (đầu grace), không phải
                    # lúc grace hoàn tất — grace chỉ để chờ xác nhận, không cộng
                    # vào thời gian neo đậu. Khi grace tắt, out_event_ts == now_ts.
                    out_ts = self._boundary_tracker.get_out_event_ts(
                        str(track.track_id)
                    )
                    crossing_ts = out_ts if out_ts is not None else now_ts
                    track.berth_out_ts = crossing_ts
                else:
                    crossing_ts = now_ts
                if direction:
                    boundary_crossings.append((str(track.track_id), direction))
                    self._reid_manager.report_boundary_crossing(
                        int(self.config.camera_id),
                        str(track.track_id),
                        direction,
                        crossing_ts,
                    )
                phase = self._boundary_tracker.get_phase(str(track.track_id))
                if phase == 'inside' and track.berth_in_ts is None:
                    track.berth_in_ts = now_ts
                elif phase == 'completed' and track.berth_out_ts is None:
                    track.berth_out_ts = now_ts
            # Commit-OUT-on-death: track đang ở phase 'leaving' (đã rời zone,
            # grace chưa kịp hoàn tất) mà sắp bị forget (track chết / mất YOLO)
            # → chốt OUT tại leaving_since_ts. Giải race grace > track_max_lost.
            leaving_outs = self._boundary_tracker.finalize_leaving_for_missing(
                active_ids
            )
            for tid, out_ts in leaving_outs:
                boundary_crossings.append((tid, 'out'))
                self._reid_manager.report_boundary_crossing(
                    int(self.config.camera_id),
                    tid,
                    'out',
                    out_ts,
                )
            self._boundary_tracker.forget(active_ids)
        else:
            for track in tracked_boats:
                track.berth_zone_overlap = None
                track.berth_zone_threshold = None

        if self._needs_overlay_frame(tracked_boats):
            annotated = raw_frame.copy()
            draw_berth_state_bbox_overlays(annotated, tracked_boats)
            for track in tracked_boats:
                color = _color_for_track(track)
                box = track.box
                cv2.rectangle(
                    annotated,
                    (int(box[0]), int(box[1])),
                    (int(box[2]), int(box[3])),
                    color,
                    2,
                )
            overlay_scale = (
                self.config.resize_scale
                if self.config.resize_scale != 1.0
                else 1.0
            )
            overlay_zone_threshold = resolve_bbox_cross_threshold(self._boundary_lines_payload)
            overlay_frame = draw_ship_detection_overlay(
                annotated,
                tracked_boats,
                self._ocr_cache,
                self._ocr_lock,
                self.config.ocr_label_ttl_sec,
                fps_est,
                overlay_scale,
                frame_captured_mono=captured_mono,
                camera_id=int(self.config.camera_id),
                zone_threshold=overlay_zone_threshold,
            )
            overlay_cfg = BoundaryConfig.for_overlay(self._boundary_lines_payload)
            if overlay_cfg is not None:
                from app.utils.ai.draw_boundary import draw_boundary_lines

                overlay_frame = draw_boundary_lines(overlay_frame, overlay_cfg)
            if self._on_overlay_media_sample is not None:
                try:
                    self._on_overlay_media_sample(
                        int(self.config.camera_id),
                        overlay_frame,
                        tracked_boats,
                    )
                except Exception:
                    logger.exception(
                        'on_overlay_media_sample failed for camera_id=%s',
                        self.config.camera_id,
                    )
            if self._on_boundary_media_sample is not None:
                try:
                    self._on_boundary_media_sample(
                        int(self.config.camera_id),
                        overlay_frame,
                        tracked_boats,
                        boundary_crossings,
                    )
                except Exception:
                    logger.exception(
                        'on_boundary_media_sample failed for camera_id=%s',
                        self.config.camera_id,
                    )
            if self.config.enable_preview_stream:
                pipeline_preview.push_bgr_frame(overlay_frame)
            record_queues = (
                self._video_queue is not None or self._single_camera_video_queue is not None
            )
            if record_queues:
                item = (overlay_frame, tracked_boats)
                if self._video_queue is not None:
                    put_queue_drop_oldest(self._video_queue, item)
                if self._single_camera_video_queue is not None:
                    put_queue_drop_oldest(self._single_camera_video_queue, item)

        self._queue_ocr(raw_frame, tracked_boats)
        self._queue_visual(raw_frame, tracked_boats)
        self._maybe_save_training_snapshots(raw_frame, tracked_boats)
        with self._overlay_tracks_lock:
            self._overlay_tracks = [
                track.copy_public()
                for track in tracked_boats
                if track.state
                in (TrackState.TENTATIVE, TrackState.CONFIRMED, TrackState.LOST)
            ]

    def _needs_overlay_frame(self, tracked_boats: list[TrackedBoat]) -> bool:
        """Chỉ dựng overlay khi có consumer thật cần tới nó.

        Preview stream và ghi video cần overlay mọi frame. Callback media chỉ dùng
        overlay khi có track CONFIRMED (xem `PipelineService._enqueue_media_sample`:
        không có track CONFIRMED thì job bị bỏ ngay).
        """
        if (
            self.config.enable_preview_stream
            or self._video_queue is not None
            or self._single_camera_video_queue is not None
        ):
            return True
        if self._on_overlay_media_sample is None and self._on_boundary_media_sample is None:
            return False
        return any(track.state == TrackState.CONFIRMED for track in tracked_boats)

    def _maybe_save_training_snapshots(
        self,
        raw_frame: np.ndarray,
        tracked_boats: list[TrackedBoat],
    ) -> None:
        collector = self._training_snapshot
        if collector is None or not collector.enabled:
            return
        for track in tracked_boats:
            collector.maybe_save(
                camera_id=int(self.config.camera_id),
                raw_frame=raw_frame,
                track=track,
                ocr_cache=self._ocr_cache,
                ocr_lock=self._ocr_lock,
                boat_tracker=self._tracker,
            )

    def _enrich_track(self, frame: np.ndarray, track: TrackedBoat) -> None:
        if track.state != TrackState.CONFIRMED:
            return
        # Skip embedding/OCR cost for identity-locked tracks — identity is already final
        if is_track_identity_locked(track):
            track.global_id = self._reid_manager.get_global_id(
                int(self.config.camera_id), str(track.track_id)
            )
            return
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = self._crop_box_for_track(track.box, width, height)
        crop = frame[y1:y2, x1:x2]
        embedding = self._embedding_extractor.extract(crop)
        motion_state = self._motion_classifier.classify(frame, track)
        now = time.time()
        if motion_state == MOTION_STATIC:
            if track.static_since_ts is None:
                track.static_since_ts = now
        else:
            track.static_since_ts = None
        dominant_hsv = extract_dominant_hsv(frame, (x1, y1, x2 - x1, y2 - y1))
        self._tracker.update_track_metadata(
            str(track.track_id),
            embedding=embedding,
            motion_state=motion_state,
        )
        track.embedding = embedding
        track.motion_state = motion_state
        track.dominant_color_hsv = dominant_hsv
        self._reid_manager.report_track_update(
            int(self.config.camera_id),
            track,
            embedding=embedding,
            frame_shape=(height, width),
        )
        try:
            reid_diag = self._reid_manager.diagnose_track(
                int(self.config.camera_id),
                track,
                embedding,
                now,
            )
            ck = ocr_cache_key_track(str(track.track_id), int(self.config.camera_id))
            with self._ocr_lock:
                cached = self._ocr_cache.get(ck)
                entry = cached if isinstance(cached, dict) else {}
                entry['reid_diag'] = reid_diag
                entry['time'] = time.time()
                self._ocr_cache[ck] = entry
        except Exception:
            logger.exception(
                'reid diagnose_track failed for camera_id=%s track_id=%s',
                self.config.camera_id,
                track.track_id,
            )
        global_ship_id = self._reid_manager.get_global_ship_id(
            int(self.config.camera_id),
            str(track.track_id),
        )
        if global_ship_id:
            normalized_global = str(global_ship_id).strip().upper()
            current_ship_id = str(track.ship_id or '').strip().upper()
            local_final = (
                getattr(track, 'ship_id_decision_state', None) == 'final'
                and current_ship_id
                and normalized_global != current_ship_id
            )
            if not local_final:
                track.ship_id = global_ship_id
                track.last_known_ship_id = global_ship_id
                self._tracker.update_track_metadata(str(track.track_id), ship_id=global_ship_id)
        track.global_id = self._reid_manager.get_global_id(
            int(self.config.camera_id), str(track.track_id)
        )

    def _queue_ocr(self, frame: np.ndarray, tracked_boats: list[TrackedBoat]) -> None:
        if not self.config.enable_ocr or self._ocr_queue is None:
            return
        now = time.time()
        if now - self._last_ocr_ts < float(self.config.ocr_interval_sec):
            return
        self._last_ocr_ts = now
        confirmed = tracks_open_for_recognition(
            [
                track
                for track in tracked_boats
                if track.state == TrackState.CONFIRMED
                and self._is_in_recognition_zone(track.track_id)
            ]
        )
        if not confirmed:
            return

        height, width = frame.shape[:2]
        items = self._queue_boxes(confirmed, width, height)
        if self._shared_ocr_queue is not None:
            put_queue_drop_oldest(
                self._ocr_queue,
                OcrQueueItem(
                    frame=frame.copy(),
                    boxes_list=items,
                    boat_tracker=self._tracker,
                    on_ocr_result=self._on_ocr_result,
                    camera_id=int(self.config.camera_id),
                ),
            )
        else:
            put_queue_drop_oldest(self._ocr_queue, (frame.copy(), items))

    def _queue_visual(self, frame: np.ndarray, tracked_boats: list[TrackedBoat]) -> None:
        if not self.config.enable_visual_id or self._visual_queue is None:
            return
        now = time.time()
        if now - self._last_visual_ts < float(self.config.visual_interval_sec):
            return
        self._last_visual_ts = now

        confirmed = tracks_open_for_recognition(
            [
                track
                for track in tracked_boats
                if track.state == TrackState.CONFIRMED
                and self._is_in_recognition_zone(track.track_id)
            ]
        )
        if not confirmed:
            return
        height, width = frame.shape[:2]
        items = self._queue_boxes(confirmed, width, height)
        put_queue_drop_oldest(
            self._visual_queue,
            VisualQueueItem(
                frame=frame.copy(),
                boxes_list=items,
                boat_tracker=self._tracker,
                camera_id=int(self.config.camera_id),
                ocr_cache=self._ocr_cache,
                ocr_lock=self._ocr_lock,
                on_visual_result=self._on_visual_result,
            ),
        )

    def _should_accept_ship_id(self, ship_id: str, *, source: str, confidence: float) -> bool:
        if self._ship_id_catalog is not None and not self._ship_id_catalog.is_known(ship_id):
            return False
        if source == 'ocr-hint' and confidence <= 0.0:
            return False
        return True

    def _is_in_recognition_zone(self, track_id: str) -> bool:
        """Gate: True when track bbox overlaps berth zone enough, or no zone configured."""
        track = self._tracker.get_track(str(track_id))
        if track is None:
            return True  # track gone — don't block last-moment vote
        overlap = getattr(track, 'berth_zone_overlap', None)
        threshold = getattr(track, 'berth_zone_threshold', None)
        if overlap is None or threshold is None:
            return True  # camera has no berth zone — no gate
        return bool(overlap >= threshold)

    def _on_ocr_result(self, track_id: str, ship_id: str, confidence: float) -> None:
        if self._tracker.is_track_identity_locked(str(track_id)):
            return
        if not self._is_in_recognition_zone(track_id):
            return
        if not self._should_accept_ship_id(ship_id, source='ocr', confidence=confidence):
            return
        self._reid_manager.report_ocr_result(
            int(self.config.camera_id),
            str(track_id),
            ship_id,
            confidence,
        )
        global_ship_id = self._reid_manager.get_global_ship_id(
            int(self.config.camera_id),
            str(track_id),
        )
        if global_ship_id:
            self._tracker.update_track_metadata(str(track_id), ship_id=global_ship_id)

    def _on_visual_result(
        self,
        track_id: str,
        ship_id: str | None,
        confidence: float,
        source: str,
        top_k: list[dict],
    ) -> None:
        ranked = aggregate_visual_hits(top_k) if top_k else []
        if ranked:
            emb_id = ranked[0].ship_id
            emb_conf = float(ranked[0].aggregated_score)
        else:
            emb_id = ''
            emb_conf = 0.0

        ck = ocr_cache_key_track(str(track_id), int(self.config.camera_id))
        with self._ocr_lock:
            entry = self._ocr_cache.get(ck) if isinstance(self._ocr_cache.get(ck), dict) else {}
            entry.update(
                {
                    'visual_emb_ship_id': emb_id,
                    'visual_emb_confidence': emb_conf,
                    'visual_top_k': top_k,
                    'time': time.time(),
                }
            )
            if ship_id:
                entry.update(
                    {
                        'visual_ship_id': str(ship_id).strip().upper(),
                        'visual_confidence': float(confidence),
                        'visual_source': source,
                    }
                )
            self._ocr_cache[ck] = entry

        if not ship_id or not self._should_accept_ship_id(
            ship_id, source=source, confidence=confidence
        ):
            return
        if self._tracker.is_track_identity_locked(str(track_id)):
            return
        if not self._is_in_recognition_zone(track_id):
            return
        if emb_id and emb_conf > 0:
            self._tracker.add_embedding_vote(str(track_id), emb_id, emb_conf)
        if ship_id and source == 'ocr-hint':
            self._tracker.update_track_metadata(str(track_id), ship_id=ship_id)

    def _on_local_track_removed(
        self,
        track: TrackedBoat,
        ocr_history: list[tuple[str, float]],
    ) -> None:
        self._reid_manager.report_track_removed(
            int(self.config.camera_id),
            track,
            ocr_history,
        )
        # Evict this track's OCR/visual cache entry. Nothing sweeps the shared
        # ocr_cache once a track is gone, so stale per-track entries (incl. the
        # potentially large ``visual_top_k`` payload) accumulate and leak RAM.
        track_id_str = str(track.track_id)
        stale_keys = (
            ocr_cache_key_track(track_id_str, int(self.config.camera_id)),
            ocr_cache_key_track(track_id_str),
        )
        with self._ocr_lock:
            for key in stale_keys:
                self._ocr_cache.pop(key, None)


def _edge_side(box: np.ndarray, width: int, edge_zone_ratio: float) -> str | None:
    x1, _, x2, _ = box.astype(float)
    edge_px = max(1.0, float(width) * float(edge_zone_ratio))
    centroid_x = (x1 + x2) * 0.5
    if centroid_x <= edge_px or x1 <= edge_px:
        return 'left'
    if centroid_x >= width - edge_px or x2 >= width - edge_px:
        return 'right'
    return None


def _color_for_track(track: TrackedBoat) -> tuple[int, int, int]:
    if track.state == TrackState.TENTATIVE:
        return _COLOR_TENTATIVE
    if track.state == TrackState.LOST:
        return _COLOR_LOST
    return _COLOR_CONFIRMED
