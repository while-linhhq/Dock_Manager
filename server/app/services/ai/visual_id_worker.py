from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from app.services.ai.boat_tracker import BoatTracker
from app.services.ai.identity_fusion import IdentityFusion
from app.services.ai.runtime_cache_redis import RuntimeCacheRedis
from app.services.ai.vector_store_qdrant import QdrantVectorStore
from app.services.ai.visual_embedding_extractor import VisualEmbeddingExtractor
from app.utils.ai.pipeline_utils import clamp_box

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VisualQueueItem:
    frame: np.ndarray
    boxes_list: list[tuple[str, np.ndarray]]
    boat_tracker: BoatTracker
    camera_id: int
    ocr_cache: dict
    ocr_lock: Any
    on_visual_result: Callable[[str, str, float, str, list[dict]], None] | None = None


class VisualIdWorkerThread(threading.Thread):
    def __init__(
        self,
        *,
        worker_name: str,
        visual_queue: queue.Queue,
        extractor: VisualEmbeddingExtractor,
        vector_store: QdrantVectorStore | None,
        runtime_cache: RuntimeCacheRedis | None,
        identity_fusion: IdentityFusion,
        stop_event: threading.Event,
        top_k: int = 5,
        min_crop_area: int = 4096,
        score_threshold: float = 0.72,
    ) -> None:
        super().__init__(daemon=True, name=worker_name)
        self._queue = visual_queue
        self._extractor = extractor
        self._vector_store = vector_store
        self._runtime_cache = runtime_cache
        self._identity_fusion = identity_fusion
        self._stop_event = stop_event
        self._top_k = max(1, int(top_k))
        self._min_crop_area = max(64, int(min_crop_area))
        self._score_threshold = float(score_threshold)

    def run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    item = self._queue.get(timeout=0.8)
                except queue.Empty:
                    continue
                if not isinstance(item, VisualQueueItem):
                    continue

                frame = item.frame
                if frame is None or frame.size == 0:
                    continue
                h, w = frame.shape[:2]
                crops: list[np.ndarray] = []
                refs: list[tuple[str, int, int]] = []

                for track_id, box in item.boxes_list:
                    x1, y1, x2, y2 = clamp_box(box, w, h)
                    width = max(0, x2 - x1)
                    height = max(0, y2 - y1)
                    if width * height < self._min_crop_area:
                        continue
                    crop = frame[y1:y2, x1:x2]
                    if crop.size == 0:
                        continue
                    crops.append(crop)
                    refs.append((str(track_id), width, height))

                embeddings = self._extractor.extract_batch(crops)
                for index, embedding in enumerate(embeddings):
                    if embedding is None:
                        continue
                    track_id, _, _ = refs[index]
                    ocr_hint = None
                    with item.ocr_lock:
                        cache_entry = item.ocr_cache.get(str(track_id))
                        if isinstance(cache_entry, dict):
                            ocr_hint = str(cache_entry.get('text') or '').strip().upper() or None
                    top_k = []
                    if self._vector_store is not None:
                        top_k = self._vector_store.search(
                            embedding=embedding,
                            top_k=self._top_k,
                            score_threshold=self._score_threshold,
                        )
                    result = self._identity_fusion.fuse(visual_top_k=top_k, ocr_hint=ocr_hint)
                    if self._runtime_cache is not None:
                        self._runtime_cache.set_json(
                            key=f'visual-track:{item.camera_id}:{track_id}',
                            value={
                                'ship_id': result.ship_id,
                                'confidence': result.confidence,
                                'source': result.source,
                                'top_k': result.top_k,
                            },
                        )
                    if item.on_visual_result is not None and result.ship_id:
                        item.on_visual_result(
                            track_id,
                            result.ship_id,
                            result.confidence,
                            result.source,
                            result.top_k,
                        )
        except Exception:
            logger.exception('VisualIdWorkerThread crashed')
        finally:
            self._stop_event.set()
