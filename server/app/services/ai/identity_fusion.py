from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IdentityFusionResult:
    ship_id: str | None
    confidence: float
    source: str
    top_k: list[dict]


class IdentityFusion:
    def __init__(
        self,
        *,
        match_threshold: float,
        margin_threshold: float,
    ) -> None:
        self._match_threshold = float(match_threshold)
        self._margin_threshold = float(margin_threshold)

    def fuse(
        self,
        *,
        visual_top_k: list[dict],
        ocr_hint: str | None = None,
    ) -> IdentityFusionResult:
        if not visual_top_k:
            return IdentityFusionResult(
                ship_id=ocr_hint.strip().upper() if ocr_hint else None,
                confidence=0.0,
                source='ocr-hint' if ocr_hint else 'unknown',
                top_k=[],
            )

        first = visual_top_k[0]
        top_score = float(first.get('score', 0.0))
        second_score = float(visual_top_k[1].get('score', 0.0)) if len(visual_top_k) > 1 else 0.0
        margin = top_score - second_score
        payload = first.get('payload') or {}
        predicted_ship_id = str(payload.get('ship_id') or payload.get('ship_code') or '').strip().upper()

        if ocr_hint and predicted_ship_id and ocr_hint.strip().upper() == predicted_ship_id:
            boosted = min(1.0, top_score + 0.05)
            return IdentityFusionResult(
                ship_id=predicted_ship_id,
                confidence=boosted,
                source='fused-ocr-visual',
                top_k=visual_top_k,
            )

        if top_score >= self._match_threshold and margin >= self._margin_threshold and predicted_ship_id:
            return IdentityFusionResult(
                ship_id=predicted_ship_id,
                confidence=top_score,
                source='visual',
                top_k=visual_top_k,
            )

        return IdentityFusionResult(
            ship_id=ocr_hint.strip().upper() if ocr_hint else None,
            confidence=top_score,
            source='unknown',
            top_k=visual_top_k,
        )
