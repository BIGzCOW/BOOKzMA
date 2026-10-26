import hashlib
import re
import secrets
from datetime import date, timedelta


def new_invite_token() -> str:
    return secrets.token_urlsafe(24)


def invite_token_hash(token: str) -> str | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", token):
        return None
    return hashlib.sha256(token.encode()).hexdigest()


def challenge_end_date(start: date, duration: int) -> date:
    if duration not in {7, 30}:
        raise ValueError("challenge duration must be 7 or 30 days")
    return start + timedelta(days=duration - 1)


def challenge_progress(completed_days: set[date], start: date, today: date) -> int:
    if today < start:
        return 0
    count = 0
    day = start
    while day <= today and day in completed_days:
        count += 1
        day += timedelta(days=1)
    return count


def challenge_failed(
    completed_days: set[date], start: date, end: date, today: date
) -> bool:
    if today > end:
        return True
    last_closed_day = min(today - timedelta(days=1), end)
    day = start
    while day <= last_closed_day:
        if day not in completed_days:
            return True
        day += timedelta(days=1)
    return False