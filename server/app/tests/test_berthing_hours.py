from datetime import datetime, timezone

from app.services.detection_invoice_service import resolve_berth_window


def test_prefers_berth_in_out():
    s = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    bi = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    bo = datetime(2026, 1, 1, 11, tzinfo=timezone.utc)
    assert resolve_berth_window(s, e, bi, bo) == (bi, bo)


def test_falls_back_to_start_end():
    s = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert resolve_berth_window(s, e, None, None) == (s, e)
