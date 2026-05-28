import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.repositories.camera_group_repository import camera_group_repo
from app.repositories.camera_repository import camera_repo
from app.repositories.user_repository import user_repo
from app.services import pipeline_preview
from app.services.ai import seam_anchor_baseline
from app.services.ai.multi_frame_reader import capture_snapshot
from app.utils.ai.frame_quality import is_usable_bgr_frame
from app.services.pipeline_service import pipeline_service
from app.utils.ws_safe import SafeWebSocket

router = APIRouter()


class PipelineStartRequest(BaseModel):
    camera_group_id: int
    enable_ocr: bool = True


class PipelineTestVideoRequest(BaseModel):
    source: str
    enable_ocr: bool = True
    save_to_db: bool = True


@router.post("/start")
async def start_pipeline(req: PipelineStartRequest, db: Session = Depends(get_db)):
    if pipeline_service.is_running:
        return {"message": "Pipeline is already running"}
    try:
        group = camera_group_repo.get(db, req.camera_group_id)
        if not group:
            raise HTTPException(status_code=404, detail='Camera group not found')
        if not group.is_active:
            raise HTTPException(status_code=400, detail='Camera group is inactive')
        await asyncio.to_thread(pipeline_service.start_group, group, req.enable_ocr)
        return {
            "message": "Pipeline started",
            "camera_group_id": req.camera_group_id,
            "camera_group_name": group.name,
        }
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err)) from err

@router.post("/stop")
async def stop_pipeline():
    if not pipeline_service.is_running:
        return {"message": "Pipeline is not running"}
    await asyncio.to_thread(pipeline_service.stop)
    return {"message": "Pipeline stopped"}

@router.get("/status")
async def get_status():
    gpu = pipeline_service.gpu_status
    if gpu is None:
        from app.utils.ai.gpu_probe import collect_gpu_runtime_status

        gpu = await asyncio.to_thread(collect_gpu_runtime_status)
    return {
        "is_running": pipeline_service.is_running,
        "ocr_cache_size": len(pipeline_service.ocr_cache),
        "active_group_id": pipeline_service.active_group_id,
        "seam_anchor_active": pipeline_service.seam_anchor_verifier is not None,
        "gpu": gpu,
    }


@router.websocket('/preview-stream')
async def pipeline_preview_stream(websocket: WebSocket) -> None:
    """Binary JPEG frames while pipeline is running; query ?token=JWT."""
    token = websocket.query_params.get('token')
    if not token:
        await websocket.close(code=1008)
        return
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get('sub')
        if user_id is None:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    try:
        user = user_repo.get(db, int(user_id))
        if user is None or not user.is_active:
            await websocket.close(code=1008)
            return
    finally:
        db.close()

    ws = SafeWebSocket(websocket)
    await ws.accept()
    loop = asyncio.get_running_loop()
    try:
        last_sent = loop.time()
        last_sequence = 0
        while True:
            sequence, jpeg = await asyncio.to_thread(
                pipeline_preview.wait_for_jpeg,
                last_sequence,
                1.0,
            )
            if jpeg and sequence > last_sequence:
                last_sequence = sequence
                await ws.send_bytes(jpeg)
                last_sent = loop.time()
            else:
                now = loop.time()
                if now - last_sent > 15.0:
                    await ws.send_text('ka')
                    last_sent = now
    except WebSocketDisconnect:
        pass
    except Exception:
        # Best-effort: avoid crashing the server loop on transient send errors
        return

@router.post("/test-video")
async def test_video(req: PipelineTestVideoRequest):
    """
    Test API: Process a video file and return detection results.
    """
    try:
        results = pipeline_service.test_video_sync(
            req.source,
            req.enable_ocr,
            req.save_to_db,
        )
        return {
            "success": True,
            "source": req.source,
            "saved_to_db": req.save_to_db,
            "detections_count": len(results),
            "results": results
        }
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err)) from err


class SeamAnchorLockRequest(BaseModel):
    group_id: Optional[int] = None
    camera_ids: Optional[list[int]] = None
    force_capture: bool = False

    @model_validator(mode='after')
    def validate_target(self) -> 'SeamAnchorLockRequest':
        if self.group_id is None and not self.camera_ids:
            raise ValueError('Either group_id or camera_ids is required')
        return self


def _resolve_target_cameras(
    db: Session,
    req: SeamAnchorLockRequest,
) -> tuple[list[int], int | None, dict[int, str]]:
    rtsp_by_camera: dict[int, str] = {}
    if req.group_id is not None:
        group = camera_group_repo.get(db, int(req.group_id))
        if not group:
            raise HTTPException(status_code=404, detail='Camera group not found')
        camera_ids = [
            int(member.camera_id)
            for member in group.members
            if bool(member.enabled) and getattr(member, 'camera', None) is not None
        ]
        for member in group.members:
            if member.camera is not None and member.camera.rtsp_url:
                rtsp_by_camera[int(member.camera_id)] = str(member.camera.rtsp_url)
        if req.camera_ids:
            filtered = [cid for cid in camera_ids if cid in set(int(x) for x in req.camera_ids)]
            camera_ids = filtered
        return camera_ids, int(req.group_id), rtsp_by_camera

    camera_ids = [int(x) for x in (req.camera_ids or [])]
    for camera_id in camera_ids:
        camera = camera_repo.get(db, int(camera_id))
        if camera is None:
            raise HTTPException(status_code=404, detail=f'Camera {camera_id} not found')
        if camera.rtsp_url:
            rtsp_by_camera[int(camera_id)] = str(camera.rtsp_url)
    return camera_ids, None, rtsp_by_camera


@router.post('/seam-anchor/lock-background')
async def lock_seam_anchor_background(
    req: SeamAnchorLockRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    camera_ids, group_id, rtsp_by_camera = _resolve_target_cameras(db, req)
    if not camera_ids:
        raise HTTPException(status_code=400, detail='No cameras resolved to lock background')

    use_live_buffer = (
        pipeline_service.is_running
        and not req.force_capture
        and pipeline_service.active_group_id is not None
        and (group_id is None or pipeline_service.active_group_id == group_id)
    )

    locked: list[dict] = []
    failures: list[dict] = []
    live_frames: dict[int, object] | None = None
    if use_live_buffer:
        live_frames = pipeline_service.get_synchronized_frames(
            [int(camera_id) for camera_id in camera_ids],
            timeout_sec=2.5,
        )

    for camera_id in camera_ids:
        frame = None
        source = 'capture'
        if live_frames is not None:
            frame = live_frames.get(int(camera_id))
            if frame is not None:
                source = 'live_sync'

        if frame is None and use_live_buffer:
            frame = pipeline_service.get_latest_camera_frame(int(camera_id))
            if frame is not None:
                source = 'live'

        if frame is None:
            rtsp_url = rtsp_by_camera.get(int(camera_id))
            if not rtsp_url:
                failures.append({'camera_id': camera_id, 'reason': 'rtsp_url_missing'})
                continue
            frame = capture_snapshot(rtsp_url)
            if frame is None:
                failures.append({'camera_id': camera_id, 'reason': 'capture_failed'})
                continue

        if not is_usable_bgr_frame(frame):
            failures.append({'camera_id': camera_id, 'reason': 'frame_quality_rejected'})
            continue

        baseline_path = seam_anchor_baseline.save_baseline(group_id, int(camera_id), frame)
        applied = False
        bg_registry = pipeline_service.bg_registry
        if (
            bg_registry is not None
            and (group_id is None or pipeline_service.active_group_id == group_id)
        ):
            applied = bg_registry.lock_from_frame(int(camera_id), frame)

        locked.append(
            {
                'camera_id': int(camera_id),
                'source': source,
                'baseline_path': baseline_path,
                'applied_to_runtime': applied,
            }
        )

    if not locked:
        raise HTTPException(
            status_code=503,
            detail={'message': 'Failed to lock background', 'failures': failures},
        )

    return {
        'locked': locked,
        'failures': failures,
        'group_id': group_id,
        'used_live_buffer': use_live_buffer,
    }


@router.get('/seam-anchor/state')
async def seam_anchor_state(_=Depends(get_current_user)):
    verifier = pipeline_service.seam_anchor_verifier
    if verifier is None:
        return {
            'enabled': False,
            'anchors': [],
            'message': 'Seam anchor verifier is not active (pipeline not running or hybrid disabled)',
        }

    states = verifier.states_snapshot()
    anchors_payload = []
    for state in states:
        anchors_payload.append(
            {
                'global_id': state.global_id,
                'ship_id': state.ship_id,
                'track_id': state.track_id,
                'cam_a_id': state.cam_a_id,
                'cam_b_id': state.cam_b_id,
                'bbox_a': list(state.bbox_a),
                'bbox_b': list(state.bbox_b) if state.bbox_b else None,
                'first_seen_ts': state.first_seen_ts,
                'last_seen_ts': state.last_seen_ts,
                'anchored_at': state.anchored_at,
                'miss_started_at': state.miss_started_at,
                'last_score_a': state.last_score_a,
                'last_score_b': state.last_score_b,
            }
        )
    debug = verifier.debug_info()
    return {
        'enabled': True,
        'group_id': pipeline_service.active_group_id,
        'anchors': anchors_payload,
        'debug': debug,
    }
