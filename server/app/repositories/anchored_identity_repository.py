"""Repository for anchored_identities table (seam-anchor persistence)."""
from __future__ import annotations

import datetime
import logging
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.anchored_identity import AnchoredIdentity
from app.services.ai.boat_tracker import TrackState, TrackedBoat
from app.services.ai.seam_anchor_verifier import AnchorState

_log = logging.getLogger(__name__)


def _utc_from_ts(ts: float) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(float(ts), tz=datetime.timezone.utc)


def _ts_from_utc(value: datetime.datetime | None) -> float:
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.timestamp()


def _bbox_to_payload(bbox: tuple[int, int, int, int] | None) -> dict | None:
    if bbox is None:
        return None
    x, y, w, h = bbox
    return {'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h)}


def _payload_to_bbox(payload: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(payload, dict):
        return None
    try:
        return (
            int(payload['x']),
            int(payload['y']),
            int(payload['w']),
            int(payload['h']),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _embedding_to_bytes(embedding: np.ndarray | None) -> tuple[bytes | None, list[int] | None]:
    if embedding is None:
        return None, None
    arr = np.asarray(embedding, dtype=np.float32)
    return arr.tobytes(), list(arr.shape)


def _bytes_to_embedding(blob: bytes | None, shape: list[int] | None) -> np.ndarray | None:
    if not blob:
        return None
    arr = np.frombuffer(blob, dtype=np.float32)
    if shape:
        try:
            arr = arr.reshape(shape)
        except ValueError:
            pass
    return arr.copy()


def _track_to_payload(track: TrackedBoat) -> dict[str, Any]:
    return {
        'track_id': str(track.track_id),
        'box': [float(v) for v in track.box.tolist()],
        'conf': float(track.conf),
        'first_seen_ts': float(track.first_seen_ts),
        'last_seen_ts': float(track.last_seen_ts),
        'ship_id': track.ship_id,
        'last_known_ship_id': track.last_known_ship_id,
        'camera_id': track.camera_id,
        'motion_state': track.motion_state,
        'hits': int(track.hits),
        'misses': int(track.misses),
        'ever_confirmed': bool(track.ever_confirmed),
    }


def _payload_to_track(payload: Any) -> TrackedBoat | None:
    if not isinstance(payload, dict):
        return None
    try:
        box = np.asarray(payload.get('box') or [0, 0, 0, 0], dtype=np.float32)
        return TrackedBoat(
            track_id=str(payload.get('track_id') or ''),
            state=TrackState.REMOVED,
            box=box,
            conf=float(payload.get('conf') or 0.0),
            hits=int(payload.get('hits') or 0),
            misses=int(payload.get('misses') or 0),
            first_seen_ts=float(payload.get('first_seen_ts') or 0.0),
            last_seen_ts=float(payload.get('last_seen_ts') or 0.0),
            ship_id=payload.get('ship_id'),
            camera_id=payload.get('camera_id'),
            velocity=None,
            embedding=None,
            motion_state=payload.get('motion_state'),
            last_known_ship_id=payload.get('last_known_ship_id'),
            ever_confirmed=bool(payload.get('ever_confirmed', True)),
        )
    except (TypeError, ValueError):
        return None


class AnchoredIdentityRepository:
    """Persist seam anchors so they survive process restarts."""

    def upsert(self, state: AnchorState, *, group_id: int | None = None) -> None:
        embedding_bytes, embedding_shape = _embedding_to_bytes(state.embedding)
        payload = {
            'group_id': int(group_id) if group_id is not None else None,
            'global_id': state.global_id,
            'ship_id': state.ship_id,
            'track_id': state.track_id,
            'cam_a_id': int(state.cam_a_id) if state.cam_a_id is not None else None,
            'cam_b_id': int(state.cam_b_id) if state.cam_b_id is not None else None,
            'bbox_a': _bbox_to_payload(state.bbox_a),
            'bbox_b': _bbox_to_payload(state.bbox_b),
            'embedding': embedding_bytes,
            'embedding_shape': embedding_shape,
            'ocr_history': [
                {'ship_id': str(sid), 'conf': float(conf)} for sid, conf in state.ocr_history
            ],
            'first_seen_at': _utc_from_ts(state.first_seen_ts),
            'last_seen_at': _utc_from_ts(state.last_seen_ts),
            'anchored_at': _utc_from_ts(state.anchored_at),
            'last_track': _track_to_payload(state.last_track),
            'confidence': float(state.last_track.conf) if state.last_track else None,
        }

        db: Session = SessionLocal()
        try:
            row = (
                db.query(AnchoredIdentity)
                .filter(AnchoredIdentity.global_id == state.global_id)
                .first()
            )
            if row is None:
                row = AnchoredIdentity(**payload)
                db.add(row)
            else:
                for key, value in payload.items():
                    setattr(row, key, value)
            db.commit()
        except Exception:
            db.rollback()
            _log.exception('anchored_identity_repo.upsert failed for %s', state.global_id)
            raise
        finally:
            db.close()

    def update_last_seen(self, global_id: str, last_seen_ts: float) -> None:
        db: Session = SessionLocal()
        try:
            row = (
                db.query(AnchoredIdentity)
                .filter(AnchoredIdentity.global_id == str(global_id))
                .first()
            )
            if row is None:
                return
            row.last_seen_at = _utc_from_ts(last_seen_ts)
            db.commit()
        except Exception:
            db.rollback()
            _log.exception('anchored_identity_repo.update_last_seen failed for %s', global_id)
        finally:
            db.close()

    def delete(self, global_id: str) -> None:
        db: Session = SessionLocal()
        try:
            row = (
                db.query(AnchoredIdentity)
                .filter(AnchoredIdentity.global_id == str(global_id))
                .first()
            )
            if row is None:
                return
            db.delete(row)
            db.commit()
        except Exception:
            db.rollback()
            _log.exception('anchored_identity_repo.delete failed for %s', global_id)
        finally:
            db.close()

    def list_active(self, *, group_id: int | None = None) -> list[AnchoredIdentity]:
        db: Session = SessionLocal()
        try:
            query = db.query(AnchoredIdentity)
            if group_id is not None:
                query = query.filter(AnchoredIdentity.group_id == int(group_id))
            return query.all()
        except Exception:
            _log.exception('anchored_identity_repo.list_active failed')
            return []
        finally:
            db.close()

    def row_to_state(self, row: AnchoredIdentity) -> AnchorState | None:
        bbox_a = _payload_to_bbox(row.bbox_a)
        if bbox_a is None:
            return None
        bbox_b = _payload_to_bbox(row.bbox_b)
        embedding = _bytes_to_embedding(row.embedding, row.embedding_shape)
        last_track = _payload_to_track(row.last_track) or TrackedBoat(
            track_id=str(row.track_id or ''),
            state=TrackState.REMOVED,
            box=np.zeros(4, dtype=np.float32),
            conf=float(row.confidence or 0.0),
            hits=0,
            misses=0,
            first_seen_ts=_ts_from_utc(row.first_seen_at),
            last_seen_ts=_ts_from_utc(row.last_seen_at),
            ship_id=row.ship_id,
            camera_id=row.cam_a_id,
            ever_confirmed=True,
        )

        history_payload = row.ocr_history or []
        ocr_history: list[tuple[str, float]] = []
        for item in history_payload:
            if not isinstance(item, dict):
                continue
            ship_id = item.get('ship_id')
            conf = item.get('conf')
            if ship_id is None:
                continue
            try:
                ocr_history.append((str(ship_id), float(conf or 0.0)))
            except (TypeError, ValueError):
                continue

        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        return AnchorState(
            global_id=str(row.global_id),
            ship_id=row.ship_id,
            track_id=str(row.track_id or ''),
            cam_a_id=int(row.cam_a_id) if row.cam_a_id is not None else 0,
            cam_b_id=int(row.cam_b_id) if row.cam_b_id is not None else None,
            bbox_a=bbox_a,
            bbox_b=bbox_b,
            embedding=embedding,
            first_seen_ts=_ts_from_utc(row.first_seen_at),
            last_seen_ts=_ts_from_utc(row.last_seen_at),
            last_validated_at=now,
            miss_started_at=None,
            anchored_at=_ts_from_utc(row.anchored_at),
            last_track=last_track,
            ocr_history=ocr_history,
            last_db_flush_at=now,
        )


anchored_identity_repo = AnchoredIdentityRepository()
