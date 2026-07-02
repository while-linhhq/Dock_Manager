from datetime import datetime, timezone

from decimal import Decimal

from app.services.detection_invoice_service import _berthing_hours, resolve_berth_window


def test_prefers_berth_in_out():
    """Cả berth_in và berth_out đầy đủ, không overlap detection window."""
    s = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    bi = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    bo = datetime(2026, 1, 1, 11, tzinfo=timezone.utc)
    assert resolve_berth_window(s, e, bi, bo) == (bi, bo)


def test_falls_back_to_start_end():
    """Không có berth nào -> fallback start/end."""
    s = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert resolve_berth_window(s, e, None, None) == (s, e)


def test_berth_in_without_berth_out():
    """Chỉ berth_in, thiếu berth_out: dùng (berth_in, end)."""
    s = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    bi = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    result = resolve_berth_window(s, e, bi, None)
    assert result == (bi, e), f"Expected (bi, e), got {result}"


def test_berth_out_without_berth_in():
    """Chỉ berth_out, thiếu berth_in: dùng (start, berth_out)."""
    s = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    bo = datetime(2026, 1, 1, 11, tzinfo=timezone.utc)
    result = resolve_berth_window(s, e, None, bo)
    assert result == (s, bo), f"Expected (s, bo), got {result}"


def test_berth_before_start_overlap():
    """Berth window overlap với detection (bi<start nhưng bo>start):
    vẫn dùng (bi, bo) vì overlap là hợp lệ."""
    s = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bi = datetime(2026, 1, 1, 9, 30, 0, tzinfo=timezone.utc)
    bo = datetime(2026, 1, 1, 11, 30, 0, tzinfo=timezone.utc)
    result = resolve_berth_window(s, e, bi, bo)
    assert result == (bi, bo), f"Expected (bi, bo), got {result}"


def test_berth_after_end_overlap():
    """Berth sau detection (bo>end nhưng bi<end): overlap hợp lệ."""
    s = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bi = datetime(2026, 1, 1, 10, 30, 0, tzinfo=timezone.utc)
    bo = datetime(2026, 1, 1, 12, 30, 0, tzinfo=timezone.utc)
    result = resolve_berth_window(s, e, bi, bo)
    assert result == (bi, bo), f"Expected (bi, bo), got {result}"


def test_berth_out_before_start_disjoint():
    """Bo < start: berth hoàn toàn trước detection -> (None, None)."""
    s = datetime(2026, 1, 1, 12, 31, 6, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, 31, 14, tzinfo=timezone.utc)
    bi = datetime(2026, 1, 1, 11, 59, 32, tzinfo=timezone.utc)
    bo = datetime(2026, 1, 1, 12, 31, 2, tzinfo=timezone.utc)
    result = resolve_berth_window(s, e, bi, bo)
    assert result == (None, None), f"Expected (None, None), got {result}"


def test_berth_in_after_end_disjoint():
    """Bi > end: berth hoàn toàn sau detection -> (None, None)."""
    s = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bi = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
    bo = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
    result = resolve_berth_window(s, e, bi, bo)
    assert result == (None, None), f"Expected (None, None), got {result}"


def test_berth_in_only_after_end():
    """Chỉ bi nhưng bi > end: (None, None)."""
    s = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bi = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
    result = resolve_berth_window(s, e, bi, None)
    assert result == (None, None), f"Expected (None, None), got {result}"


def test_berth_out_only_before_start():
    """Chỉ bo nhưng bo < start: (None, None)."""
    s = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bo = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    result = resolve_berth_window(s, e, None, bo)
    assert result == (None, None), f"Expected (None, None), got {result}"


def test_both_cross_disjoint():
    """bi < start, bo < start (hoàn toàn trước): (None, None)."""
    s = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bi = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    bo = datetime(2026, 1, 1, 9, 30, 0, tzinfo=timezone.utc)
    result = resolve_berth_window(s, e, bi, bo)
    assert result == (None, None), f"Expected (None, None), got {result}"


def test_berth_invalid_reversed():
    """Berth_in > berth_out (dữ liệu lỗi): (None, None)."""
    s = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bi = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    bo = datetime(2026, 1, 1, 10, 30, 0, tzinfo=timezone.utc)
    result = resolve_berth_window(s, e, bi, bo)
    assert result == (None, None), f"Expected (None, None), got {result}"


def test_missing_window_charges_zero_hours():
    """Không đủ start/end thì không tự cộng tối thiểu; không làm tròn tiền."""
    assert _berthing_hours(None, None) == Decimal('0')


def test_seconds_are_not_rounded_up_to_minimum_centihour():
    s = datetime(2026, 1, 1, 14, 3, 4, tzinfo=timezone.utc)
    e = datetime(2026, 1, 1, 14, 3, 16, tzinfo=timezone.utc)
    assert _berthing_hours(s, e) == Decimal('12') / Decimal('3600')
