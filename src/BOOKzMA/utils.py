import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from BOOKzMA.constants import DEFAULT_TIMEZONE

_FA_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_EN_TO_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa(value: int | str) -> str:
    return str(value).translate(_EN_TO_FA)


def parse_positive_int(text: str, maximum: int) -> int | None:
    normalized = text.strip().translate(_FA_TO_EN)
    if not re.fullmatch(r"\d+", normalized):
        return None
    value = int(normalized)
    return value if 0 < value <= maximum else None


def parse_time(text: str) -> time | None:
    """21:30 ، ۲۱:۳۰ ، 21.30 یا فقط 21"""
    s = text.strip().translate(_FA_TO_EN).replace(".", ":").replace("٫", ":")
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", s)
    if not m:
        return None
    hour, minute = int(m[1]), int(m[2] or 0)
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def safe_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def local_now(tz_name: str) -> datetime:
    return datetime.now(safe_zone(tz_name))


def local_today(tz_name: str) -> date:
    return local_now(tz_name).date()
