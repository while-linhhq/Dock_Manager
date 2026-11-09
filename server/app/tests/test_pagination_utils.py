from fastapi import Response

from app.utils.pagination import TOTAL_COUNT_HEADER, resolve_page, set_total_header


def test_limit_over_max_is_clamped() -> None:
    assert resolve_page(0, 9999) == (0, 200)


def test_limit_zero_or_negative_becomes_one() -> None:
    assert resolve_page(0, 0) == (0, 1)
    assert resolve_page(0, -5) == (0, 1)


def test_skip_negative_becomes_zero() -> None:
    assert resolve_page(-7, 50) == (0, 50)


def test_catalog_max_limit_is_honoured() -> None:
    assert resolve_page(0, 5000, max_limit=1000) == (0, 1000)


def test_default_limit_used_when_none() -> None:
    assert resolve_page(0, None) == (0, 50)


def test_set_total_header_writes_string() -> None:
    response = Response()
    set_total_header(response, 123)
    assert response.headers[TOTAL_COUNT_HEADER] == '123'
