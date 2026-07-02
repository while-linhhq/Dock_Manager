from app.services.ai.ship_id_evidence import ShipIdEvidence, ShipIdEvidenceConfig


CFG = ShipIdEvidenceConfig(
    ocr_confidence_threshold=0.0,
    visual_match_threshold=0.55,
    visual_no_ocr_match_threshold=0.55,
    visual_conflict_threshold=0.96,
)


def test_ocr_winner_is_final_when_has_any_known_vote():
    evidence = ShipIdEvidence()
    evidence.add_ocr('BD-0001', 0.70, now=1.0)

    decision = evidence.resolve(CFG)

    assert decision.state == 'final'
    assert decision.ship_id == 'BD-0001'
    assert decision.source == 'ocr'


def test_embedding_pool_uses_visual_no_ocr_threshold_without_ocr():
    evidence = ShipIdEvidence()
    evidence.add_embedding('BD-0002', 0.56, now=1.0)

    decision = evidence.resolve(CFG)

    assert decision.state == 'final'
    assert decision.ship_id == 'BD-0002'
    assert decision.source == 'embedding'


def test_embedding_below_visual_no_ocr_threshold_is_not_final():
    evidence = ShipIdEvidence()
    evidence.add_embedding('BD-0002', 0.54, now=1.0)

    decision = evidence.resolve(CFG)

    assert decision.state == 'none'
    assert decision.ship_id is None


def test_ocr_and_embedding_agree_is_consensus():
    evidence = ShipIdEvidence()
    evidence.add_ocr('BD-0001', 0.70, now=1.0)
    evidence.add_embedding('BD-0001', 0.60, now=2.0)

    decision = evidence.resolve(CFG)

    assert decision.state == 'final'
    assert decision.ship_id == 'BD-0001'
    assert decision.source == 'consensus'


def test_weak_ocr_conflict_loses_to_valid_embedding_pool():
    evidence = ShipIdEvidence()
    evidence.add_ocr('BD-WRONG', 0.90, now=1.0)
    evidence.add_embedding('BD-0002', 0.80, now=2.0)
    evidence.add_embedding('BD-0002', 0.82, now=3.0)
    evidence.add_embedding('BD-0002', 0.81, now=4.0)

    decision = evidence.resolve(CFG)

    assert decision.state == 'final'
    assert decision.ship_id == 'BD-0002'
    assert decision.source == 'embedding'


def test_strong_ocr_conflict_beats_embedding_below_conflict_threshold():
    evidence = ShipIdEvidence()
    evidence.add_ocr('BD-0001', 0.70, now=1.0)
    evidence.add_ocr('BD-0001', 0.70, now=2.0)
    evidence.add_embedding('BD-9999', 0.80, now=3.0)
    evidence.add_embedding('BD-9999', 0.82, now=4.0)
    evidence.add_embedding('BD-9999', 0.81, now=5.0)

    decision = evidence.resolve(CFG)

    assert decision.state == 'final'
    assert decision.ship_id == 'BD-0001'
    assert decision.source == 'ocr'


def test_embedding_above_conflict_threshold_beats_ocr_conflict():
    evidence = ShipIdEvidence()
    evidence.add_ocr('BD-0001', 0.70, now=1.0)
    evidence.add_ocr('BD-0001', 0.70, now=2.0)
    evidence.add_embedding('BD-9999', 0.97, now=3.0)

    decision = evidence.resolve(CFG)

    assert decision.state == 'final'
    assert decision.ship_id == 'BD-9999'
    assert decision.source == 'embedding'


def test_ocr_below_confidence_threshold_is_invalid():
    cfg = ShipIdEvidenceConfig(
        ocr_confidence_threshold=0.80,
        visual_match_threshold=0.55,
        visual_no_ocr_match_threshold=0.55,
        visual_conflict_threshold=0.96,
    )
    evidence = ShipIdEvidence()
    evidence.add_ocr('BD-0001', 0.70, now=1.0)  # total=0.70 < 0.80

    decision = evidence.resolve(cfg)

    assert decision.state == 'none'
    assert decision.ship_id is None


def test_ocr_at_confidence_threshold_is_valid():
    cfg = ShipIdEvidenceConfig(
        ocr_confidence_threshold=0.70,
        visual_match_threshold=0.55,
        visual_no_ocr_match_threshold=0.55,
        visual_conflict_threshold=0.96,
    )
    evidence = ShipIdEvidence()
    evidence.add_ocr('BD-0001', 0.70, now=1.0)  # total=0.70 >= 0.70

    decision = evidence.resolve(cfg)

    assert decision.state == 'final'
    assert decision.ship_id == 'BD-0001'
    assert decision.source == 'ocr'
