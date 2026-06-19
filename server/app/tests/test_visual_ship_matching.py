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


def test_resolve_requires_consensus_and_margin():
    hits = [
        {'id': 'a1', 'score': 0.7, 'payload': {'ship_id': 'BD-0077'}},
        {'id': 'b1', 'score': 0.68, 'payload': {'ship_id': 'SG-7082'}},
    ]
    decision = resolve_visual_match(
        hits,
        match_threshold=0.55,
        margin_threshold=0.08,
        consensus_count=2,
    )
    assert decision.accepted is False

    hits_ok = [
        {'id': 'a1', 'score': 0.82, 'payload': {'ship_id': 'BD-0077'}},
        {'id': 'a2', 'score': 0.8, 'payload': {'ship_id': 'BD-0077'}},
        {'id': 'b1', 'score': 0.5, 'payload': {'ship_id': 'SG-7082'}},
    ]
    decision_ok = resolve_visual_match(
        hits_ok,
        match_threshold=0.55,
        margin_threshold=0.08,
        consensus_count=2,
    )
    assert decision_ok.accepted is True
    assert decision_ok.ship_id == 'BD-0077'
