"""Secure start payloads for one-time study-buddy invitations."""

import hashlib
import re
import secrets

INVITE_PREFIX = "buddy_"
_INVITE_PATTERN = re.compile(r"buddy_[A-Za-z0-9_-]{32}\Z")


def create_invite_token() -> tuple[str, str]:
    payload = f"{INVITE_PREFIX}{secrets.token_urlsafe(24)}"
    return payload, hashlib.sha256(payload.encode()).hexdigest()


def invite_token_hash(payload: str | None) -> str | None:
    if payload is None or _INVITE_PATTERN.fullmatch(payload) is None:
        return None
    return hashlib.sha256(payload.encode()).hexdigest()