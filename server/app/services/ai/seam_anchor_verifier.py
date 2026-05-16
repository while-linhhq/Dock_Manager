"""
Seam Anchor Verifier — keep a boat identity alive while it's moored at the
seam between two adjacent cameras (YOLO can't detect the split body).

Verification per frame:
- Anchor remembers two ROIs (one on cam_a, one on cam_b at the seam).
- Background subtraction returns foreground ratio per ROI.
- OCCUPIED when fg ratio > threshold on either ROI -> renew last_seen_ts.
- DEPARTED when fg ratio is below threshold on BOTH ROIs continuously for
  `departed_grace_sec` -> release the anchor (downstream persists Detection).
- Periodic re-validation (color/embedding) prevents false-positive renewal
  by other boats parking at the same spot.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from app.services.ai.background_model import BackgroundModelRegistry
from app.services.ai.boat_tracker import TrackedBoat
from app.services.ai.seam_anchor_color import extract_dominant_hsv, hsv_matches
from app.services.ai.embedding_extractor import (
    EmbeddingExtractor,
    cosine_similarity,
    normalize_embedding,
)
from app.services.ai.motion_classifier import MOTION_STATIC

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeamAnchorConfig:
    enabled: bool = True
    seam_roi_width_ratio: float = 0.15
    seam_proximity_px: int = 40
    bg_subtract_threshold: float = 0.18
    iou_resurrect_threshold: float = 0.3
    embedding_match_enabled: bool = True
    embedding_sim_threshold: float = 0.65
    revalidation_sec: float = 5.0
    departed_grace_sec: float = 30.0
    max_duration_sec: float = 172800.0
    min_stationary_sec: float = 8.0
    color_hsv_tolerance_h: int = 15
    db_update_debounce_sec: float = 30.0


@dataclass
class AnchorState:
    global_id: str
    ship_id: str | None
    track_id: str
    cam_a_id: int
    cam_b_id: int | None
    bbox_a: tuple[int, int, int, int]
    bbox_b: tuple[int, int, int, int] | None
    embedding: np.ndarray | None
    first_seen_ts: float
    last_seen_ts: float
    last_validated_at: float
    miss_started_at: float | None
    anchored_at: float
    last_track: TrackedBoat
    dominant_color_hsv: tuple[int, int, int] | None = None
    ocr_history: list[tuple[str, float]] = field(default_factory=list)
    last_db_flush_at: float = 0.0
    last_score_a: float = 0.0
    last_score_b: float = 0.0


class SeamAnchorVerifier:
    """Verify anchored identities at camera seams using background subtraction."""

    def __init__(
        self,
        *,
        bg_registry: BackgroundModelRegistry,
        camera_order: list[int],
        config: SeamAnchorConfig,
        on_release: Callable[[str, float], None] | None = None,
        embedding_extractor: EmbeddingExtractor | None = None,
        anchored_repo: Any | None = None,
        group_id: int | None = None,
    ) -> None:
        self._bg_registry = bg_registry
        self._camera_order = [int(camera_id) for camera_id in camera_order]
        self._camera_index = {
            camera_id: index for index, camera_id in enumerate(self._camera_order)
        }
        self._config = config
        self._on_release = on_release
        self._embedding_extractor = embedding_extractor
        self._anchored_repo = anchored_repo
        self._group_id = group_id
        self._anchors: dict[str, AnchorState] = {}
        self._frame_shapes: dict[int, tuple[int, int]] = {}
        self._lock = threading.RLock()

    def set_on_release(self, callback: Callable[[str, float], None]) -> None:
        self._on_release = callback

    @property
    def config(self) -> SeamAnchorConfig:
        return self._config

    def adjacent_camera_id(self, camera_id: int, side: str) -> int | None:
        index = self._camera_index.get(int(camera_id))
        if index is None:
            return None
        if side == 'left' and index > 0:
            return self._camera_order[index - 1]
        if side == 'right' and index + 1 < len(self._camera_order):
            return self._camera_order[index + 1]
        return None

    def set_frame_shape(self, camera_id: int, height: int, width: int) -> None:
        with self._lock:
            self._frame_shapes[int(camera_id)] = (int(height), int(width))

    def get_frame_shape(self, camera_id: int) -> tuple[int, int] | None:
        with self._lock:
            return self._frame_shapes.get(int(camera_id))

    def states_snapshot(self) -> list[AnchorState]:
        with self._lock:
            return [self._copy_state(state) for state in self._anchors.values()]

    def debug_info(self) -> dict[str, Any]:
        """Runtime debug payload for GET /pipeline/seam-anchor/state (dashboard overlay)."""
        with self._lock:
            frame_shapes = {
                str(camera_id): [int(height), int(width)]
                for camera_id, (height, width) in self._frame_shapes.items()
            }
            bg_ready: dict[str, bool] = {}
            for camera_id in self._camera_order:
                model = self._bg_registry.get(int(camera_id))
                bg_ready[str(camera_id)] = bool(model is not None and model.is_ready())
            return {
                'bg_subtract_threshold': float(self._config.bg_subtract_threshold),
                'camera_order': list(self._camera_order),
                'frame_shapes': frame_shapes,
                'bg_ready': bg_ready,
                'anchor_count': len(self._anchors),
            }

    def get(self, global_id: str) -> AnchorState | None:
        with self._lock:
            state = self._anchors.get(str(global_id))
            return self._copy_state(state) if state else None

    def try_anchor(
        self,
        *,
        global_id: str,
        ship_id: str | None,
        track_id: str,
        camera_id: int,
        bbox: np.ndarray,
        embedding: np.ndarray | None,
        motion_state: str | None,
        first_seen_ts: float,
        last_seen_ts: float,
        ocr_history: list[tuple[str, float]],
        last_track: TrackedBoat,
        dominant_color_hsv: tuple[int, int, int] | None = None,
    ) -> bool:
        if not self._config.enabled:
            return False
        if motion_state is not None and motion_state != MOTION_STATIC:
            return False
        if self._config.min_stationary_sec > 0:
            static_since = getattr(last_track, 'static_since_ts', None)
            if static_since is None:
                return False
            if time.time() - float(static_since) < self._config.min_stationary_sec:
                return False

        bg_model = self._bg_registry.get(int(camera_id))
        if bg_model is None or not bg_model.is_ready():
            _log.debug(
                'seam_anchor.try_anchor: bg model not ready for camera_id=%s', camera_id
            )
            return False

        frame_shape = self.get_frame_shape(int(camera_id))
        if frame_shape is None:
            _log.debug(
                'seam_anchor.try_anchor: unknown frame shape camera_id=%s', camera_id
            )
            return False

        side = self._bbox_seam_side(bbox, frame_shape)
        if side is None:
            return False

        adjacent_id = self.adjacent_camera_id(int(camera_id), side)
        if adjacent_id is None:
            return False

        bbox_a = self._clamp_bbox(bbox, frame_shape)
        bbox_b = self._seam_roi(adjacent_id, opposite_side(side))
        if bbox_b is None:
            return False

        resolved_color = dominant_color_hsv or getattr(
            last_track, 'dominant_color_hsv', None
        )
        now = time.time()
        state = AnchorState(
            global_id=str(global_id),
            ship_id=ship_id,
            track_id=str(track_id),
            cam_a_id=int(camera_id),
            cam_b_id=int(adjacent_id),
            bbox_a=bbox_a,
            bbox_b=bbox_b,
            dominant_color_hsv=resolved_color,
            embedding=normalize_embedding(embedding) if embedding is not None else None,
            first_seen_ts=float(first_seen_ts),
            last_seen_ts=float(last_seen_ts),
            last_validated_at=now,
            miss_started_at=None,
            anchored_at=now,
            last_track=last_track.copy_public(),
            ocr_history=list(ocr_history),
            last_db_flush_at=now,
        )

        with self._lock:
            self._anchors[state.global_id] = state

        bg_a = self._bg_registry.get(int(camera_id))
        bg_b = self._bg_registry.get(int(adjacent_id))
        if bg_a is not None:
            bg_a.freeze_regions([bbox_a])
        if bg_b is not None:
            bg_b.freeze_regions([bbox_b])

        if self._anchored_repo is not None:
            try:
                self._anchored_repo.upsert(state, group_id=self._group_id)
            except Exception:
                _log.exception('seam_anchor: failed to persist anchor %s', state.global_id)

        _log.info(
            'seam_anchor anchored global_id=%s ship_id=%s cam_a=%s cam_b=%s bbox_a=%s',
            state.global_id,
            state.ship_id,
            state.cam_a_id,
            state.cam_b_id,
            state.bbox_a,
        )
        return True

    def update_frames(self, batch: dict[int, np.ndarray]) -> None:
        if not self._config.enabled or not batch:
            return
        with self._lock:
            anchors = list(self._anchors.values())

        if not anchors:
            return

        now = time.time()
        to_release: list[str] = []
        for anchor in anchors:
            frame_a = batch.get(anchor.cam_a_id)
            frame_b = batch.get(anchor.cam_b_id) if anchor.cam_b_id is not None else None

            score_a = 0.0
            score_b = 0.0
            if frame_a is not None:
                model_a = self._bg_registry.get(anchor.cam_a_id)
                if model_a is not None and model_a.is_ready():
                    score_a = model_a.foreground_ratio(frame_a, anchor.bbox_a)
            if frame_b is not None and anchor.bbox_b is not None:
                model_b = self._bg_registry.get(anchor.cam_b_id) if anchor.cam_b_id is not None else None
                if model_b is not None and model_b.is_ready():
                    score_b = model_b.foreground_ratio(frame_b, anchor.bbox_b)

            occupied = (
                score_a > self._config.bg_subtract_threshold
                or score_b > self._config.bg_subtract_threshold
            )

            with self._lock:
                live = self._anchors.get(anchor.global_id)
                if live is None:
                    continue
                live.last_score_a = float(score_a)
                live.last_score_b = float(score_b)
                if occupied:
                    live.last_seen_ts = now
                    live.miss_started_at = None
                    if (
                        self._config.embedding_match_enabled
                        and now - live.last_validated_at >= self._config.revalidation_sec
                    ):
                        live.last_validated_at = now
                        if not self._revalidate_appearance(live, batch):
                            to_release.append(live.global_id)
                            continue
                else:
                    if live.miss_started_at is None:
                        live.miss_started_at = now
                    elif now - live.miss_started_at >= self._config.departed_grace_sec:
                        to_release.append(live.global_id)
                        continue

                if (
                    self._anchored_repo is not None
                    and now - live.last_db_flush_at >= self._config.db_update_debounce_sec
                ):
                    live.last_db_flush_at = now
                    try:
                        self._anchored_repo.update_last_seen(
                            live.global_id, live.last_seen_ts
                        )
                    except Exception:
                        _log.exception(
                            'seam_anchor: failed to flush last_seen for %s',
                            live.global_id,
                        )

                if now - live.anchored_at >= self._config.max_duration_sec:
                    _log.warning(
                        'seam_anchor: max duration exceeded for %s, releasing',
                        live.global_id,
                    )
                    to_release.append(live.global_id)

        for global_id in to_release:
            self._release_internal(global_id, notify_release=True)

    def try_resurrect(
        self,
        camera_id: int,
        bbox: np.ndarray,
        embedding: np.ndarray | None = None,
    ) -> str | None:
        if not self._config.enabled:
            return None

        best_id: str | None = None
        best_iou = 0.0

        with self._lock:
            candidates = list(self._anchors.values())

        for anchor in candidates:
            roi: tuple[int, int, int, int] | None = None
            if anchor.cam_a_id == int(camera_id):
                roi = anchor.bbox_a
            elif anchor.cam_b_id == int(camera_id) and anchor.bbox_b is not None:
                roi = anchor.bbox_b
            if roi is None:
                continue
            iou = _iou_xyxy_from_xywh(bbox_to_xyxy(np.asarray(bbox, dtype=np.float32)), roi)
            if iou > best_iou:
                best_iou = iou
                best_id = anchor.global_id

        if best_id is None or best_iou < self._config.iou_resurrect_threshold:
            return None

        if self._config.embedding_match_enabled and embedding is not None:
            with self._lock:
                anchor = self._anchors.get(best_id)
            if anchor is not None and anchor.embedding is not None:
                sim = cosine_similarity(anchor.embedding, embedding)
                if sim < self._config.embedding_sim_threshold:
                    _log.info(
                        'seam_anchor: skip resurrect %s due to low embedding sim=%.3f',
                        best_id,
                        sim,
                    )
                    return None

        self._release_internal(best_id, notify_release=False)
        _log.info(
            'seam_anchor: resurrect global_id=%s camera_id=%s iou=%.3f',
            best_id,
            camera_id,
            best_iou,
        )
        return best_id

    def remove(self, global_id: str) -> AnchorState | None:
        return self._release_internal(str(global_id), notify_release=False)

    def restore_from_db(self) -> None:
        if self._anchored_repo is None:
            return
        try:
            rows = self._anchored_repo.list_active(group_id=self._group_id)
        except Exception:
            _log.exception('seam_anchor: failed to load anchored identities from db')
            return

        restored = 0
        with self._lock:
            for row in rows:
                state = self._anchored_repo.row_to_state(row)
                if state is None:
                    continue
                self._anchors[state.global_id] = state
                restored += 1

        for state in list(self._anchors.values()):
            bg_a = self._bg_registry.get(state.cam_a_id)
            if bg_a is not None:
                bg_a.freeze_regions([state.bbox_a])
            if state.cam_b_id is not None and state.bbox_b is not None:
                bg_b = self._bg_registry.get(state.cam_b_id)
                if bg_b is not None:
                    bg_b.freeze_regions([state.bbox_b])

        if restored:
            _log.info('seam_anchor: restored %d anchored identities from db', restored)

    def _release_internal(self, global_id: str, *, notify_release: bool) -> AnchorState | None:
        with self._lock:
            state = self._anchors.pop(global_id, None)

        if state is None:
            return None

        bg_a = self._bg_registry.get(state.cam_a_id)
        if bg_a is not None:
            bg_a.clear_frozen_regions()
        if state.cam_b_id is not None:
            bg_b = self._bg_registry.get(state.cam_b_id)
            if bg_b is not None:
                bg_b.clear_frozen_regions()

        if self._anchored_repo is not None:
            try:
                self._anchored_repo.delete(global_id)
            except Exception:
                _log.exception('seam_anchor: failed to delete anchor row %s', global_id)

        if notify_release and self._on_release is not None:
            try:
                self._on_release(state.global_id, state.last_seen_ts)
            except Exception:
                _log.exception('seam_anchor: on_release callback failed for %s', global_id)

        return state

    def _revalidate_appearance(
        self,
        anchor: AnchorState,
        batch: dict[int, np.ndarray],
    ) -> bool:
        crops: list[np.ndarray] = []
        hsv_samples: list[tuple[int, int, int]] = []
        frame_a = batch.get(anchor.cam_a_id)
        if frame_a is not None:
            model_a = self._bg_registry.get(anchor.cam_a_id)
            if model_a is not None and model_a.is_ready():
                crop, mask = model_a.foreground_crop(frame_a, anchor.bbox_a)
                if _has_signal(mask, self._config.bg_subtract_threshold):
                    crops.append(_apply_mask(crop, mask))
                    sample = extract_dominant_hsv(frame_a, anchor.bbox_a)
                    if sample is not None:
                        hsv_samples.append(sample)

        frame_b = batch.get(anchor.cam_b_id) if anchor.cam_b_id is not None else None
        if frame_b is not None and anchor.bbox_b is not None:
            model_b = (
                self._bg_registry.get(anchor.cam_b_id) if anchor.cam_b_id is not None else None
            )
            if model_b is not None and model_b.is_ready():
                crop, mask = model_b.foreground_crop(frame_b, anchor.bbox_b)
                if _has_signal(mask, self._config.bg_subtract_threshold):
                    crops.append(_apply_mask(crop, mask))
                    sample = extract_dominant_hsv(frame_b, anchor.bbox_b)
                    if sample is not None:
                        hsv_samples.append(sample)

        if anchor.dominant_color_hsv is not None and hsv_samples:
            if not any(
                hsv_matches(
                    anchor.dominant_color_hsv,
                    sample,
                    tolerance_h=self._config.color_hsv_tolerance_h,
                )
                for sample in hsv_samples
            ):
                _log.warning(
                    'seam_anchor: color revalidation failed for %s',
                    anchor.global_id,
                )
                return False

        if anchor.embedding is None or self._embedding_extractor is None:
            return True

        if not crops:
            return True

        for crop in crops:
            try:
                emb = self._embedding_extractor.extract(crop)
            except Exception:
                _log.exception('seam_anchor: embedding extract failed during revalidate')
                continue
            if emb is None:
                continue
            if cosine_similarity(anchor.embedding, emb) >= self._config.embedding_sim_threshold:
                return True

        _log.warning(
            'seam_anchor: revalidation failed for %s — possible foreign object at seam',
            anchor.global_id,
        )
        return False

    def _seam_roi(self, camera_id: int, side: str) -> tuple[int, int, int, int] | None:
        shape = self.get_frame_shape(int(camera_id))
        if shape is None:
            return None
        height, width = shape
        if width <= 0 or height <= 0:
            return None
        seam_w = max(1, int(width * self._config.seam_roi_width_ratio))
        if side == 'left':
            return (0, 0, seam_w, height)
        if side == 'right':
            return (max(0, width - seam_w), 0, seam_w, height)
        return None

    def _bbox_seam_side(
        self,
        bbox: np.ndarray,
        frame_shape: tuple[int, int],
    ) -> str | None:
        height, width = frame_shape
        if width <= 0 or height <= 0:
            return None
        x1, _, x2, _ = (float(v) for v in bbox.tolist())
        proximity = max(1, int(self._config.seam_proximity_px))
        if min(x1, x2) <= proximity:
            return 'left'
        if max(x1, x2) >= width - proximity:
            return 'right'
        return None

    @staticmethod
    def _clamp_bbox(
        bbox: np.ndarray,
        frame_shape: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        height, width = frame_shape
        x1, y1, x2, y2 = (float(v) for v in bbox.tolist())
        x = max(0, int(min(x1, x2)))
        y = max(0, int(min(y1, y2)))
        w = max(1, int(abs(x2 - x1)))
        h = max(1, int(abs(y2 - y1)))
        x = min(width - 1, x)
        y = min(height - 1, y)
        w = min(width - x, w)
        h = min(height - y, h)
        return x, y, w, h

    @staticmethod
    def _copy_state(state: AnchorState | None) -> AnchorState | None:
        if state is None:
            return None
        return AnchorState(
            global_id=state.global_id,
            ship_id=state.ship_id,
            track_id=state.track_id,
            cam_a_id=state.cam_a_id,
            cam_b_id=state.cam_b_id,
            bbox_a=state.bbox_a,
            bbox_b=state.bbox_b,
            dominant_color_hsv=state.dominant_color_hsv,
            embedding=state.embedding.copy() if state.embedding is not None else None,
            first_seen_ts=state.first_seen_ts,
            last_seen_ts=state.last_seen_ts,
            last_validated_at=state.last_validated_at,
            miss_started_at=state.miss_started_at,
            anchored_at=state.anchored_at,
            last_track=state.last_track.copy_public(),
            ocr_history=list(state.ocr_history),
            last_db_flush_at=state.last_db_flush_at,
            last_score_a=state.last_score_a,
            last_score_b=state.last_score_b,
        )


def opposite_side(side: str) -> str:
    return 'right' if side == 'left' else 'left'


def bbox_to_xyxy(bbox: np.ndarray) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (float(v) for v in bbox.tolist())
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _iou_xyxy_from_xywh(
    box_xyxy: tuple[float, float, float, float],
    roi_xywh: tuple[int, int, int, int],
) -> float:
    a_x1, a_y1, a_x2, a_y2 = box_xyxy
    b_x1 = float(roi_xywh[0])
    b_y1 = float(roi_xywh[1])
    b_x2 = b_x1 + float(roi_xywh[2])
    b_y2 = b_y1 + float(roi_xywh[3])
    inter_x1 = max(a_x1, b_x1)
    inter_y1 = max(a_y1, b_y1)
    inter_x2 = min(a_x2, b_x2)
    inter_y2 = min(a_y2, b_y2)
    iw = max(0.0, inter_x2 - inter_x1)
    ih = max(0.0, inter_y2 - inter_y1)
    inter = iw * ih
    area_a = max(0.0, a_x2 - a_x1) * max(0.0, a_y2 - a_y1)
    area_b = max(0.0, b_x2 - b_x1) * max(0.0, b_y2 - b_y1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def _has_signal(mask: np.ndarray, threshold: float) -> bool:
    if mask.size == 0:
        return False
    return float(np.count_nonzero(mask > 0) / mask.size) > threshold


def _apply_mask(crop_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if crop_bgr.size == 0 or mask.size == 0:
        return crop_bgr
    binary = (mask > 0).astype(np.uint8)
    if binary.shape[:2] != crop_bgr.shape[:2]:
        return crop_bgr
    return cv2.bitwise_and(crop_bgr, crop_bgr, mask=binary)
