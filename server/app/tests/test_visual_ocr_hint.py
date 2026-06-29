from unittest.mock import MagicMock

from app.services.ai.boat_tracker import BoatTracker
from app.utils.ai.pipeline_utils import (
    ocr_cache_key_track,
    parse_ocr_ship_id_from_label,
    resolve_ocr_hint_for_visual,
)


def test_parse_ocr_ship_id_from_label():
    assert parse_ocr_ship_id_from_label('BS-1234 (0.92)') == 'BS-1234'
    assert parse_ocr_ship_id_from_label('bs-1234 (voted)') == 'BS-1234'
    assert parse_ocr_ship_id_from_label('') is None


def test_resolve_ocr_hint_uses_camera_scoped_cache_key():
    tracker = MagicMock(spec=BoatTracker)
    tracker.get_voted_ship_id.return_value = None
    ocr_cache = {
        ocr_cache_key_track('trk_1', 7): {
            'text': 'SG-7082 (voted)',
            'ocr_ship_id': 'SG-7082',
        },
    }
    lock = MagicMock()
    lock.__enter__ = MagicMock(return_value=None)
    lock.__exit__ = MagicMock(return_value=False)

    hint = resolve_ocr_hint_for_visual(
        boat_tracker=tracker,
        track_id='trk_1',
        ocr_cache=ocr_cache,
        ocr_lock=lock,
        camera_id=7,
    )
    assert hint == 'SG-7082'


def test_resolve_ocr_hint_prefers_tracker_vote():
    tracker = MagicMock(spec=BoatTracker)
    tracker.get_voted_ship_id.return_value = 'BD-0077'
    ocr_cache = {
        ocr_cache_key_track('trk_1', 7): {
            'text': 'SG-7082 (voted)',
            'ocr_ship_id': 'SG-7082',
        },
    }
    lock = MagicMock()
    lock.__enter__ = MagicMock(return_value=None)
    lock.__exit__ = MagicMock(return_value=False)

    hint = resolve_ocr_hint_for_visual(
        boat_tracker=tracker,
        track_id='trk_1',
        ocr_cache=ocr_cache,
        ocr_lock=lock,
        camera_id=7,
    )
    assert hint == 'BD-0077'


def test_bare_track_id_cache_key_misses_multi_camera_entry():
    ocr_cache = {
        ocr_cache_key_track('trk_1', 7): {'ocr_ship_id': 'SG-7082'},
    }
    lock = MagicMock()
    lock.__enter__ = MagicMock(return_value=None)
    lock.__exit__ = MagicMock(return_value=False)

    hint = resolve_ocr_hint_for_visual(
        boat_tracker=None,
        track_id='trk_1',
        ocr_cache=ocr_cache,
        ocr_lock=lock,
        camera_id=7,
    )
    assert hint == 'SG-7082'

    # Legacy broken lookup path would miss this entry.
    assert ocr_cache.get('trk_1') is None


def test_resolve_ocr_hint_drops_unknown_ship_id_with_catalog_gate():
    tracker = MagicMock(spec=BoatTracker)
    tracker.get_voted_ship_id.return_value = 'OO-7215'
    ocr_cache = {}
    lock = MagicMock()
    lock.__enter__ = MagicMock(return_value=None)
    lock.__exit__ = MagicMock(return_value=False)

    hint = resolve_ocr_hint_for_visual(
        boat_tracker=tracker,
        track_id='trk_1',
        ocr_cache=ocr_cache,
        ocr_lock=lock,
        camera_id=7,
        catalog_is_known=lambda sid: sid == 'SG-8212',
    )
    assert hint is None
