from __future__ import annotations

from dataclasses import dataclass

from app.services.ai.visual_ship_matching import resolve_visual_match


@dataclass(frozen=True)
class IdentityFusionResult:
    ship_id: str | None
    confidence: float
    source: str
    top_k: list[dict]


class IdentityFusion:
    def __init__(self, *, match_threshold: float) -> None:
        self._match_threshold = float(match_threshold)

    def fuse(
        self,
        *,
        visual_top_k: list[dict],
        ocr_hint: str | None = None,
    ) -> IdentityFusionResult:
        decision = resolve_visual_match(
            visual_top_k,
            match_threshold=self._match_threshold,
            ocr_hint=ocr_hint,
        )
        if decision.accepted:
            ship_id = decision.ship_id
        elif decision.source == 'ocr-hint':
            ship_id = decision.ship_id
        else:
            ship_id = None
        return IdentityFusionResult(
            ship_id=ship_id,
            confidence=decision.confidence,
            source=decision.source,
            top_k=visual_top_k,
        )
