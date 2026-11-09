"""Unit tests for the license feature registry + Keygate feature normalization."""
from app.core.license.features import feature_bool, feature_int, max_cameras, normalize_features

def test_int_feature_string_is_parsed():
    assert normalize_features({'max_cameras': '12'}) == {'max_cameras': 12}

def test_missing_int_feature_falls_back_to_zero():
    assert max_cameras({}) == 0
    assert feature_int({'max_cameras': 'abc'}, 'max_cameras') == 0

def test_bool_feature_stays_bool():
    assert feature_bool({'module_ai_lab': True}, 'module_ai_lab') is True
    assert feature_bool({'module_ai_lab': 'true'}, 'module_ai_lab') is True
    assert feature_bool({}, 'module_ai_lab') is False

def test_unknown_feature_is_preserved_but_not_coerced():
    out = normalize_features({'custom_flag': 'yes'})
    assert out['custom_flag'] == 'yes'
