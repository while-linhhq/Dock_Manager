from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.core.config import settings
from app.services.ai.visual_embedding_factory import get_visual_embedding_extractor
from app.services.ai.vector_store_qdrant import QdrantVectorStore
from app.services.ai_lab_service import (
    decode_upload_bgr,
    media_kind_from_name,
    run_detection_lab,
    visual_search_ranked,
)

router = APIRouter()


def _get_visual_extractor():
    return get_visual_embedding_extractor()


def _get_qdrant_store(*, vector_size: int) -> QdrantVectorStore:
    return QdrantVectorStore(
        host=settings.QDRANT_HOST,
        port=int(settings.QDRANT_PORT),
        api_key=settings.QDRANT_API_KEY or None,
        collection_name=settings.QDRANT_COLLECTION,
        vector_size=int(vector_size),
        distance=settings.QDRANT_DISTANCE,
    )


def _resolve_qdrant_vector_size(extractor: VisualEmbeddingExtractor) -> int:
    probe = _get_qdrant_store(vector_size=extractor.vector_dim)
    collection_size = probe.collection_vector_size()
    if collection_size and collection_size > 0:
        return int(collection_size)
    return int(extractor.vector_dim)


@router.post('/detect')
async def lab_detect_media(
    file: UploadFile = File(...),
    frame_stride: int = Form(8),
    max_output_frames: int = Form(48),
    _user=Depends(get_current_user),
):
    filename = str(file.filename or 'upload.bin')
    media_kind = media_kind_from_name(filename)
    if media_kind is None:
        raise HTTPException(
            status_code=400,
            detail='Unsupported file type. Use image (jpg/png/webp) or video (mp4/avi/mov/mkv).',
        )

    suffix = Path(filename).suffix.lower() or ('.jpg' if media_kind == 'image' else '.mp4')
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail='Empty upload')

    max_bytes = 200 * 1024 * 1024 if media_kind == 'video' else 25 * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail='File too large for lab upload')

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = run_detection_lab(
            tmp_path,
            media_kind=media_kind,
            frame_stride=frame_stride,
            max_output_frames=max_output_frames,
        )
        result['filename'] = filename
        return result
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err)) from err
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


@router.post('/visual-search')
async def lab_visual_search(
    file: UploadFile = File(...),
    _user=Depends(get_current_user),
):
    filename = str(file.filename or 'query.jpg')
    if media_kind_from_name(filename) != 'image':
        raise HTTPException(status_code=400, detail='Visual search requires an image upload')

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail='Empty upload')
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail='Image too large (max 25MB)')

    try:
        frame = decode_upload_bgr(content)
        extractor = _get_visual_extractor()
        if extractor.backend == 'unavailable':
            raise HTTPException(status_code=503, detail='Visual embedding model is unavailable')

        vector_size = _resolve_qdrant_vector_size(extractor)
        qdrant = _get_qdrant_store(vector_size=vector_size)
        if not qdrant.healthcheck():
            raise HTTPException(status_code=503, detail='Qdrant is unavailable')

        result = visual_search_ranked(
            frame,
            extractor=extractor,
            qdrant=qdrant,
            top_k=settings.VISUAL_TOP_K,
            match_threshold=settings.VISUAL_MATCH_THRESHOLD,
        )
        return {
            'filename': filename,
            **result,
        }
    except HTTPException:
        raise
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err)) from err
