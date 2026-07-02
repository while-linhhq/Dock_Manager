"""IoU-based boat tracker + state machine (TENTATIVE / CONFIRMED / LOST)."""
from __future__ import annotations

import datetime
import threading
import time
from uuid import uuid4
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.services.ai.ship_id_evidence import ShipIdDecision, ShipIdEvidence, ShipIdEvidenceConfig


class TrackState(str, Enum):
    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"
    LOST = "LOST"
    REMOVED = "REMOVED"


def iou_xyxy(a: np.ndarray, b: np.ndarray) -> float:
    """IoU for two xyxy boxes."""
    x1 = max(float(a[0]), float(b[0]))
    y1 = max(float(a[1]), float(b[1]))
    x2 = min(float(a[2]), float(b[2]))
    y2 = min(float(a[3]), float(b[3]))
    iw = max(0.0, x2 - x1)
    ih = max(0.0, y2 - y1)
    inter = iw * ih
    aa = max(0.0, float(a[2]) - float(a[0])) * max(0.0, float(a[3]) - float(a[1]))
    ab = max(0.0, float(b[2]) - float(b[0])) * max(0.0, float(b[3]) - float(b[1]))
    union = aa + ab - inter
    if union <= 0:
        return 0.0
    return inter / union


def _centroid_xyxy(box: np.ndarray) -> tuple[float, float]:
    x1, y1, x2, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
    return ((x1 + x2) * 0.5, (y1 + y2) * 0.5)


def _euclidean(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = a[0] - b[0], a[1] - b[1]
    return float(np.hypot(dx, dy))


def _vote_id_from_hist(hist: list[tuple[str, float]]) -> str | None:
    if not hist:
        return None
    totals: dict[str, float] = {}
    for sid, conf in hist:
        totals[sid] = totals.get(sid, 0.0) + conf
    return max(totals, key=totals.get)  # type: ignore[arg-type]


@dataclass
class TrackedBoat:
    track_id: str
    state: TrackState
    box: np.ndarray
    conf: float
    hits: int
    misses: int
    first_seen_ts: float
    last_seen_ts: float
    ship_id: str | None = None
    camera_id: int | None = None
    velocity: tuple[float, float] | None = None
    embedding: np.ndarray | None = None
    motion_state: str | None = None
    static_since_ts: float | None = None
    dominant_color_hsv: tuple[int, int, int] | None = None
    last_known_ship_id: str | None = None
    global_id: str | None = None
    ever_confirmed: bool = False
    berth_in_ts: float | None = None
    berth_out_ts: float | None = None
    berth_zone_overlap: float | None = None
    berth_zone_threshold: float | None = None
    ship_id_stable_candidate: str | None = None
    ship_id_stable_since_ts: float | None = None
    ship_id_locked: bool = False
    ship_id_locked_value: str | None = None
    ship_id_decision_state: str | None = None
    ship_id_decision_source: str | None = None
    ship_id_evidence_summary: dict | None = None

    def copy_public(self) -> TrackedBoat:
        """Shallow copy with copied box array (safe for queue consumers)."""
        return TrackedBoat(
            track_id=self.track_id,
            state=self.state,
            box=self.box.copy(),
            conf=self.conf,
            hits=self.hits,
            misses=self.misses,
            first_seen_ts=self.first_seen_ts,
            last_seen_ts=self.last_seen_ts,
            ship_id=self.ship_id,
            camera_id=self.camera_id,
            velocity=self.velocity,
            embedding=self.embedding.copy() if self.embedding is not None else None,
            motion_state=self.motion_state,
            static_since_ts=self.static_since_ts,
            dominant_color_hsv=self.dominant_color_hsv,
            last_known_ship_id=self.last_known_ship_id,
            global_id=self.global_id,
            ever_confirmed=self.ever_confirmed,
            berth_in_ts=self.berth_in_ts,
            berth_out_ts=self.berth_out_ts,
            berth_zone_overlap=self.berth_zone_overlap,
            berth_zone_threshold=self.berth_zone_threshold,
            ship_id_stable_candidate=self.ship_id_stable_candidate,
            ship_id_stable_since_ts=self.ship_id_stable_since_ts,
            ship_id_locked=self.ship_id_locked,
            ship_id_locked_value=self.ship_id_locked_value,
            ship_id_decision_state=self.ship_id_decision_state,
            ship_id_decision_source=self.ship_id_decision_source,
            ship_id_evidence_summary=self.ship_id_evidence_summary,
        )


@dataclass
class PendingRemoved:
    """Track đã REMOVED chờ re-id hoặc hết hạn mới ghi log."""

    track: TrackedBoat
    ocr_history: list[tuple[str, float]]
    removed_ts: float
    last_box: np.ndarray
    voted_ship_id: str | None


class BoatTracker:
    """
    Hungarian matching on IoU cost; debounce flicker (LOST) and short FPs (TENTATIVE).
    """

    _BIG = 1e9

    def __init__(
        self,
        min_hits: int = 3,
        max_tentative_misses: int = 3,
        max_lost_frames: int = 45,
        iou_threshold: float = 0.3,
        on_track_removed: Callable[[TrackedBoat, list[tuple[str, float]]], None] | None = None,
        reid_window_sec: float = 120.0,
        reid_max_centroid_dist: float = 150.0,
        camera_id: int | None = None,
        min_confirm_sec: float | None = None,
        max_tentative_sec: float | None = None,
        max_lost_sec: float | None = None,
        visual_match_threshold: float = 0.55,
        visual_no_ocr_match_threshold: float = 0.55,
        visual_conflict_threshold: float = 0.96,
        ocr_confidence_threshold: float = 0.0,
    ):
        self.min_hits = max(1, int(min_hits))
        self.max_tentative_misses = max(1, int(max_tentative_misses))
        self.max_lost_frames = max(1, int(max_lost_frames))
        self.min_confirm_sec = (
            float(min_confirm_sec) if min_confirm_sec is not None and min_confirm_sec > 0 else None
        )
        self.max_tentative_sec = (
            float(max_tentative_sec)
            if max_tentative_sec is not None and max_tentative_sec > 0
            else None
        )
        self.max_lost_sec = (
            float(max_lost_sec) if max_lost_sec is not None and max_lost_sec > 0 else None
        )
        self.iou_threshold = float(iou_threshold)
        self._on_track_removed = on_track_removed
        self.reid_window_sec = float(reid_window_sec)
        self.reid_max_centroid_dist = float(reid_max_centroid_dist)
        self.camera_id = int(camera_id) if camera_id is not None else None

        self._tracks: dict[str, TrackedBoat] = {}
        self._ocr_history: dict[str, list[tuple[str, float]]] = {}
        self._ship_id_evidence: dict[str, ShipIdEvidence] = {}
        self._ship_id_evidence_config = ShipIdEvidenceConfig(
            visual_match_threshold=float(visual_match_threshold),
            visual_no_ocr_match_threshold=float(visual_no_ocr_match_threshold),
            visual_conflict_threshold=float(visual_conflict_threshold),
            ocr_confidence_threshold=float(ocr_confidence_threshold),
        )
        self._id_day: datetime.date | None = None
        self._daily_seq = 0
        self._pending_removed: list[PendingRemoved] = []
        self._lock = threading.RLock()

    def _new_id(self) -> str:
        """Prefix + UUID for globally-unique track_id (stable across restarts)."""
        # Keep a short human prefix for logs; UUID ensures uniqueness.
        return f"trk_{uuid4().hex}"

    def _merge_pending_into_track(
        self, pending: PendingRemoved, tid: str, tb: TrackedBoat
    ) -> bool:
        pending_vote = pending.voted_ship_id or _vote_id_from_hist(pending.ocr_history)
        current_vote = _vote_id_from_hist(self._ocr_history.get(tid, []))
        if pending_vote and current_vote and pending_vote != current_vote:
            return False
        tb.first_seen_ts = pending.track.first_seen_ts
        curr = self._ocr_history.get(tid, [])
        self._ocr_history[tid] = list(pending.ocr_history) + list(curr)
        best = self.get_voted_ship_id(tid)
        if best is not None:
            tb.ship_id = best
        return True

    def _count_confirmed_locked(self) -> int:
        return sum(
            1 for t in self._tracks.values() if t.state == TrackState.CONFIRMED
        )

    def _try_spatial_reid(self, tid: str, tb: TrackedBoat, now: float) -> None:
        if not self._pending_removed:
            return
        if self._count_confirmed_locked() > 1:
            return
        new_c = _centroid_xyxy(tb.box)
        for i, pending in enumerate(self._pending_removed):
            if now - pending.removed_ts > self.reid_window_sec:
                continue
            old_c = _centroid_xyxy(pending.last_box)
            if _euclidean(new_c, old_c) <= self.reid_max_centroid_dist:
                if self._merge_pending_into_track(pending, tid, tb):
                    self._pending_removed.pop(i)
                break

    def _try_shipid_reid(self, track_id: str, tb: TrackedBoat, now: float) -> None:
        best = self.get_voted_ship_id(track_id)
        if best is None:
            return
        for i, pending in enumerate(self._pending_removed):
            if pending.voted_ship_id is None or pending.voted_ship_id != best:
                continue
            if now - pending.removed_ts > self.reid_window_sec:
                continue
            if self._merge_pending_into_track(pending, track_id, tb):
                self._pending_removed.pop(i)
            break

    def _update_track_detection(
        self,
        tb: TrackedBoat,
        box: np.ndarray,
        conf: float,
        now: float,
    ) -> None:
        previous_centroid = _centroid_xyxy(tb.box)
        new_box = np.asarray(box, dtype=np.float32).copy()
        new_centroid = _centroid_xyxy(new_box)
        elapsed = max(1e-6, now - tb.last_seen_ts)
        tb.velocity = (
            (new_centroid[0] - previous_centroid[0]) / elapsed,
            (new_centroid[1] - previous_centroid[1]) / elapsed,
        )
        tb.box = new_box
        tb.conf = float(conf)
        tb.last_seen_ts = now

    def _flush_expired_pending(self, now: float) -> None:
        if not self._pending_removed:
            return
        still: list[PendingRemoved] = []
        for pending in self._pending_removed:
            if now - pending.removed_ts >= self.reid_window_sec:
                if self._on_track_removed is not None:
                    try:
                        self._on_track_removed(pending.track, pending.ocr_history)
                    except Exception as e:
                        print(f"[WARNING] on_track_removed callback error: {e}")
            else:
                still.append(pending)
        self._pending_removed = still

    def _apply_ship_id_decision(self, tb: TrackedBoat, decision: ShipIdDecision) -> None:
        tb.ship_id_decision_state = decision.state
        tb.ship_id_decision_source = decision.source
        tb.ship_id_evidence_summary = self.get_evidence_summary(tb.track_id)
        if decision.ship_id is None:
            return
        tb.ship_id = decision.ship_id
        tb.last_known_ship_id = decision.ship_id

    def _resolve_ship_id_evidence(self, track_id: str, tb: TrackedBoat) -> ShipIdDecision | None:
        evidence = self._ship_id_evidence.get(track_id)
        if evidence is None:
            return None
        decision = evidence.resolve(self._ship_id_evidence_config)
        self._apply_ship_id_decision(tb, decision)
        return decision

    def add_ocr_vote(self, track_id: str, ship_id: str, confidence: float) -> None:
        """Tích lũy một phiếu OCR cho track; cập nhật ship_id theo evidence resolver."""
        now = time.time()
        with self._lock:
            tb = self._tracks.get(track_id)
            if tb is not None and tb.ship_id_locked:
                return
            self._ocr_history.setdefault(track_id, []).append((ship_id, confidence))
            evidence = self._ship_id_evidence.setdefault(track_id, ShipIdEvidence())
            evidence.add_ocr(ship_id, confidence, now=now)
            tb = self._tracks.get(track_id)
            if tb is not None:
                self._resolve_ship_id_evidence(track_id, tb)
            if tb is not None and self.reid_window_sec > 0:
                self._try_shipid_reid(track_id, tb, now)

    def add_embedding_vote(self, track_id: str, ship_id: str, confidence: float) -> None:
        now = time.time()
        with self._lock:
            tb = self._tracks.get(track_id)
            if tb is None or tb.ship_id_locked:
                return
            evidence = self._ship_id_evidence.setdefault(track_id, ShipIdEvidence())
            evidence.add_embedding(ship_id, confidence, now=now)
            self._resolve_ship_id_evidence(track_id, tb)

    def get_voted_ship_id(self, track_id: str) -> str | None:
        """Confidence-weighted majority vote: tổng conf mỗi sid, trả sid cao nhất."""
        with self._lock:
            hist = self._ocr_history.get(track_id)
            if not hist:
                return None
            totals: dict[str, float] = {}
            for sid, conf in hist:
                totals[sid] = totals.get(sid, 0.0) + conf
            return max(totals, key=totals.get)  # type: ignore[arg-type]

    def get_ocr_history(self, track_id: str) -> list[tuple[str, float]]:
        with self._lock:
            return list(self._ocr_history.get(track_id, []))

    def get_vote_summary(self, track_id: str) -> dict[str, dict]:
        """Per-sid: count + total confidence (legacy OCR only)."""
        with self._lock:
            hist = self._ocr_history.get(track_id, [])
            out: dict[str, dict] = {}
            for sid, conf in hist:
                if sid not in out:
                    out[sid] = {"count": 0, "total_conf": 0.0}
                out[sid]["count"] += 1
                out[sid]["total_conf"] += conf
            return out

    def get_evidence_summary(self, track_id: str) -> dict[str, dict]:
        """Two-pool evidence summary for port_logs: {ocr: {...}, embedding: {...}}."""
        with self._lock:
            evidence = self._ship_id_evidence.get(track_id)
            if evidence is None:
                return {}
            out: dict[str, dict] = {}
            if evidence.ocr_pool.votes:
                ocr_rows: dict[str, dict] = {}
                for sid, scores in evidence.ocr_pool.votes.items():
                    ocr_rows[sid] = {
                        "count": len(scores),
                        "total_conf": sum(scores),
                    }
                out["ocr"] = ocr_rows
            if evidence.embedding_pool.votes:
                emb_rows: dict[str, dict] = {}
                for sid, scores in evidence.embedding_pool.votes.items():
                    total = sum(scores)
                    emb_rows[sid] = {
                        "count": len(scores),
                        "total_score": total,
                        "avg_score": total / max(1, len(scores)),
                    }
                out["embedding"] = emb_rows
            return out

    def update(
        self,
        boxes: Sequence[np.ndarray],
        confs: Sequence[float],
        ts: float | None = None,
    ) -> list[TrackedBoat]:
        """
        Match detections to tracks, update state machine.
        Returns active tracks for display: TENTATIVE, CONFIRMED, LOST (not REMOVED).
        Fires on_track_removed callback for each REMOVED track (deferred if re-id enabled).
        """
        now = time.time() if ts is None else float(ts)
        with self._lock:
            boxes = list(boxes)
            confs = list(confs)
            if len(boxes) != len(confs):
                n = min(len(boxes), len(confs))
                boxes, confs = boxes[:n], confs[:n]

            track_ids = [
                tid for tid, t in self._tracks.items() if t.state != TrackState.REMOVED
            ]
            n_t, n_d = len(track_ids), len(boxes)

            matched_track_idx: set[int] = set()
            matched_det_idx: set[int] = set()

            if n_t > 0 and n_d > 0:
                cost = self._build_cost_matrix(track_ids, boxes)
                r, c = linear_sum_assignment(cost)
                for ri, ci in zip(r, c, strict=False):
                    if cost[ri, ci] < self._BIG - 1.0:
                        matched_track_idx.add(ri)
                        matched_det_idx.add(ci)
                        tid = track_ids[ri]
                        tb = self._tracks[tid]
                        b = boxes[ci]
                        cf = confs[ci]
                        self._update_track_detection(tb, b, cf, now)
                        tb.hits += 1
                        tb.misses = 0
                        if tb.state == TrackState.TENTATIVE:
                            if self._should_confirm_tentative(tb, now):
                                tb.state = TrackState.CONFIRMED
                                tb.ever_confirmed = True
                                if self.reid_window_sec > 0:
                                    self._try_spatial_reid(tid, tb, now)
                        elif tb.state == TrackState.LOST:
                            tb.state = TrackState.CONFIRMED
                            tb.ever_confirmed = True

            for j in range(n_d):
                if j in matched_det_idx:
                    continue
                tid = self._new_id()
                self._tracks[tid] = TrackedBoat(
                    track_id=tid,
                    state=TrackState.TENTATIVE,
                    box=np.asarray(boxes[j], dtype=np.float32).copy(),
                    conf=float(confs[j]),
                    hits=1,
                    misses=0,
                    first_seen_ts=now,
                    last_seen_ts=now,
                    ship_id=None,
                    camera_id=self.camera_id,
                )

            for i in range(n_t):
                if i in matched_track_idx:
                    continue
                tid = track_ids[i]
                tb = self._tracks[tid]
                tb.misses += 1
                if tb.state == TrackState.TENTATIVE:
                    if self._should_remove_tentative(tb, now):
                        tb.state = TrackState.REMOVED
                elif tb.state == TrackState.CONFIRMED:
                    if tb.misses >= 1:
                        tb.state = TrackState.LOST
                elif tb.state == TrackState.LOST:
                    if self._should_remove_lost(tb, now):
                        tb.state = TrackState.REMOVED

            to_del = [
                tid for tid, t in self._tracks.items() if t.state == TrackState.REMOVED
            ]
            for tid in to_del:
                tb = self._tracks.pop(tid)
                hist = self._ocr_history.pop(tid, [])
                self._ship_id_evidence.pop(tid, None)
                if not tb.ever_confirmed:
                    continue
                if self.reid_window_sec > 0:
                    vote_snap = _vote_id_from_hist(hist)
                    self._pending_removed.append(
                        PendingRemoved(
                            track=tb.copy_public(),
                            ocr_history=list(hist),
                            removed_ts=now,
                            last_box=tb.box.copy(),
                            voted_ship_id=vote_snap,
                        )
                    )
                elif self._on_track_removed is not None:
                    try:
                        self._on_track_removed(tb.copy_public(), hist)
                    except Exception as e:
                        print(f"[WARNING] on_track_removed callback error: {e}")

            if self.reid_window_sec > 0:
                self._flush_expired_pending(now)

            return self.all_active()

    def update_ship_id_stability(
        self,
        *,
        lock_sec: float,
        now: float,
        catalog_is_known: Callable[[str], bool] | None = None,
    ) -> list[TrackedBoat]:
        """Update ship_id lock state on live tracks and return active copies."""
        from app.services.ai.ship_id_lock import update_tracks_ship_id_stability

        with self._lock:
            for track_id, track in self._tracks.items():
                self._resolve_ship_id_evidence(track_id, track)
            update_tracks_ship_id_stability(
                list(self._tracks.values()),
                lock_sec=lock_sec,
                now=now,
                catalog_is_known=catalog_is_known,
            )
            return self.all_active()

    def _should_confirm_tentative(self, tb: TrackedBoat, now: float) -> bool:
        if self.min_confirm_sec is not None:
            return (
                tb.hits >= 2
                and (now - tb.first_seen_ts) >= self.min_confirm_sec
            )
        return tb.hits >= self.min_hits

    def _should_remove_tentative(self, tb: TrackedBoat, now: float) -> bool:
        if self.max_tentative_sec is not None:
            return (now - tb.last_seen_ts) >= self.max_tentative_sec
        return tb.misses >= self.max_tentative_misses

    def _should_remove_lost(self, tb: TrackedBoat, now: float) -> bool:
        if self.max_lost_sec is not None:
            return (now - tb.last_seen_ts) >= self.max_lost_sec
        return tb.misses >= self.max_lost_frames

    def _build_cost_matrix(
        self, track_ids: list[str], boxes: list[np.ndarray]
    ) -> np.ndarray:
        n_t, n_d = len(track_ids), len(boxes)
        c = np.full((n_t, n_d), self._BIG, dtype=np.float64)
        for i in range(n_t):
            tb = self._tracks[track_ids[i]]
            for j in range(n_d):
                iou = iou_xyxy(tb.box, boxes[j])
                if iou >= self.iou_threshold:
                    c[i, j] = 1.0 - float(iou)
        return c

    def confirmed_boats(self) -> list[TrackedBoat]:
        with self._lock:
            return [
                t.copy_public()
                for t in self._tracks.values()
                if t.state == TrackState.CONFIRMED
            ]

    def all_active(self) -> list[TrackedBoat]:
        """TENTATIVE + CONFIRMED + LOST for overlay / queues."""
        with self._lock:
            out = []
            for t in self._tracks.values():
                if t.state in (
                    TrackState.TENTATIVE,
                    TrackState.CONFIRMED,
                    TrackState.LOST,
                ):
                    out.append(t.copy_public())
            out.sort(key=lambda x: (x.first_seen_ts, x.track_id))
            return out

    def get_track(self, track_id: str) -> TrackedBoat | None:
        with self._lock:
            return self._tracks.get(track_id)

    def get_track_state(self, track_id: str) -> TrackState | None:
        with self._lock:
            tb = self._tracks.get(track_id)
            return tb.state if tb is not None else None

    def is_track_identity_locked(self, track_id: str) -> bool:
        with self._lock:
            tb = self._tracks.get(track_id)
            return bool(tb is not None and tb.ship_id_locked)

    def set_ship_id(self, track_id: str, ship_id: str | None) -> None:
        """Direct set (legacy compat); prefer add_ocr_vote for voting."""
        with self._lock:
            tb = self._tracks.get(track_id)
            if tb is not None and tb.ship_id_locked:
                return
            if tb is not None:
                tb.ship_id = ship_id
                if ship_id:
                    tb.last_known_ship_id = ship_id

    def update_track_metadata(
        self,
        track_id: str,
        *,
        embedding: np.ndarray | None = None,
        motion_state: str | None = None,
        ship_id: str | None = None,
    ) -> None:
        with self._lock:
            tb = self._tracks.get(track_id)
            if tb is None:
                return
            if embedding is not None:
                tb.embedding = np.asarray(embedding, dtype=np.float32).copy()
            if motion_state is not None:
                tb.motion_state = motion_state
            if ship_id and not tb.ship_id_locked:
                normalized_ship_id = str(ship_id).strip().upper()
                current_ship_id = str(tb.ship_id or '').strip().upper()
                if (
                    tb.ship_id_decision_state == 'final'
                    and current_ship_id
                    and normalized_ship_id != current_ship_id
                ):
                    return
                tb.ship_id = ship_id
                tb.last_known_ship_id = ship_id

    def flush_shutdown_logs(self) -> None:
        """
        Gọi khi dừng nguồn (video/RTSP tắt hoặc user Stop): đảm bảo ghi JSONL.

        - Mọi track trong ``_pending_removed`` (chờ re-ID) được ghi ngay (không chờ hết cửa sổ).
        - Mọi track còn lại đã ``ever_confirmed`` được ghi như khi track kết thúc.
        - Track chưa từng CONFIRMED bị bỏ qua (giống logic REMOVED thường).
        """
        with self._lock:
            if self._on_track_removed is None:
                self._pending_removed.clear()
                self._tracks.clear()
                self._ocr_history.clear()
                self._ship_id_evidence.clear()
                return

            for pending in list(self._pending_removed):
                try:
                    self._on_track_removed(
                        pending.track, list(pending.ocr_history)
                    )
                except Exception as e:
                    print(f"[WARNING] on_track_removed callback error: {e}")
            self._pending_removed.clear()

            for tid in list(self._tracks.keys()):
                tb = self._tracks.get(tid)
                if tb is None:
                    continue
                if not tb.ever_confirmed:
                    self._tracks.pop(tid, None)
                    self._ocr_history.pop(tid, None)
                    self._ship_id_evidence.pop(tid, None)
                    continue
                hist = list(self._ocr_history.pop(tid, []))
                self._ship_id_evidence.pop(tid, None)
                self._tracks.pop(tid, None)
                snap = tb.copy_public()
                snap.state = TrackState.REMOVED
                try:
                    self._on_track_removed(snap, hist)
                except Exception as e:
                    print(f"[WARNING] on_track_removed callback error: {e}")
