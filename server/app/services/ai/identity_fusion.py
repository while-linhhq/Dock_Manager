from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.services.ai.visual_ship_matching import resolve_visual_match


@dataclass(frozen=True)
class IdentityFusionResult:
    ship_id: str | None
    confidence: float
    source: str
    top_k: list[dict]
    accepted: bool


class IdentityFusion:
    def __init__(
        self,
        *,
        match_threshold: float,
        no_ocr_match_threshold: float,
        conflict_threshold: float = 0.96,
        catalog_is_known: Callable[[str], bool] | None = None,
    ) -> None:
        self._match_threshold = float(match_threshold)
        self._no_ocr_match_threshold = float(no_ocr_match_threshold)
        self._conflict_threshold = float(conflict_threshold)
        self._catalog_is_known = catalog_is_known

    def set_catalog_is_known(self, catalog_is_known: Callable[[str], bool] | None) -> None:
        self._catalog_is_known = catalog_is_known

    def fuse(
        self,
        *,
        visual_top_k: list[dict],
        ocr_hint: str | None = None,
    ) -> IdentityFusionResult:
        decision = resolve_visual_match(
            visual_top_k,
            match_threshold=self._match_threshold,
            no_ocr_threshold=self._no_ocr_match_threshold,
            conflict_threshold=self._conflict_threshold,
            ocr_hint=ocr_hint,
            catalog_is_known=self._catalog_is_known,
        )
        ship_id = decision.ship_id if decision.accepted and decision.ship_id else None
        return IdentityFusionResult(
            ship_id=ship_id,
            confidence=decision.confidence,
            source=decision.source,
            top_k=visual_top_k,
            accepted=decision.accepted,
        )
