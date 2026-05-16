from __future__ import annotations

import asyncio

import cv2
from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.repositories.camera_group_repository import camera_group_repo
from app.repositories.camera_repository import camera_repo
from app.repositories.port_config_repository import port_config_repo
from app.repositories.user_repository import user_repo
from app.schemas.camera_group import (
    CameraGroupCreate,
    CameraGroupRead,
    CameraGroupUpdate,
    FusedPreviewRequest,
)
from app.services.ai.frame_fusion import FrameFuser, FusionConfig, FusionMember, scaled_fusion_config
from app.services.ai.multi_frame_reader import TimedFrame, capture_snapshot
from app.services.editor_preview import editor_preview_manager
from app.utils.ws_safe import SafeWebSocket
from app.services.fused_preview_worker import FusedPreviewWorker

router = APIRouter()


def _load_record_fps(db: Session) -> int:
    row = port_config_repo.get_by_key(db, 'record_fps')
    try:
        return max(1, int(str(row.value if row is not None else settings.RECORD_FPS).strip()))
    except Exception:
        return max(1, int(settings.RECORD_FPS))


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
        scaled_fusion_config(
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
                        crop_top=member.crop_top,
                        crop_bottom=member.crop_bottom,
                        crop_left=member.crop_left,
                        crop_right=member.crop_right,
                        enabled=member.enabled,
                    )
                    for member in data.members
                ],
            ),
            max_width=settings.FUSED_FRAME_MAX_WIDTH,
            max_height=settings.FUSED_FRAME_MAX_HEIGHT,
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

    ws = SafeWebSocket(websocket)
    await ws.accept()
    acquired_camera_ids: set[int] = set()
    editor_preview_manager.set_target_fps(record_fps)
    worker = FusedPreviewWorker(target_fps=record_fps)
    worker.start()

    async def receive_configs() -> None:
        nonlocal acquired_camera_ids
        while True:
            raw_config = await ws.receive_json()
            preview_config = FusedPreviewRequest.model_validate(raw_config)
            acquired_camera_ids = _sync_editor_preview_readers(
                preview_config,
                acquired_camera_ids,
            )
            worker.update_config(preview_config)

    receiver_task = asyncio.create_task(receive_configs())

    loop = asyncio.get_running_loop()
    try:
        last_sent_at = loop.time()
        last_sequence = 0
        while True:
            last_sequence, jpeg = await asyncio.to_thread(
                worker.wait_for_jpeg,
                last_sequence,
                1.0,
            )
            if jpeg:
                await ws.send_bytes(jpeg)
                last_sent_at = loop.time()
            else:
                now = loop.time()
                if now - last_sent_at > 15.0:
                    await ws.send_text('ka')
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
    ws = SafeWebSocket(websocket)
    await ws.accept()
    loop = asyncio.get_running_loop()
    try:
        last_sent = loop.time()
        last_sequence = 0
        while True:
            sequence, jpeg = editor_preview_manager.get_jpeg_with_sequence(camera_id)
            if jpeg and sequence > last_sequence:
                last_sequence = sequence
                await ws.send_bytes(jpeg)
                last_sent = loop.time()
            else:
                now = loop.time()
                if now - last_sent > 15.0:
                    await ws.send_text('ka')
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
                        crop_top=member.crop_top,
                        crop_bottom=member.crop_bottom,
                        crop_left=member.crop_left,
                        crop_right=member.crop_right,
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
