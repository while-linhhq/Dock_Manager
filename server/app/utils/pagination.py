from fastapi import Response

DEFAULT_PAGE_SIZE: int = 50
MAX_PAGE_SIZE: int = 200
DEFAULT_CATALOG_LIMIT: int = 100
MAX_CATALOG_LIMIT: int = 1000

TOTAL_COUNT_HEADER: str = 'X-Total-Count'


def resolve_page(
    skip: int | None,
    limit: int | None,
    *,
    max_limit: int = MAX_PAGE_SIZE,
    default_limit: int = DEFAULT_PAGE_SIZE,
) -> tuple[int, int]:
    """Clamp client pagination input into a safe ``(skip, limit)`` pair.

    ``None`` skip means 0, ``None`` limit means ``default_limit``. Out-of-range
    values are clamped instead of rejected so endpoints never 500 on bad input.
    """
    safe_skip = 0 if skip is None else max(int(skip), 0)
    requested_limit = int(default_limit) if limit is None else int(limit)
    safe_limit = min(max(requested_limit, 1), int(max_limit))
    return safe_skip, safe_limit


def set_total_header(response: Response, total: int) -> None:
    """Publish the total row count (before paging) via the X-Total-Count header."""
    response.headers[TOTAL_COUNT_HEADER] = str(total)
