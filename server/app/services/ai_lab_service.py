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
from app.services.ai.ship_id_rule_engine import get_rule_engine
from app.services.ai.frame_fusion import FrameFuser, FusionConfig, FusionMember
from app.services.ai.multi_frame_reader import TimedFrame
from app.services.ai.vector_store_qdrant import QdrantVectorStore
from app.services.ai.visual_embedding_extractor import VisualEmbeddingExtractor
from app.utils.ai.overlay import draw_ship_detection_overlay
from app.utils.ai.pipeline_utils import clamp_box
from app.utils.ai.ship_id_recognizer import create_ship_id_recognizer
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


def _boat_payload(tb, *, ocr_frame: dict | None = None) -> dict[str, Any]:
    box = [int(tb.box[0]), int(tb.box[1]), int(tb.box[2]), int(tb.box[3])]
    payload: dict[str, Any] = {
        'track_id': str(tb.track_id),
        'state': tb.state.value,
        'confidence': float(tb.conf),
        'box': box,
        'ship_id': str(tb.ship_id) if tb.ship_id else None,
    }
    if ocr_frame:
        payload['ocr'] = ocr_frame
    return payload


def _run_ocr_on_tracks(
    frame: np.ndarray,
    tracked_boats: list,
    *,
    tracker: BoatTracker,
    recognizer,
) -> None:
    if recognizer is None:
        return
    height, width = frame.shape[:2]
    for tb in tracked_boats:
        if tb.state != TrackState.CONFIRMED:
            continue
        x1, y1, x2, y2 = clamp_box(tb.box, width, height)
        crop = frame[y1:y2, x1:x2]
        if crop.size <= 0:
            continue
        try:
            ocr_res = recognizer.recognize_bgr(crop)
        except Exception:
            logger.exception('AI Lab OCR failed track_id=%s', tb.track_id)
            continue
        if not ocr_res:
            continue
        best = ocr_res[0]
        sid = str(best.get('id') or '').strip()
        conf = float(best.get('confidence') or 0.0)
        if not sid:
            continue
        tracker.add_ocr_vote(str(tb.track_id), sid, conf)
        voted = tracker.get_voted_ship_id(str(tb.track_id))
        if voted:
            tb.ship_id = voted
            tb.last_known_ship_id = voted


def _ocr_snapshot_for_track(tracker: BoatTracker, track_id: str) -> dict[str, Any] | None:
    hist = tracker.get_ocr_history(track_id)
    if not hist:
        return None
    vote_summary = tracker.get_vote_summary(track_id)
    voted = tracker.get_voted_ship_id(track_id)
    last_sid, last_conf = hist[-1]
    return {
        'last_id': last_sid,
        'last_confidence': round(float(last_conf), 4),
        'voted_id': voted,
        'attempts': len(hist),
        'votes': vote_summary,
    }


def _process_frame(
    frame: np.ndarray,
    *,
    detector,
    tracker: BoatTracker,
    fps_est: float,
    recognizer=None,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    boxes_list, det_confs = detector.predict_boxes(frame)
    tracked_boats = tracker.update(boxes_list, det_confs)

    _run_ocr_on_tracks(frame, tracked_boats, tracker=tracker, recognizer=recognizer)

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
    boats_out = [
        _boat_payload(
            tb,
            ocr_frame=_ocr_snapshot_for_track(tracker, str(tb.track_id)),
        )
        for tb in tracked_boats
    ]
    return overlay, boats_out


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
    enable_ocr: bool = True,
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

    recognizer = None
    ocr_device: str | None = None
    if enable_ocr and settings.ENABLE_OCR:
        recognizer = create_ship_id_recognizer(rule_engine=get_rule_engine())
        ocr_device = str(getattr(recognizer, 'device', 'in-process'))

    stride = max(1, int(frame_stride))
    max_frames = max(1, min(int(max_output_frames), 120))
    frames_out: list[dict[str, Any]] = []

    try:
        if media_kind == 'image':
            frame = cv2.imread(source_path)
            if frame is None or frame.size == 0:
                raise ValueError('Could not decode image file')
            overlay, boats = _process_frame(
                frame,
                detector=detector,
                tracker=tracker,
                fps_est=0.0,
                recognizer=recognizer,
            )
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
                'ocr_enabled': bool(recognizer),
                'ocr_device': ocr_device,
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
                recognizer=recognizer,
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
            'ocr_enabled': bool(recognizer),
            'ocr_device': ocr_device,
            'frames': frames_out,
        }
    finally:
        if recognizer is not None:
            try:
                close_fn = getattr(recognizer, 'close', None)
                if callable(close_fn):
                    close_fn()
            except Exception:
                logger.exception('AI Lab failed to close OCR recognizer')



def _fusion_member_from_group_member(member) -> FusionMember:
    return FusionMember(
        camera_id=int(member.camera_id),
        role=str(getattr(member, 'role', 'tile') or 'tile'),
        priority=int(getattr(member, 'priority', 0) or 0),
        layout_x=int(getattr(member, 'layout_x', 0) or 0),
        layout_y=int(getattr(member, 'layout_y', 0) or 0),
        layout_w=getattr(member, 'layout_w', None),
        layout_h=getattr(member, 'layout_h', None),
        layout_rotation=float(getattr(member, 'layout_rotation', 0) or 0),
        crop_top=int(getattr(member, 'crop_top', 0) or 0),
        crop_bottom=int(getattr(member, 'crop_bottom', 0) or 0),
        crop_left=int(getattr(member, 'crop_left', 0) or 0),
        crop_right=int(getattr(member, 'crop_right', 0) or 0),
        enabled=bool(getattr(member, 'enabled', True)),
    )


def _build_group_fuser(group) -> FrameFuser | None:
    if group is None:
        return None
    members = [
        _fusion_member_from_group_member(member)
        for member in getattr(group, 'members', [])
        if bool(getattr(member, 'enabled', True))
    ]
    if not members:
        return None
    return FrameFuser(
        FusionConfig(
            fusion_mode=str(getattr(group, 'fusion_mode', 'layout') or 'layout'),
            canvas_width=int(getattr(group, 'canvas_width', 1920) or 1920),
            canvas_height=int(getattr(group, 'canvas_height', 1080) or 1080),
            members=members,
        )
    )


def run_group_camera_lab(
    sources: list[dict[str, Any]],
    *,
    frame_stride: int = 8,
    max_output_frames: int = 48,
    enable_ocr: bool = True,
    group=None,
) -> dict[str, Any]:
    """Run offline multi-camera test from synchronized video uploads."""
    if len(sources) < 2:
        raise ValueError('Group Cam Test requires at least 2 video files')

    model_path, device, conf, imgsz = _resolve_lab_yolo_params()
    detector, _ = load_yolo_detector(model_path, device, float(conf), imgsz=imgsz)

    recognizer = None
    ocr_device: str | None = None
    if enable_ocr and settings.ENABLE_OCR:
        recognizer = create_ship_id_recognizer(rule_engine=get_rule_engine())
        ocr_device = str(getattr(recognizer, 'device', 'in-process'))

    stride = max(1, int(frame_stride))
    max_frames = max(1, min(int(max_output_frames), 120))
    caps: dict[int, cv2.VideoCapture] = {}
    trackers: dict[int, BoatTracker] = {}
    metadata: list[dict[str, Any]] = []
    fuser = _build_group_fuser(group)

    try:
        for source in sources:
            camera_id = int(source['camera_id'])
            cap = cv2.VideoCapture(str(source['path']))
            if not cap.isOpened():
                raise ValueError(f'Could not open video for camera {camera_id}: {source.get("filename") or source["path"]}')
            caps[camera_id] = cap
            trackers[camera_id] = BoatTracker(
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
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            metadata.append({
                'camera_id': camera_id,
                'filename': str(source.get('filename') or Path(str(source['path'])).name),
                'total_frames': total_frames,
                'fps': round(fps, 3),
            })

        frames_out: list[dict[str, Any]] = []
        frame_index = 0
        processed = 0
        while processed < max_frames:
            batch: dict[int, np.ndarray] = {}
            exhausted = False
            for camera_id, cap in caps.items():
                ret, frame = cap.read()
                if not ret:
                    exhausted = True
                    break
                batch[camera_id] = frame
            if exhausted:
                break

            current_index = frame_index
            frame_index += 1
            if current_index % stride != 0:
                continue

            cameras_out: list[dict[str, Any]] = []
            timed_frames: dict[int, TimedFrame] = {}
            for source in sources:
                camera_id = int(source['camera_id'])
                frame = batch.get(camera_id)
                if frame is None:
                    continue
                cap = caps[camera_id]
                fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
                overlay, boats = _process_frame(
                    frame,
                    detector=detector,
                    tracker=trackers[camera_id],
                    fps_est=fps,
                    recognizer=recognizer,
                )
                time_sec = current_index / fps if fps > 0 else 0.0
                timed_frames[camera_id] = TimedFrame(camera_id=camera_id, frame=overlay, captured_at=time_sec)
                cameras_out.append({
                    'camera_id': camera_id,
                    'filename': str(source.get('filename') or Path(str(source['path'])).name),
                    'jpeg_base64': _encode_jpeg_base64(overlay),
                    'boats': boats,
                })

            fused_preview = _encode_jpeg_base64(fuser.fuse(timed_frames)) if fuser is not None and timed_frames else None
            time_sec = min((item.captured_at for item in timed_frames.values()), default=0.0)
            frames_out.append({
                'frame_index': current_index,
                'time_sec': round(float(time_sec), 3),
                'fused_jpeg_base64': fused_preview,
                'cameras': cameras_out,
            })
            processed += 1

        for tracker in trackers.values():
            tracker.flush_shutdown_logs()

        return {
            'media_type': 'group_video',
            'group_id': int(getattr(group, 'id', 0) or 0) if group is not None else None,
            'group_name': str(getattr(group, 'name', '') or '') if group is not None else None,
            'camera_count': len(caps),
            'videos': metadata,
            'sampled_frames': len(frames_out),
            'frame_stride': stride,
            'ocr_enabled': bool(recognizer),
            'ocr_device': ocr_device,
            'frames': frames_out,
        }
    finally:
        for cap in caps.values():
            cap.release()
        if recognizer is not None:
            try:
                close_fn = getattr(recognizer, 'close', None)
                if callable(close_fn):
                    close_fn()
            except Exception:
                logger.exception('AI Lab group test failed to close OCR recognizer')


def decode_upload_bgr(content: bytes) -> np.ndarray:
    arr = np.frombuffer(content, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None or frame.size == 0:
        raise ValueError('Invalid image file')
    return frame


def run_ocr_lab(image_bgr: np.ndarray) -> dict[str, Any]:
    """Run pipeline OCR (same recognizer as live pipeline) on a single image/crop."""
    import time

    if image_bgr is None or image_bgr.size == 0:
        raise ValueError('Empty image')

    height, width = image_bgr.shape[:2]
    recognizer = None
    started = time.perf_counter()
    try:
        recognizer = create_ship_id_recognizer(rule_engine=get_rule_engine())
        ship_ids = list(recognizer.recognize_bgr(image_bgr) or [])
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        ocr_device = str(getattr(recognizer, 'device', 'in-process'))

        normalized: list[dict[str, Any]] = []
        for item in ship_ids:
            sid = str(item.get('id') or '').strip()
            if not sid:
                continue
            normalized.append(
                {
                    'id': sid,
                    'confidence': round(float(item.get('confidence') or 0.0), 4),
                    'raw_text': str(item.get('raw_text') or ''),
                }
            )

        return {
            'ocr_device': ocr_device,
            'processing_ms': round(elapsed_ms, 1),
            'image_size': {'width': int(width), 'height': int(height)},
            'matched': len(normalized) > 0,
            'ship_ids': normalized,
            'jpeg_base64': _encode_jpeg_base64(image_bgr),
        }
    finally:
        if recognizer is not None:
            try:
                close_fn = getattr(recognizer, 'close', None)
                if callable(close_fn):
                    close_fn()
            except Exception:
                logger.exception('AI Lab OCR failed to close recognizer')


def visual_search_ranked(
    frame: np.ndarray,
    *,
    extractor: VisualEmbeddingExtractor,
    qdrant: QdrantVectorStore,
    top_k: int = 20,
    match_threshold: float = 0.55,
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
    )
    return result.get('match')
