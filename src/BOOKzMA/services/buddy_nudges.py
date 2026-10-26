"""Eligibility rules for opt-in study-buddy nudges."""

from datetime import date

from BOOKzMA.db.models import BuddyPair, User


def classify_nudge_targets(
    buddies: list[tuple[BuddyPair, User]], read_user_ids: set[int], nudge_day: date
) -> tuple[list[tuple[BuddyPair, User]], int, int]:
    targets = []
    already_read = 0
    already_nudged = 0
    for pair, buddy in buddies:
        if buddy.id in read_user_ids:
            already_read += 1
        elif pair.last_nudge_on == nudge_day:
            already_nudged += 1
        else:
            targets.append((pair, buddy))
    return targets, already_read, already_nudged