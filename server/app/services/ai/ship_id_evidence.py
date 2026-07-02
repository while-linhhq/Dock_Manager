from __future__ import annotations

from dataclasses import dataclass, field

from app.services.ship_id_utils import is_unknown_ship_id


@dataclass(frozen=True)
class ShipIdEvidenceConfig:
    visual_match_threshold: float
    visual_no_ocr_match_threshold: float
    visual_conflict_threshold: float
    ocr_confidence_threshold: float = 0.0


@dataclass(frozen=True)
class EvidenceStats:
    ship_id: str
    count: int
    total_score: float
    avg_score: float
    margin: float


@dataclass(frozen=True)
class ShipIdDecision:
    ship_id: str | None
    state: str
    source: str
    ocr: EvidenceStats | None = None
    embedding: EvidenceStats | None = None


@dataclass
class EvidencePool:
    votes: dict[str, list[float]] = field(default_factory=dict)

    def add(self, ship_id: str, score: float) -> None:
        normalized = _normalize_ship_id(ship_id)
        if normalized is None:
            return
        value = max(0.0, float(score))
        if value <= 0.0:
            return
        self.votes.setdefault(normalized, []).append(value)

    def winner(self) -> EvidenceStats | None:
        if not self.votes:
            return None
        totals = {
            ship_id: sum(scores)
            for ship_id, scores in self.votes.items()
            if scores
        }
        if not totals:
            return None
        ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
        ship_id, total = ranked[0]
        second_total = ranked[1][1] if len(ranked) > 1 else 0.0
        count = len(self.votes[ship_id])
        return EvidenceStats(
            ship_id=ship_id,
            count=count,
            total_score=float(total),
            avg_score=float(total) / max(1, count),
            margin=float(total) - float(second_total),
        )


def _normalize_ship_id(ship_id: str | None) -> str | None:
    if not ship_id:
        return None
    normalized = str(ship_id).strip().upper()
    if not normalized or is_unknown_ship_id(normalized):
        return None
    return normalized


def _ocr_is_valid(stats: EvidenceStats | None, *, config: ShipIdEvidenceConfig) -> bool:
    if stats is None:
        return False
    return stats.total_score >= float(config.ocr_confidence_threshold)


def _embedding_is_valid(
    stats: EvidenceStats | None,
    *,
    has_valid_ocr: bool,
    config: ShipIdEvidenceConfig,
) -> bool:
    if stats is None:
        return False
    threshold = (
        float(config.visual_match_threshold)
        if has_valid_ocr
        else float(config.visual_no_ocr_match_threshold)
    )
    return stats.avg_score >= threshold


@dataclass
class ShipIdEvidence:
    ocr_pool: EvidencePool = field(default_factory=EvidencePool)
    embedding_pool: EvidencePool = field(default_factory=EvidencePool)

    def add_ocr(self, ship_id: str, confidence: float, *, now: float | None = None) -> None:
        self.ocr_pool.add(ship_id, confidence)

    def add_embedding(self, ship_id: str, score: float, *, now: float | None = None) -> None:
        self.embedding_pool.add(ship_id, score)

    def resolve(self, config: ShipIdEvidenceConfig) -> ShipIdDecision:
        ocr = self.ocr_pool.winner()
        embedding = self.embedding_pool.winner()
        ocr_valid = _ocr_is_valid(ocr, config=config)
        embedding_valid = _embedding_is_valid(
            embedding,
            has_valid_ocr=ocr_valid,
            config=config,
        )

        if ocr_valid and embedding_valid:
            if ocr is not None and embedding is not None and ocr.ship_id == embedding.ship_id:
                return ShipIdDecision(ocr.ship_id, 'final', 'consensus', ocr, embedding)
            if embedding is not None and embedding.avg_score >= float(config.visual_conflict_threshold):
                return ShipIdDecision(embedding.ship_id, 'final', 'embedding', ocr, embedding)
            if ocr is not None and ocr.count >= 2:
                return ShipIdDecision(ocr.ship_id, 'final', 'ocr', ocr, embedding)
            if embedding is not None:
                return ShipIdDecision(embedding.ship_id, 'final', 'embedding', ocr, embedding)

        if ocr_valid and ocr is not None:
            return ShipIdDecision(ocr.ship_id, 'final', 'ocr', ocr, embedding)

        if embedding_valid and embedding is not None:
            return ShipIdDecision(embedding.ship_id, 'final', 'embedding', ocr, embedding)

        return ShipIdDecision(None, 'none', 'none', ocr, embedding)
