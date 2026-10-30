import re

from BOOKzMA.constants import MAX_BOOK_AUTHOR_LENGTH, MAX_BOOK_TITLE_LENGTH


def normalize_title(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized or len(normalized) > MAX_BOOK_TITLE_LENGTH:
        return None
    return normalized


def normalize_author(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized or len(normalized) > MAX_BOOK_AUTHOR_LENGTH:
        return None
    return normalized


def progress_percent(pages_read: int, total_pages: int) -> int:
    if total_pages <= 0:
        return 0
    return max(0, min(100, pages_read * 100 // total_pages))
