"""Offline AI lab: detection overlay frames + Qdrant visual search."""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.core.config import settings
from app.db.session import SessionLocal
from app.repositories.port_config_repository import port_config_repo
from app.services.ai.boat_tracker import BoatTracker, TrackState
from app.services.ai.vector_store_qdrant import QdrantVectorStore
from app.services.ai.visual_embedding_extractor import VisualEmbeddingExtractor
from app.utils.ai.overlay import draw_ship_detection_overlay
from app.utils.ai.yolo_detector import load_yolo_detector

logger = logging.getLogger(__name__)

_COLOR_TENTATIVE = (128, 128, 128)
_COLOR_CONFIRMED = (0, 255, 0)
_COLOR_LOST = (0, 165, 255)

_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}


def media_kind_from_name(filename: str) -> str | None:
    suffix = Path(filename or '').suffix.lower()
    if suffix in _IMAGE_EXTENSIONS:
        return 'image'
    if suffix in _VIDEO_EXTENSIONS:
        return 'video'
    return None


def _color_for_state(state: TrackState) -> tuple[int, int, int]:
    if state == TrackState.TENTATIVE:
        return _COLOR_TENTATIVE
    if state == TrackState.LOST:
        return _COLOR_LOST
    return _COLOR_CONFIRMED


def _encode_jpeg_base64(frame: np.ndarray, *, max_width: int = 1280) -> str:
    output = frame
    height, width = frame.shape[:2]
    if width > max_width > 0:
        scale = max_width / float(width)
        output = cv2.resize(
            frame,
            (max_width, max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    ok, encoded = cv2.imencode('.jpg', output, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    if not ok:
        raise ValueError('Failed to encode preview JPEG')
    return base64.b64encode(encoded.tobytes()).decode('ascii')


def _boat_payload(tb) -> dict[str, Any]:
    box = [int(tb.box[0]), int(tb.box[1]), int(tb.box[2]), int(tb.box[3])]
    return {
        'track_id': str(tb.track_id),
        'state': tb.state.value,
        'confidence': float(tb.conf),
        'box': box,
        'ship_id': str(tb.ship_id) if tb.ship_id else None,
    }


def _process_frame(
    frame: np.ndarray,
    *,
    detector,
    tracker: BoatTracker,
    fps_est: float,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    boxes_list, det_confs = detector.predict_boxes(frame)
    tracked_boats = tracker.update(boxes_list, det_confs)

    annotated = frame.copy()
    for tb in tracked_boats:
        col = _color_for_state(tb.state)
        b = tb.box
        cv2.rectangle(
            annotated,
            (int(b[0]), int(b[1])),
            (int(b[2]), int(b[3])),
            col,
            2,
        )

    overlay = draw_ship_detection_overlay(
        annotated.copy(),
        tracked_boats,
        None,
        None,
        5.0,
        fps_est,
        1.0,
    )
    return overlay, [_boat_payload(tb) for tb in tracked_boats]


def _parse_positive_int(raw: str, default: int) -> int:
    try:
        return max(32, int(float(str(raw).strip())))
    except (TypeError, ValueError):
        return default


def _resolve_lab_yolo_params() -> tuple[str, str, float, int]:
    """Read YOLO params from port_configs (UI) with settings/env fallback."""
    model_path = settings.MODEL_PATH
    device = settings.DEVICE
    conf = float(settings.CONF)
    imgsz = int(settings.YOLO_IMGSZ)

    db = SessionLocal()
    try:
        cfg = {row.key: str(row.value or '').strip() for row in port_config_repo.get_all(db)}
    finally:
        db.close()

    if cfg.get('model_path'):
        model_path = cfg['model_path']
    if cfg.get('device'):
        device = cfg['device']
    if cfg.get('conf'):
        try:
            conf = float(cfg['conf'])
        except ValueError:
            pass
    if cfg.get('yolo_imgsz'):
        imgsz = _parse_positive_int(cfg['yolo_imgsz'], imgsz)

    return model_path, device, conf, imgsz


def run_detection_lab(
    source_path: str,
    *,
    media_kind: str,
    frame_stride: int = 8,
    max_output_frames: int = 48,
) -> dict[str, Any]:
    model_path, device, conf, imgsz = _resolve_lab_yolo_params()
    detector, _ = load_yolo_detector(
        model_path,
        device,
        float(conf),
        imgsz=imgsz,
    )
    tracker = BoatTracker(
        min_hits=1,
        max_tentative_misses=2,
        max_lost_frames=3,
        iou_threshold=settings.TRACK_IOU_THRESHOLD,
        reid_window_sec=settings.TRACK_REID_WINDOW_SEC,
        reid_max_centroid_dist=settings.TRACK_REID_MAX_DIST,
        min_confirm_sec=float(settings.TRACK_MIN_CONFIRM_SEC),
        max_tentative_sec=float(settings.TRACK_MAX_TENTATIVE_SEC),
        max_lost_sec=float(settings.TRACK_MAX_LOST_SEC),
    )

    stride = max(1, int(frame_stride))
    max_frames = max(1, min(int(max_output_frames), 120))
    frames_out: list[dict[str, Any]] = []

    if media_kind == 'image':
        frame = cv2.imread(source_path)
        if frame is None or frame.size == 0:
            raise ValueError('Could not decode image file')
        overlay, boats = _process_frame(frame, detector=detector, tracker=tracker, fps_est=0.0)
        frames_out.append(
            {
                'frame_index': 0,
                'time_sec': 0.0,
                'jpeg_base64': _encode_jpeg_base64(overlay),
                'boats': boats,
            },
        )
        return {
            'media_type': 'image',
            'total_frames': 1,
            'sampled_frames': 1,
            'frames': frames_out,
        }

    cap = cv2.VideoCapture(source_path)
    if not cap.isOpened():
        raise ValueError(f'Could not open video: {source_path}')

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    frame_index = 0
    processed = 0

    while processed < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        frame_index += 1
        if (frame_index - 1) % stride != 0:
            continue

        overlay, boats = _process_frame(
            frame,
            detector=detector,
            tracker=tracker,
            fps_est=fps,
        )
        time_sec = (frame_index - 1) / fps if fps > 0 else 0.0
        frames_out.append(
            {
                'frame_index': frame_index - 1,
                'time_sec': round(time_sec, 3),
                'jpeg_base64': _encode_jpeg_base64(overlay),
                'boats': boats,
            },
        )
        processed += 1

    cap.release()
    tracker.flush_shutdown_logs()

    return {
        'media_type': 'video',
        'total_frames': total_frames if total_frames > 0 else frame_index,
        'sampled_frames': len(frames_out),
        'frame_stride': stride,
        'frames': frames_out,
    }


def decode_upload_bgr(content: bytes) -> np.ndarray:
    arr = np.frombuffer(content, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None or frame.size == 0:
        raise ValueError('Invalid image file')
    return frame


def visual_search_ranked(
    frame: np.ndarray,
    *,
    extractor: VisualEmbeddingExtractor,
    qdrant: QdrantVectorStore,
    top_k: int = 20,
    match_threshold: float = 0.55,
    margin_threshold: float = 0.08,
    consensus_count: int = 2,
) -> dict[str, Any]:
    from app.core.config import settings
    from app.services.ai.visual_ship_matching import resolve_visual_match

    embedding = extractor.extract(frame)
    if embedding is None:
        raise ValueError('Failed to extract visual embedding')

    search_k = max(1, int(top_k or settings.VISUAL_TOP_K))
    hits = qdrant.search(embedding=embedding, top_k=search_k, score_threshold=None)
    decision = resolve_visual_match(
        hits,
        match_threshold=match_threshold,
        margin_threshold=margin_threshold,
        consensus_count=consensus_count,
    )

    ranked_ships = []
    for candidate in decision.ranked_ships:
        preview_url = None
        vessel_id = None
        vessel_name = ''
        filename = candidate.filenames[0] if candidate.filenames else ''
        if candidate.point_ids:
            for hit in hits:
                if str(hit.get('id')) == candidate.point_ids[0]:
                    payload = dict(hit.get('payload') or {})
                    vessel_id = payload.get('vessel_id')
                    vessel_name = str(payload.get('vessel_name') or '')
                    filename = str(payload.get('filename') or filename)
                    if vessel_id is not None:
                        preview_url = (
                            f'/api/v1/vessels/{vessel_id}/visual-enroll/{candidate.point_ids[0]}/preview'
                        )
                    break
        ranked_ships.append(
            {
                'ship_id': candidate.ship_id,
                'aggregated_score': round(candidate.aggregated_score, 4),
                'similarity_percent': round(max(0.0, min(100.0, candidate.aggregated_score * 100.0)), 2),
                'hit_count': candidate.hit_count,
                'point_ids': candidate.point_ids,
                'vessel_id': int(vessel_id) if vessel_id is not None else None,
                'vessel_name': vessel_name,
                'filename': filename,
                'preview_url': preview_url,
            }
        )

    best_match = None
    if decision.best is not None:
        top_ship = ranked_ships[0] if ranked_ships else None
        if top_ship:
            best_match = {
                'point_id': decision.best.point_ids[0] if decision.best.point_ids else '',
                'score': decision.best.aggregated_score,
                'similarity_percent': top_ship['similarity_percent'],
                'ship_id': decision.best.ship_id,
                'vessel_id': top_ship.get('vessel_id'),
                'vessel_name': top_ship.get('vessel_name') or '',
                'filename': top_ship.get('filename') or '',
                'preview_url': top_ship.get('preview_url'),
            }

    return {
        'has_match': decision.accepted,
        'accepted': decision.accepted,
        'match': best_match,
        'ranked_ships': ranked_ships,
        'margin': round(decision.margin, 4),
        'source': decision.source,
        'confidence': round(decision.confidence, 4),
    }


def visual_search_top1(
    frame: np.ndarray,
    *,
    extractor: VisualEmbeddingExtractor,
    qdrant: QdrantVectorStore,
) -> dict[str, Any] | None:
    """Backward-compatible wrapper returning the best aggregated ship match."""
    from app.core.config import settings

    result = visual_search_ranked(
        frame,
        extractor=extractor,
        qdrant=qdrant,
        top_k=settings.VISUAL_TOP_K,
        match_threshold=settings.VISUAL_MATCH_THRESHOLD,
        margin_threshold=settings.VISUAL_MARGIN_THRESHOLD,
        consensus_count=settings.VISUAL_CONSENSUS_COUNT,
    )
    return result.get('match')
