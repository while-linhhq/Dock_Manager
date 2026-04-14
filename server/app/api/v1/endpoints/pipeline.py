import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.repositories.camera_repository import camera_repo
from app.repositories.user_repository import user_repo
from app.services import pipeline_preview
from app.services.pipeline_service import pipeline_service

router = APIRouter()


class PipelineStartRequest(BaseModel):
    source: Optional[str] = None
    camera_id: Optional[int] = None
    enable_ocr: bool = True

    @model_validator(mode='after')
    def validate_source_or_camera(self) -> 'PipelineStartRequest':
        if not self.source and self.camera_id is None:
            raise ValueError('Either source or camera_id is required')
        return self


class PipelineTestVideoRequest(BaseModel):
    source: str
    enable_ocr: bool = True
    save_to_db: bool = True


@router.post("/start")
async def start_pipeline(req: PipelineStartRequest, db: Session = Depends(get_db)):
    if pipeline_service.is_running:
        return {"message": "Pipeline is already running"}
    try:
        resolved_source = req.source
        camera_name = None

        if req.camera_id is not None:
            camera = camera_repo.get(db, req.camera_id)
            if not camera:
                raise HTTPException(status_code=404, detail='Camera not found')
            # Không chặn is_active: khởi chạy pipeline là thao tác chủ động; cờ active chủ yếu
            # dùng cho thống kê / danh sách mặc định. RTSP vẫn có thể hợp lệ khi camera «tắt».
            resolved_source = camera.rtsp_url
            camera_name = camera.camera_name

        if not resolved_source:
            raise HTTPException(status_code=400, detail='No source resolved for pipeline')

        pipeline_service.start(resolved_source, req.enable_ocr)
        return {
            "message": "Pipeline started",
            "source": resolved_source,
            "camera_id": req.camera_id,
            "camera_name": camera_name,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_pipeline():
    if not pipeline_service.is_running:
        return {"message": "Pipeline is not running"}
    pipeline_service.stop()
    return {"message": "Pipeline stopped"}

@router.get("/status")
async def get_status():
    return {
        "is_running": pipeline_service.is_running,
        "ocr_cache_size": len(pipeline_service.ocr_cache)
    }


@router.websocket('/preview-stream')
async def pipeline_preview_stream(websocket: WebSocket) -> None:
    """Binary JPEG frames (~8 fps) while pipeline is running; query ?token=JWT."""
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

    await websocket.accept()
    try:
        last_sent = 0.0
        while True:
            jpeg = pipeline_preview.get_jpeg()
            if jpeg:
                await websocket.send_bytes(jpeg)
                last_sent = asyncio.get_event_loop().time()
            else:
                # Keep the connection alive even if no new frames yet (proxy/NAT idle timeout).
                now = asyncio.get_event_loop().time()
                if now - last_sent > 15.0:
                    await websocket.send_text('ka')
                    last_sent = now
            await asyncio.sleep(0.05)
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
