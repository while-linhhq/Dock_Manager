from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.camera_repository import camera_repo
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
            if not camera.is_active:
                raise HTTPException(status_code=400, detail='Selected camera is inactive')
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
