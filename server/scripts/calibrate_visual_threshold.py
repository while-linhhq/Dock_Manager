#!/usr/bin/env python3
"""
Leave-one-out calibration for vessel visual embeddings.

Usage (from server/):
  python scripts/calibrate_visual_threshold.py
  python scripts/calibrate_visual_threshold.py --ship-id BD-0077
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.core.config import settings
from app.services.ai.vector_store_qdrant import QdrantVectorStore
from app.services.ai.visual_ship_matching import aggregate_visual_hits

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
_log = logging.getLogger('calibrate_visual_threshold')


def calibrate(*, ship_filter: str | None = None) -> None:
    store = QdrantVectorStore(
        host=settings.QDRANT_HOST,
        port=int(settings.QDRANT_PORT),
        api_key=settings.QDRANT_API_KEY or None,
        collection_name=settings.QDRANT_COLLECTION,
        vector_size=int(settings.QDRANT_VECTOR_SIZE),
        distance=settings.QDRANT_DISTANCE,
    )
    if not store.healthcheck():
        raise RuntimeError('Qdrant unavailable')

    offset = None
    points: list[dict] = []
    while True:
        batch, offset = store.scroll_all(limit=256, offset=offset, with_vectors=True)
        points.extend(batch)
        if offset is None:
            break

    if ship_filter:
        points = [
            p
            for p in points
            if str((p.get('payload') or {}).get('ship_id') or '').upper() == ship_filter.upper()
        ]

    if len(points) < 2:
        _log.warning('Need at least 2 enrolled points; found %s', len(points))
        return

    same_scores: list[float] = []
    cross_scores: list[float] = []

    for index, query in enumerate(points):
        query_id = str(query.get('id'))
        query_ship = str((query.get('payload') or {}).get('ship_id') or '').upper()
        vector = query.get('vector')
        if vector is None:
            continue
        embedding = np.asarray(vector, dtype=np.float32).reshape(-1)
        hits = store.search(embedding=embedding, top_k=settings.VISUAL_TOP_K, score_threshold=None)
        hits = [hit for hit in hits if str(hit.get('id')) != query_id]
        ranked = aggregate_visual_hits(hits)
        if not ranked:
            continue
        best = ranked[0]
        if best.ship_id == query_ship:
            same_scores.append(best.aggregated_score)
            second_distinct = next(
                (candidate.aggregated_score for candidate in ranked if candidate.ship_id != query_ship),
                None,
            )
            if second_distinct is not None:
                cross_scores.append(second_distinct)
        else:
            cross_scores.append(best.aggregated_score)

    def _stats(values: list[float]) -> str:
        if not values:
            return 'n=0'
        arr = np.asarray(values, dtype=np.float32)
        return f'n={len(values)} min={arr.min():.3f} p50={np.median(arr):.3f} max={arr.max():.3f}'

    _log.info('Same-ship aggregated scores: %s', _stats(same_scores))
    _log.info('Cross-ship aggregated scores: %s', _stats(cross_scores))

    if same_scores and cross_scores:
        cross_p95 = float(np.percentile(np.asarray(cross_scores), 95))
        same_p05 = float(np.percentile(np.asarray(same_scores), 5))
        suggested = max(cross_p95 + 0.02, (cross_p95 + same_p05) / 2)
        suggested = min(0.95, max(0.35, suggested))
        _log.info('Suggested VISUAL_MATCH_THRESHOLD ~= %.3f', suggested)

    by_ship: dict[str, list[float]] = defaultdict(list)
    for score in same_scores:
        by_ship['same'].append(score)
    for score in cross_scores:
        by_ship['cross'].append(score)
    _log.info('Summary buckets: %s', {key: len(vals) for key, vals in by_ship.items()})


def main() -> None:
    parser = argparse.ArgumentParser(description='Calibrate visual match threshold (leave-one-out)')
    parser.add_argument('--ship-id', default=None, help='Optional ship_id filter')
    args = parser.parse_args()
    calibrate(ship_filter=args.ship_id)


if __name__ == '__main__':
    main()
