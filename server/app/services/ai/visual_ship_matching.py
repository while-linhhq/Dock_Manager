from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ShipMatchCandidate:
    ship_id: str
    aggregated_score: float
    hit_count: int
    point_ids: list[str]
    filenames: list[str]


def _ship_id_from_hit(hit: dict[str, Any]) -> str:
    payload = hit.get('payload') or {}
    return str(payload.get('ship_id') or payload.get('ship_code') or '').strip().upper()


def aggregate_visual_hits(
    hits: list[dict[str, Any]],
    *,
    top_m_for_mean: int = 3,
) -> list[ShipMatchCandidate]:
    """Group Qdrant hits by ship_id; score = mean of top-m point scores per ship."""
    if not hits:
        return []

    grouped: dict[str, list[tuple[float, str, str]]] = {}
    for hit in hits:
        ship_id = _ship_id_from_hit(hit)
        if not ship_id:
            continue
        score = float(hit.get('score') or 0.0)
        point_id = str(hit.get('id') or '')
        payload = hit.get('payload') or {}
        filename = str(payload.get('filename') or '')
        grouped.setdefault(ship_id, []).append((score, point_id, filename))

    ranked: list[ShipMatchCandidate] = []
    top_m = max(1, int(top_m_for_mean))
    for ship_id, entries in grouped.items():
        entries.sort(key=lambda item: item[0], reverse=True)
        top_scores = [score for score, _, _ in entries[:top_m]]
        aggregated = sum(top_scores) / len(top_scores)
        ranked.append(
            ShipMatchCandidate(
                ship_id=ship_id,
                aggregated_score=aggregated,
                hit_count=len(entries),
                point_ids=[point_id for _, point_id, _ in entries[:top_m]],
                filenames=[name for _, _, name in entries[:top_m] if name],
            )
        )

    ranked.sort(key=lambda item: item.aggregated_score, reverse=True)
    return ranked


@dataclass(frozen=True)
class VisualMatchDecision:
    accepted: bool
    ship_id: str | None
    confidence: float
    source: str
    best: ShipMatchCandidate | None
    ranked_ships: list[ShipMatchCandidate]
    margin: float


def resolve_visual_match(
    hits: list[dict[str, Any]],
    *,
    match_threshold: float,
    margin_threshold: float,
    consensus_count: int = 2,
    top_m_for_mean: int = 3,
    ocr_hint: str | None = None,
) -> VisualMatchDecision:
    ranked = aggregate_visual_hits(hits, top_m_for_mean=top_m_for_mean)
    if not ranked:
        normalized_ocr = ocr_hint.strip().upper() if ocr_hint else None
        return VisualMatchDecision(
            accepted=bool(normalized_ocr),
            ship_id=normalized_ocr,
            confidence=0.0,
            source='ocr-hint' if normalized_ocr else 'unknown',
            best=None,
            ranked_ships=[],
            margin=0.0,
        )

    best = ranked[0]
    second_score = ranked[1].aggregated_score if len(ranked) > 1 else 0.0
    margin = best.aggregated_score - second_score
    normalized_ocr = ocr_hint.strip().upper() if ocr_hint else None

    if normalized_ocr and best.ship_id == normalized_ocr:
        boosted = min(1.0, best.aggregated_score + 0.05)
        return VisualMatchDecision(
            accepted=True,
            ship_id=best.ship_id,
            confidence=boosted,
            source='fused-ocr-visual',
            best=best,
            ranked_ships=ranked,
            margin=margin,
        )

    accepted = (
        best.aggregated_score >= float(match_threshold)
        and margin >= float(margin_threshold)
        and best.hit_count >= max(1, int(consensus_count))
    )
    if accepted:
        return VisualMatchDecision(
            accepted=True,
            ship_id=best.ship_id,
            confidence=best.aggregated_score,
            source='visual',
            best=best,
            ranked_ships=ranked,
            margin=margin,
        )

    return VisualMatchDecision(
        accepted=False,
        ship_id=normalized_ocr,
        confidence=best.aggregated_score,
        source='ocr-hint' if normalized_ocr else 'unknown',
        best=best,
        ranked_ships=ranked,
        margin=margin,
    )
