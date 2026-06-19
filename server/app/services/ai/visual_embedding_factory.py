from __future__ import annotations

import logging
from threading import Lock

from app.core.config import settings
from app.services.ai.visual_embedding_extractor import VisualEmbeddingExtractor

_log = logging.getLogger(__name__)

_extractor: VisualEmbeddingExtractor | None = None
_extractor_lock = Lock()


def get_visual_embedding_extractor() -> VisualEmbeddingExtractor:
    """Process-wide singleton so enroll/search/pipeline share one embedding model."""
    global _extractor
    with _extractor_lock:
        if _extractor is None:
            _extractor = VisualEmbeddingExtractor(
                model_path=settings.VISUAL_MODEL_PATH or None,
                backbone=settings.VISUAL_BACKBONE,
                device=settings.VISUAL_DEVICE or settings.DEVICE,
                image_size=settings.VISUAL_IMAGE_SIZE,
                embedding_dim=settings.VISUAL_EMBEDDING_DIM,
            )
            _log.info(
                'Visual embedding extractor ready backend=%s dim=%s',
                _extractor.backend,
                _extractor.vector_dim,
            )
        return _extractor


def reset_visual_embedding_extractor_for_tests() -> None:
    global _extractor
    with _extractor_lock:
        _extractor = None
