from app.services.ai.visual_ship_matching import aggregate_visual_hits, resolve_visual_match


def test_aggregate_groups_by_ship_id():
    hits = [
        {'id': 'a1', 'score': 0.9, 'payload': {'ship_id': 'BD-0077'}},
        {'id': 'a2', 'score': 0.85, 'payload': {'ship_id': 'BD-0077'}},
        {'id': 'b1', 'score': 0.8, 'payload': {'ship_id': 'SG-7082'}},
    ]
    ranked = aggregate_visual_hits(hits, top_m_for_mean=2)
    assert ranked[0].ship_id == 'BD-0077'
    assert ranked[0].hit_count == 2
    assert ranked[0].aggregated_score > ranked[1].aggregated_score


def test_resolve_accepts_on_match_threshold_only():
    hits_ok = [
        {'id': 'a1', 'score': 0.82, 'payload': {'ship_id': 'BD-0077'}},
        {'id': 'b1', 'score': 0.68, 'payload': {'ship_id': 'SG-7082'}},
    ]
    decision_ok = resolve_visual_match(hits_ok, match_threshold=0.55)
    assert decision_ok.accepted is True
    assert decision_ok.ship_id == 'BD-0077'

    hits_low = [
        {'id': 'a1', 'score': 0.5, 'payload': {'ship_id': 'BD-0077'}},
    ]
    decision_low = resolve_visual_match(hits_low, match_threshold=0.55)
    assert decision_low.accepted is False
    assert decision_low.ship_id is None


def test_resolve_ocr_hint_takes_priority():
    hits = [
        {'id': 'a1', 'score': 0.9, 'payload': {'ship_id': 'SG-7082'}},
    ]
    decision = resolve_visual_match(hits, match_threshold=0.55, ocr_hint='BD-0077')
    assert decision.ship_id == 'BD-0077'
    assert decision.source == 'ocr-hint'

    fused = resolve_visual_match(hits, match_threshold=0.55, ocr_hint='SG-7082')
    assert fused.accepted is True
    assert fused.source == 'fused-ocr-visual'
