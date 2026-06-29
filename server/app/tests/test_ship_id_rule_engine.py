import re

from app.services.ai.ship_id_rule_engine import ShipIdRuleEngine


def _make_engine(patterns=None, blacklist=None, convert_map=None) -> ShipIdRuleEngine:
    engine = ShipIdRuleEngine()
    engine._compiled_patterns = []
    if patterns:
        for p in patterns:
            try:
                engine._compiled_patterns.append({
                    'pattern': re.compile(p['pattern']),
                    'name': p.get('name', ''),
                })
            except re.error:
                pass
    engine._blacklist = set(blacklist or [])
    engine._convert_map = dict(convert_map or {})
    return engine


def test_apply_pass_through():
    engine = _make_engine()
    assert engine.apply('SG-1234') == 'SG-1234'


def test_apply_blacklisted_returns_none():
    engine = _make_engine(blacklist=['SG-1234'])
    assert engine.apply('SG-1234') is None


def test_apply_convert_map():
    engine = _make_engine(convert_map={'SC-4567': 'SG-4567'})
    assert engine.apply('SC-4567') == 'SG-4567'


def test_apply_blacklist_beats_convert_map():
    engine = _make_engine(blacklist=['SC-4567'], convert_map={'SC-4567': 'SG-4567'})
    assert engine.apply('SC-4567') is None


def test_extract_ship_ids_standard_pattern():
    engine = _make_engine(patterns=[{'pattern': r'([A-Z50]{2})[-\s]?(\d{4})'}])
    results = engine.extract_ship_ids('SG-1234')
    assert len(results) == 1
    assert results[0]['id'] == 'SG-1234'


def test_extract_normalizes_5_to_s():
    engine = _make_engine(patterns=[{'pattern': r'([A-Z50]{2})[-\s]?(\d{4})'}])
    results = engine.extract_ship_ids('5G-1234')
    assert results[0]['id'] == 'SG-1234'


def test_extract_filters_blacklisted():
    engine = _make_engine(
        patterns=[{'pattern': r'([A-Z50]{2})[-\s]?(\d{4})'}],
        blacklist=['SG-1234'],
    )
    assert engine.extract_ship_ids('SG-1234') == []


def test_extract_applies_convert_map():
    engine = _make_engine(
        patterns=[{'pattern': r'([A-Z50]{2})[-\s]?(\d{4})'}],
        convert_map={'SC-4567': 'SG-4567'},
    )
    results = engine.extract_ship_ids('SC-4567')
    assert results[0]['id'] == 'SG-4567'


def test_extract_multiple_patterns_priority():
    engine = _make_engine(patterns=[
        {'pattern': r'([A-Z50]{2})[-\s]?(\d{4,5})'},
    ])
    results = engine.extract_ship_ids('SG-12345')
    assert results[0]['id'] == 'SG-12345'


def test_no_patterns_falls_back_to_default():
    engine = ShipIdRuleEngine()
    engine._compiled_patterns = []
    engine._blacklist = set()
    engine._convert_map = {}
    results = engine.extract_ship_ids('SG-1234')
    assert len(results) == 1
    assert results[0]['id'] == 'SG-1234'
