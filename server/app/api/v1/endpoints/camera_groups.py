from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models.camera_group import CameraGroupMember
from app.repositories.camera_group_repository import camera_group_repo
from app.repositories.camera_repository import camera_repo
from app.repositories.port_config_repository import port_config_repo
from app.repositories.user_repository import user_repo
from app.schemas.camera_group import (
    AutoCalibrateRequest,
    AutoCalibrateResponse,
    CalibrationComputeRequest,
    CalibrationComputeResponse,
    CameraGroupCreate,
    CameraGroupRead,
    CameraGroupUpdate,
    FusedPreviewRequest,
    ManualPairCalibrationRequest,
    ManualPairCalibrationResponse,
    PairMatchStat,
)
from app.services.ai.frame_fusion import FrameFuser, FusionConfig, FusionMember
from app.services.ai.multi_frame_reader import TimedFrame, capture_snapshot
from app.services.calibration_service import (
    chain_manual_pair_homographies,
    compute_canvas_from_manual_homographies,
    compute_homography,
    compute_pair_homography,
)
from app.services.editor_preview import editor_preview_manager
from app.services.fused_preview_worker import FusedPreviewWorker
from app.services.panorama_stitch_service import auto_stitch

router = APIRouter()


def _load_record_fps(db: Session) -> int:
    row = port_config_repo.get_by_key(db, 'record_fps')
    try:
        return max(1, int(str(row.value if row is not None else settings.RECORD_FPS).strip()))
    except Exception:
        return max(1, int(settings.RECORD_FPS))


def _enabled_members_by_camera_id(group) -> dict[int, CameraGroupMember]:
    return {
        int(member.camera_id): member
        for member in group.members
        if member.enabled
    }


def _capture_ordered_frames(group, camera_order: list[int]) -> dict[int, np.ndarray]:
    members_by_camera_id = _enabled_members_by_camera_id(group)
    frames: dict[int, np.ndarray] = {}

    for camera_id in camera_order:
        member = members_by_camera_id.get(int(camera_id))
        if member is None:
            raise HTTPException(
                status_code=422,
                detail=f'Camera {camera_id} is not an enabled group member',
            )
        if member.camera is None:
            raise HTTPException(status_code=404, detail=f'Camera {camera_id} not found')
        frame = capture_snapshot(member.camera.rtsp_url)
        if frame is not None:
            frames[int(camera_id)] = frame

    missing = [camera_id for camera_id in camera_order if camera_id not in frames]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f'Could not capture frames for cameras: {missing}',
        )
    return frames


def _resolve_camera_order(group, camera_order: list[int] | None) -> list[int]:
    enabled_ids = [
        int(member.camera_id)
        for member in sorted(group.members, key=lambda item: (item.priority, item.id or 0))
        if member.enabled
    ]
    if camera_order is not None:
        requested = [int(camera_id) for camera_id in camera_order]
        resolved = [camera_id for camera_id in requested if camera_id in enabled_ids]
        resolved.extend(camera_id for camera_id in enabled_ids if camera_id not in resolved)
    else:
        resolved = enabled_ids

    if len(resolved) < 2:
        raise HTTPException(status_code=422, detail='Camera order must contain at least two enabled cameras')
    if len(set(resolved)) != len(resolved):
        raise HTTPException(status_code=422, detail='Camera order must not contain duplicate cameras')
    return resolved


def _ensure_ordered_group_members(db: Session, group, camera_order: list[int]) -> None:
    members_by_camera_id = {int(member.camera_id): member for member in group.members}
    next_priority = max((int(member.priority or 0) for member in group.members), default=-1) + 1

    for camera_id in camera_order:
        camera = camera_repo.get(db, int(camera_id))
        if camera is None:
            raise HTTPException(status_code=404, detail=f'Camera {camera_id} not found')

        member = members_by_camera_id.get(int(camera_id))
        if member is not None:
            member.enabled = True
            member.camera = camera
            continue

        member = CameraGroupMember(
            group_id=group.id,
            camera_id=int(camera_id),
            role='tile',
            priority=next_priority,
            enabled=True,
        )
        member.camera = camera
        next_priority += 1
        db.add(member)
        group.members.append(member)

    db.flush()


@router.get('/', response_model=list[CameraGroupRead])
def list_camera_groups(
    active_only: bool = False,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return camera_group_repo.get_all(db, active_only=active_only)


@router.post('/', response_model=CameraGroupRead, status_code=201)
def create_camera_group(
    data: CameraGroupCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return camera_group_repo.create(db, data, created_by=current_user.id)


@router.get('/{group_id}', response_model=CameraGroupRead)
def get_camera_group(
    group_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    group = camera_group_repo.get(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail='Camera group not found')
    return group


@router.patch('/{group_id}', response_model=CameraGroupRead)
def update_camera_group(
    group_id: int,
    data: CameraGroupUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    group = camera_group_repo.get(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail='Camera group not found')
    return camera_group_repo.update(db, group, data)


@router.delete('/{group_id}', status_code=204)
def delete_camera_group(
    group_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    group = camera_group_repo.get(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail='Camera group not found')
    camera_group_repo.delete(db, group)


@router.post('/{group_id}/auto-calibrate', response_model=AutoCalibrateResponse)
def auto_calibrate_group(
    group_id: int,
    data: AutoCalibrateRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    group = camera_group_repo.get(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail='Camera group not found')

    if data.camera_order:
        _ensure_ordered_group_members(db, group, [int(camera_id) for camera_id in data.camera_order])
    camera_order = _resolve_camera_order(group, data.camera_order)
    reference_camera_id = (
        int(data.reference_camera_id)
        if data.reference_camera_id is not None and int(data.reference_camera_id) in camera_order
        else None
    )
    frames = _capture_ordered_frames(group, camera_order)

    try:
        result = auto_stitch(
            frames,
            reference_camera_id=reference_camera_id,
            camera_order=camera_order,
        )
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    homographies = result.homographies
    for member in group.members:
        member.homography = homographies.get(int(member.camera_id))
        member.calibration_points = None

    group.canvas_width = result.canvas_width
    group.canvas_height = result.canvas_height
    group.fusion_mode = 'panorama'
    group.stitch_metadata = {
        'reference_camera_id': result.reference_camera_id,
        'camera_order': camera_order,
        'pair_stats': [stat.__dict__ for stat in result.pair_stats],
        'unmatched_camera_ids': result.unmatched_camera_ids,
        'auto_calibrated_at': datetime.now(timezone.utc).isoformat(),
    }
    db.commit()

    return AutoCalibrateResponse(
        reference_camera_id=result.reference_camera_id,
        canvas_width=result.canvas_width,
        canvas_height=result.canvas_height,
        pair_stats=[PairMatchStat(**stat.__dict__) for stat in result.pair_stats],
        unmatched_camera_ids=result.unmatched_camera_ids,
    )


@router.post('/{group_id}/manual-pair-chain', response_model=ManualPairCalibrationResponse)
def manual_pair_chain_group(
    group_id: int,
    data: ManualPairCalibrationRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    group = camera_group_repo.get(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail='Camera group not found')

    _ensure_ordered_group_members(db, group, [int(camera_id) for camera_id in data.camera_order])
    camera_order = _resolve_camera_order(group, data.camera_order)
    reference_camera_id = (
        int(data.reference_camera_id)
        if data.reference_camera_id is not None and int(data.reference_camera_id) in camera_order
        else None
    )
    adjacent_edges = {
        frozenset((source_id, target_id))
        for source_id, target_id in zip(camera_order, camera_order[1:], strict=False)
    }
    pair_homographies: dict[tuple[int, int], np.ndarray] = {}
    pair_stats: list[PairMatchStat] = []
    manual_pairs = []

    for pair in data.pairs:
        source_id = int(pair.source_camera_id)
        target_id = int(pair.target_camera_id)
        edge = frozenset((source_id, target_id))
        if edge not in adjacent_edges:
            raise HTTPException(
                status_code=422,
                detail=f'Pair {source_id} -> {target_id} is not adjacent in camera_order',
            )
        try:
            matrix, inliers = compute_pair_homography(pair.points)
        except ValueError as err:
            raise HTTPException(status_code=422, detail=str(err)) from err

        pair_homographies[(source_id, target_id)] = matrix
        pair_stats.append(
            PairMatchStat(
                source_camera_id=source_id,
                target_camera_id=target_id,
                matches=len(pair.points),
                inliers=inliers,
                confidence=round(inliers / max(1, len(pair.points)), 4),
            )
        )
        manual_pairs.append(pair.model_dump())

    missing_edges = [
        f'{source_id}-{target_id}'
        for source_id, target_id in zip(camera_order, camera_order[1:], strict=False)
        if frozenset((source_id, target_id)) not in {
            frozenset((source_id, target_id))
            for source_id, target_id in pair_homographies.keys()
        }
    ]
    if missing_edges:
        raise HTTPException(
            status_code=422,
            detail=f'Missing manual points for adjacent pairs: {missing_edges}',
        )

    frames = _capture_ordered_frames(group, camera_order)
    try:
        chained = chain_manual_pair_homographies(
            camera_order,
            pair_homographies,
            reference_camera_id=reference_camera_id,
        )
        canvas_width, canvas_height, final_homographies = compute_canvas_from_manual_homographies(
            frames,
            chained,
        )
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    homographies = {
        camera_id: matrix.astype(float).tolist()
        for camera_id, matrix in final_homographies.items()
    }
    for member in group.members:
        member.homography = homographies.get(int(member.camera_id))
        member.calibration_points = None

    reference_camera_id = reference_camera_id or camera_order[0]
    group.canvas_width = canvas_width
    group.canvas_height = canvas_height
    group.fusion_mode = 'panorama'
    group.stitch_metadata = {
        'reference_camera_id': reference_camera_id,
        'camera_order': camera_order,
        'pair_stats': [stat.model_dump() for stat in pair_stats],
        'manual_pairs': manual_pairs,
        'unmatched_camera_ids': sorted(set(camera_order) - set(homographies.keys())),
        'manual_calibrated_at': datetime.now(timezone.utc).isoformat(),
    }
    db.commit()

    return ManualPairCalibrationResponse(
        reference_camera_id=reference_camera_id,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        pair_stats=pair_stats,
        unmatched_camera_ids=group.stitch_metadata['unmatched_camera_ids'],
    )


@router.post(
    '/{group_id}/members/{camera_id}/calibrate',
    response_model=CalibrationComputeResponse,
)
def calibrate_member(
    group_id: int,
    camera_id: int,
    data: CalibrationComputeRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    member = (
        db.query(CameraGroupMember)
        .filter(
            CameraGroupMember.group_id == group_id,
            CameraGroupMember.camera_id == camera_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail='Camera group member not found')
    try:
        homography, inliers = compute_homography(data.points)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    member.homography = homography
    member.calibration_points = [point.model_dump() for point in data.points]
    db.commit()
    return CalibrationComputeResponse(homography=homography, inliers=inliers)


@router.post(
    '/{group_id}/members/{camera_id}/manual-refine',
    response_model=CalibrationComputeResponse,
)
def manual_refine_member(
    group_id: int,
    camera_id: int,
    data: CalibrationComputeRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    group = camera_group_repo.get(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail='Camera group not found')

    member = next((item for item in group.members if int(item.camera_id) == camera_id), None)
    if not member:
        raise HTTPException(status_code=404, detail='Camera group member not found')

    reference_camera_id = (group.stitch_metadata or {}).get('reference_camera_id')
    if reference_camera_id is None:
        raise HTTPException(status_code=422, detail='Run auto-calibrate before manual refine')

    reference_member = next(
        (item for item in group.members if item.camera_id == int(reference_camera_id)),
        None,
    )
    if reference_member is None or reference_member.homography is None:
        raise HTTPException(status_code=422, detail='Reference camera homography is missing')

    try:
        source_to_reference, inliers = compute_homography(data.points)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    reference_to_canvas = np.array(reference_member.homography, dtype=np.float64)
    source_to_reference_matrix = np.array(source_to_reference, dtype=np.float64)
    refined = reference_to_canvas @ source_to_reference_matrix
    member.homography = refined.astype(float).tolist()
    member.calibration_points = [point.model_dump() for point in data.points]
    db.commit()
    return CalibrationComputeResponse(homography=member.homography, inliers=inliers)


@router.post('/preview-fused')
def preview_fused(
    data: FusedPreviewRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    frames: dict[int, TimedFrame] = {}
    for member in data.members:
        if not member.enabled:
            continue
        camera = camera_repo.get(db, member.camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail=f'Camera {member.camera_id} not found')
        frame = capture_snapshot(camera.rtsp_url)
        if frame is not None:
            frames[int(member.camera_id)] = TimedFrame(int(member.camera_id), frame, 0.0)

    if not frames:
        raise HTTPException(status_code=503, detail='Could not capture any camera frame')

    fuser = FrameFuser(
        FusionConfig(
            fusion_mode=data.fusion_mode,
            canvas_width=data.canvas_width,
            canvas_height=data.canvas_height,
            members=[
                FusionMember(
                    camera_id=member.camera_id,
                    role=member.role,
                    priority=member.priority,
                    layout_x=member.layout_x,
                    layout_y=member.layout_y,
                    layout_w=member.layout_w,
                    layout_h=member.layout_h,
                    layout_rotation=member.layout_rotation,
                    homography=member.homography,
                    enabled=member.enabled,
                )
                for member in data.members
            ],
        )
    )
    fused = fuser.fuse(frames)
    return _jpeg_response(fused)


@router.websocket('/editor-preview/fused')
async def editor_fused_preview_stream(websocket: WebSocket) -> None:
    token = websocket.query_params.get('token')
    if not token:
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    record_fps = max(1, int(settings.RECORD_FPS))
    try:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get('sub')
            if user_id is None:
                await websocket.close(code=1008)
                return
        except JWTError:
            await websocket.close(code=1008)
            return

        user = user_repo.get(db, int(user_id))
        if user is None or not user.is_active:
            await websocket.close(code=1008)
            return
        record_fps = _load_record_fps(db)
    finally:
        db.close()

    await websocket.accept()
    acquired_camera_ids: set[int] = set()
    editor_preview_manager.set_target_fps(record_fps)
    worker = FusedPreviewWorker(target_fps=record_fps)
    worker.start()

    async def receive_configs() -> None:
        nonlocal acquired_camera_ids
        while True:
            raw_config = await websocket.receive_json()
            preview_config = FusedPreviewRequest.model_validate(raw_config)
            acquired_camera_ids = _sync_editor_preview_readers(
                preview_config,
                acquired_camera_ids,
            )
            worker.update_config(preview_config)

    receiver_task = asyncio.create_task(receive_configs())

    try:
        last_sent_at = asyncio.get_event_loop().time()
        last_sequence = 0
        while True:
            last_sequence, jpeg = await asyncio.to_thread(
                worker.wait_for_jpeg,
                last_sequence,
                1.0,
            )
            if jpeg:
                await websocket.send_bytes(jpeg)
                last_sent_at = asyncio.get_event_loop().time()
            else:
                now = asyncio.get_event_loop().time()
                if now - last_sent_at > 15.0:
                    await websocket.send_text('ka')
                    last_sent_at = now
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception:
        return
    finally:
        receiver_task.cancel()
        try:
            await receiver_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        worker.stop()
        worker.join(timeout=2.0)
        for camera_id in acquired_camera_ids:
            editor_preview_manager.release(camera_id)


@router.websocket('/editor-preview/{camera_id}')
async def editor_camera_preview_stream(websocket: WebSocket, camera_id: int) -> None:
    token = websocket.query_params.get('token')
    if not token:
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    record_fps = max(1, int(settings.RECORD_FPS))
    try:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get('sub')
            if user_id is None:
                await websocket.close(code=1008)
                return
        except JWTError:
            await websocket.close(code=1008)
            return

        user = user_repo.get(db, int(user_id))
        if user is None or not user.is_active:
            await websocket.close(code=1008)
            return

        camera = camera_repo.get(db, camera_id)
        if not camera:
            await websocket.close(code=1008)
            return
        source = camera.rtsp_url
        record_fps = _load_record_fps(db)
    finally:
        db.close()

    editor_preview_manager.set_target_fps(record_fps)
    editor_preview_manager.acquire(camera_id, source)
    await websocket.accept()
    try:
        last_sent = 0.0
        last_sequence = 0
        while True:
            sequence, jpeg = editor_preview_manager.get_jpeg_with_sequence(camera_id)
            if jpeg and sequence > last_sequence:
                last_sequence = sequence
                await websocket.send_bytes(jpeg)
                last_sent = asyncio.get_event_loop().time()
            else:
                now = asyncio.get_event_loop().time()
                if now - last_sent > 15.0:
                    await websocket.send_text('ka')
                    last_sent = now
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    except Exception:
        return
    finally:
        editor_preview_manager.release(camera_id)


def _sync_editor_preview_readers(
    data: FusedPreviewRequest,
    acquired_camera_ids: set[int],
) -> set[int]:
    next_camera_ids = {int(member.camera_id) for member in data.members if member.enabled}

    db = SessionLocal()
    try:
        for camera_id in next_camera_ids - acquired_camera_ids:
            camera = camera_repo.get(db, camera_id)
            if camera is not None:
                editor_preview_manager.acquire(camera_id, camera.rtsp_url)
    finally:
        db.close()

    for camera_id in acquired_camera_ids - next_camera_ids:
        editor_preview_manager.release(camera_id)

    return next_camera_ids


def _build_preview_fuser(data: FusedPreviewRequest) -> FrameFuser:
    return FrameFuser(
        FusionConfig(
            fusion_mode=data.fusion_mode,
            canvas_width=data.canvas_width,
            canvas_height=data.canvas_height,
            members=[
                FusionMember(
                    camera_id=member.camera_id,
                    role=member.role,
                    priority=member.priority,
                    layout_x=member.layout_x,
                    layout_y=member.layout_y,
                    layout_w=member.layout_w,
                    layout_h=member.layout_h,
                    layout_rotation=member.layout_rotation,
                    homography=member.homography,
                    enabled=member.enabled,
                )
                for member in data.members
            ],
        )
    )


def _jpeg_response(frame) -> Response:
    ok, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    if not ok:
        raise HTTPException(status_code=500, detail='Failed to encode JPEG')
    return Response(content=encoded.tobytes(), media_type='image/jpeg')
