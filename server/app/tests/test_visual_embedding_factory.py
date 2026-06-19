import numpy as np

from app.services.ai.visual_embedding_extractor import VisualEmbeddingExtractor
from app.services.ai.visual_embedding_factory import (
    get_visual_embedding_extractor,
    reset_visual_embedding_extractor_for_tests,
)


def test_shared_extractor_same_embedding():
    reset_visual_embedding_extractor_for_tests()
    img = np.random.randint(0, 255, (320, 480, 3), dtype=np.uint8)
    e1 = get_visual_embedding_extractor()
    e2 = get_visual_embedding_extractor()
    assert e1 is e2
    v1 = e1.extract(img)
    v2 = e2.extract(img)
    assert v1 is not None and v2 is not None
    assert float(np.dot(v1, v2)) > 0.999


def test_deterministic_projection_across_instances():
    reset_visual_embedding_extractor_for_tests()
    from app.core.config import settings

    img = np.random.randint(0, 255, (320, 480, 3), dtype=np.uint8)
    first = get_visual_embedding_extractor()
    v_first = first.extract(img)
    reset_visual_embedding_extractor_for_tests()
    second = get_visual_embedding_extractor()
    v_second = second.extract(img)
    assert v_first is not None and v_second is not None
    assert float(np.dot(v_first, v_second)) > 0.999
