import re

from app.services.ai.ship_id_rule_engine import ShipIdRuleEngine


def _make_engine(patterns=None, blacklist=None, convert_map=None, prefix_convert=None) -> ShipIdRuleEngine:
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
    engine._prefix_convert_map = dict(prefix_convert or {})
    return engine


# Patterns matching the production DB state (5-digit tried first, both boundaried).
_PROD_PATTERNS = [
    {'pattern': r'([A-Z]{2})[-\s]?(\d{5})(?!\d)'},
    {'pattern': r'([A-Z]{2})[-\s]?(\d{4})(?!\d)'},
]


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
    engine._prefix_convert_map = {}
    results = engine.extract_ship_ids('SG-1234')
    assert len(results) == 1
    assert results[0]['id'] == 'SG-1234'


# ── Prefix convert map ─────────────────────────────────────────────────────


def test_apply_prefix_convert():
    engine = _make_engine(prefix_convert={'SC': 'SG'})
    assert engine.apply('SC-8168') == 'SG-8168'


def test_apply_prefix_convert_preserves_5_digit_suffix():
    engine = _make_engine(prefix_convert={'SC': 'SG'})
    assert engine.apply('SC-81682') == 'SG-81682'


def test_exact_convert_map_beats_prefix_convert():
    # SC-8168 has an exact rule → SG-9999; prefix rule SC->SG must NOT also fire.
    engine = _make_engine(
        convert_map={'SC-8168': 'SG-9999'},
        prefix_convert={'SC': 'SG'},
    )
    assert engine.apply('SC-8168') == 'SG-9999'


def test_blacklist_beats_prefix_convert():
    engine = _make_engine(blacklist=['SC-8168'], prefix_convert={'SC': 'SG'})
    assert engine.apply('SC-8168') is None


def test_prefix_convert_no_match_passes_through():
    engine = _make_engine(prefix_convert={'SC': 'SG'})
    assert engine.apply('BD-0077') == 'BD-0077'


def test_extract_applies_prefix_convert():
    engine = _make_engine(patterns=_PROD_PATTERNS, prefix_convert={'SC': 'SG'})
    results = engine.extract_ship_ids('SC-8168')
    assert results[0]['id'] == 'SG-8168'


# ── Tonnage-token boundary (the '24K' swallow bug) ─────────────────────────


def test_tonnage_token_not_swallowed_with_space():
    engine = _make_engine(patterns=_PROD_PATTERNS)
    results = engine.extract_ship_ids('SG-8188 24K')
    assert [r['id'] for r in results] == ['SG-8188']


def test_tonnage_token_not_swallowed_prefix_spaced():
    engine = _make_engine(patterns=_PROD_PATTERNS)
    results = engine.extract_ship_ids('SG 8188 24K')
    assert [r['id'] for r in results] == ['SG-8188']


def test_real_5_digit_id_preserved():
    engine = _make_engine(patterns=_PROD_PATTERNS)
    results = engine.extract_ship_ids('SG-10447')
    assert [r['id'] for r in results] == ['SG-10447']


def test_5_digit_with_tonnage_keeps_5_digits():
    engine = _make_engine(patterns=_PROD_PATTERNS)
    results = engine.extract_ship_ids('SG-81682 30K')
    assert [r['id'] for r in results] == ['SG-81682']


def test_combined_prefix_convert_and_boundary():
    engine = _make_engine(patterns=_PROD_PATTERNS, prefix_convert={'SC': 'SG'})
    results = engine.extract_ship_ids('SC-8188 24K')
    assert [r['id'] for r in results] == ['SG-8188']
