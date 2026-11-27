from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import case, delete, func, or_, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import (
    MesbakBuddyInvite,
    MesbakBuddyPair,
    MesbakBuddyQueue,
    MesbakBadge,
    MesbakChallenge,
    MesbakEntry,
    MesbakProfile,
    MesbakReminder,
    User,
)
from BOOKzMA.services.mesbak import (
    completed_days,
    effective_goal,
    validate_schedule,
)
from BOOKzMA.services.mesbak_social import (
    challenge_end_date,
    challenge_failed,
    challenge_progress,
)
from BOOKzMA.utils import local_today

_MESBAK_MATCH_LOCK_ID = 4_875_316_202


@dataclass(frozen=True)
class RecordResult:
    status: str
    completed_count: int
    daily_goal: int
    day_complete: bool


async def get_profile(
    session: AsyncSession, user_id: int, today: date | None = None
) -> MesbakProfile | None:
    profile = await session.get(MesbakProfile, user_id)
    if profile is not None and today is not None:
        _activate_due_goal(profile, today)
    return profile


async def configure(
    session: AsyncSession,
    user_id: int,
    daily_goal: int,
    times: list[time],
    today: date,
) -> MesbakProfile:
    schedule = validate_schedule(daily_goal, times)
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())
    profile = await session.scalar(
        select(MesbakProfile).where(MesbakProfile.user_id == user_id).with_for_update()
    )
    if profile is None:
        profile = MesbakProfile(
            user_id=user_id,
            enabled=True,
            daily_goal=daily_goal,
        )
        session.add(profile)
        await session.flush()
    else:
        _activate_due_goal(profile, today)
        if profile.daily_goal != daily_goal:
            profile.next_daily_goal = daily_goal
            profile.goal_effective_on = today + timedelta(days=1)
        else:
            profile.next_daily_goal = None
            profile.goal_effective_on = None
        profile.enabled = True

    for slot, remind_at in enumerate(schedule, 1):
        statement = insert(MesbakReminder).values(user_id=user_id, slot=slot, remind_at=remind_at)
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[MesbakReminder.user_id, MesbakReminder.slot],
                set_={"remind_at": statement.excluded.remind_at},
            )
        )
    return profile


async def set_enabled(session: AsyncSession, user_id: int, enabled: bool) -> bool:
    if not enabled:
        await session.execute(select(func.pg_advisory_xact_lock(_MESBAK_MATCH_LOCK_ID)))
    profile = await session.scalar(
        select(MesbakProfile).where(MesbakProfile.user_id == user_id).with_for_update()
    )
    if profile is None:
        return False
    profile.enabled = enabled
    if not enabled:
        profile.league_opt_in = False
        now = datetime.now(timezone.utc)
        await session.execute(
            update(MesbakChallenge)
            .where(
                MesbakChallenge.user_id == user_id,
                MesbakChallenge.status == "active",
            )
            .values(status="cancelled")
        )
        await session.execute(
            update(MesbakBuddyPair)
            .where(
                MesbakBuddyPair.status == "active",
                or_(MesbakBuddyPair.user_a == user_id, MesbakBuddyPair.user_b == user_id),
            )
            .values(status="ended", ended_at=now)
        )
        await session.execute(
            delete(MesbakBuddyInvite).where(MesbakBuddyInvite.inviter_id == user_id)
        )
        await session.execute(delete(MesbakBuddyQueue).where(MesbakBuddyQueue.user_id == user_id))
    return True


async def list_reminders(session: AsyncSession, user_id: int) -> list[MesbakReminder]:
    result = await session.scalars(
        select(MesbakReminder)
        .where(MesbakReminder.user_id == user_id)
        .order_by(MesbakReminder.slot)
    )
    return list(result)


async def set_reminder_time(session: AsyncSession, user_id: int, slot: int, remind_at: time) -> str:
    if not 1 <= slot <= 5:
        raise ValueError("slot must be between 1 and 5")
    profile = await session.scalar(
        select(MesbakProfile)
        .where(MesbakProfile.user_id == user_id, MesbakProfile.enabled.is_(True))
        .with_for_update()
    )
    if profile is None:
        return "inactive"
    duplicate = await session.scalar(
        select(MesbakReminder.slot).where(
            MesbakReminder.user_id == user_id,
            MesbakReminder.slot != slot,
            MesbakReminder.remind_at == remind_at,
        )
    )
    if duplicate is not None:
        return "duplicate"
    statement = insert(MesbakReminder).values(user_id=user_id, slot=slot, remind_at=remind_at)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[MesbakReminder.user_id, MesbakReminder.slot],
            set_={"remind_at": statement.excluded.remind_at},
        )
    )
    return "ok"


async def record_occurrence(
    session: AsyncSession, user_id: int, today: date, slot: int
) -> RecordResult:
    profile = await session.scalar(
        select(MesbakProfile).where(MesbakProfile.user_id == user_id).with_for_update()
    )
    if profile is None or not profile.enabled:
        return RecordResult("inactive", 0, 0, False)

    _activate_due_goal(profile, today)
    goal = effective_goal(
        profile.daily_goal, profile.next_daily_goal, profile.goal_effective_on, today
    )
    if not 1 <= slot <= goal:
        return RecordResult("invalid_slot", 0, goal, False)

    statement = (
        insert(MesbakEntry)
        .values(user_id=user_id, day=today, slot=slot, daily_goal=goal)
        .on_conflict_do_nothing()
        .returning(MesbakEntry.slot)
    )
    created = (await session.execute(statement)).first() is not None
    count = (
        await session.scalar(
            select(func.count())
            .select_from(MesbakEntry)
            .where(MesbakEntry.user_id == user_id, MesbakEntry.day == today)
        )
        or 0
    )
    status = "ok" if created else "duplicate"
    return RecordResult(status, count, goal, count >= goal)


async def entries_for_day(session: AsyncSession, user_id: int, day: date) -> set[int]:
    result = await session.scalars(
        select(MesbakEntry.slot).where(MesbakEntry.user_id == user_id, MesbakEntry.day == day)
    )
    return set(result)


async def daily_records(session: AsyncSession, user_id: int) -> list[tuple[date, int, int]]:
    result = await session.execute(
        select(MesbakEntry.day, func.count(), func.max(MesbakEntry.daily_goal))
        .where(MesbakEntry.user_id == user_id)
        .group_by(MesbakEntry.day)
        .order_by(MesbakEntry.day)
    )
    return [(day, count, goal) for day, count, goal in result]


async def completed_day_set(session: AsyncSession, user_id: int) -> set[date]:
    return completed_days(await daily_records(session, user_id))


async def award_streak_badges(
    session: AsyncSession, user_id: int, day: date, streak: int
) -> list[str]:
    labels = {7: "streak_7", 30: "streak_30", 100: "streak_100"}
    code = labels.get(streak)
    if code is None:
        return []
    statement = (
        insert(MesbakBadge)
        .values(user_id=user_id, code=code, awarded_day=day)
        .on_conflict_do_nothing(index_elements=[MesbakBadge.user_id, MesbakBadge.code])
        .returning(MesbakBadge.code)
    )
    result = await session.scalar(statement)
    return [result] if result is not None else []


async def list_badges(session: AsyncSession, user_id: int) -> list[str]:
    result = await session.scalars(
        select(MesbakBadge.code)
        .where(MesbakBadge.user_id == user_id)
        .order_by(MesbakBadge.awarded_day, MesbakBadge.id)
    )
    return list(result)


async def due_reminders(
    session: AsyncSession,
) -> list[tuple[MesbakReminder, MesbakProfile, User]]:
    result = await session.execute(
        select(MesbakReminder, MesbakProfile, User)
        .join(MesbakProfile, MesbakProfile.user_id == MesbakReminder.user_id)
        .join(User, User.id == MesbakProfile.user_id)
        .where(MesbakProfile.enabled.is_(True))
        .order_by(MesbakReminder.user_id, MesbakReminder.slot)
    )
    return [(reminder, profile, user) for reminder, profile, user in result.all()]


async def mark_reminder_sent(session: AsyncSession, user_id: int, slot: int, day: date) -> None:
    reminder = await session.get(MesbakReminder, (user_id, slot))
    if reminder is not None:
        reminder.last_sent_on = day
        reminder.retry_after_until = None


async def delete_reminders(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(MesbakReminder).where(MesbakReminder.user_id == user_id))


async def toggle_league(session: AsyncSession, user_id: int, enabled: bool) -> bool:
    profile = await session.scalar(
        select(MesbakProfile)
        .where(MesbakProfile.user_id == user_id, MesbakProfile.enabled.is_(True))
        .with_for_update()
    )
    if profile is None:
        return False
    profile.league_opt_in = enabled
    return True


async def league_rows(session: AsyncSession, today: date) -> list[tuple[int, str, int]]:
    members = await session.execute(
        select(User.id, User.display_name, User.timezone)
        .join(MesbakProfile, MesbakProfile.user_id == User.id)
        .where(MesbakProfile.enabled.is_(True), MesbakProfile.league_opt_in.is_(True))
    )
    people = members.all()
    if not people:
        return []
    user_ids = [person.id for person in people]
    records = await session.execute(
        select(
            MesbakEntry.user_id,
            MesbakEntry.day,
            func.count(),
            func.max(MesbakEntry.daily_goal),
        )
        .where(
            MesbakEntry.user_id.in_(user_ids),
            MesbakEntry.day.between(today - timedelta(days=8), today + timedelta(days=1)),
        )
        .group_by(MesbakEntry.user_id, MesbakEntry.day)
    )
    completed_by_user: dict[int, list[date]] = {}
    for user_id, day, count, goal in records:
        if count >= goal:
            completed_by_user.setdefault(user_id, []).append(day)
    rows = []
    for person in people:
        member_today = local_today(person.timezone)
        completed = set(completed_by_user.get(person.id, []))
        week_start = member_today - timedelta(days=6)
        week_count = sum(week_start <= day <= member_today for day in completed)
        rows.append(
            (
                person.id,
                person.display_name or "کاربر",
                week_count,
            )
        )
    return sorted(rows, key=lambda row: (-row[2], row[1].casefold(), row[0]))


async def start_challenge(
    session: AsyncSession, user_id: int, duration: int, today: date
) -> tuple[MesbakChallenge | None, str]:
    if duration not in {7, 30}:
        return None, "invalid"
    profile = await session.scalar(
        select(MesbakProfile)
        .where(MesbakProfile.user_id == user_id, MesbakProfile.enabled.is_(True))
        .with_for_update()
    )
    if profile is None:
        return None, "inactive"
    existing = await session.scalar(
        select(MesbakChallenge)
        .where(MesbakChallenge.user_id == user_id, MesbakChallenge.status == "active")
        .with_for_update()
    )
    if existing is not None:
        return existing, "already_active"
    challenge = MesbakChallenge(
        user_id=user_id,
        duration=duration,
        starts_on=today,
        ends_on=challenge_end_date(today, duration),
    )
    session.add(challenge)
    await session.flush()
    return challenge, "started"


async def challenge_state(
    session: AsyncSession, user_id: int, today: date
) -> tuple[MesbakChallenge | None, int]:
    challenge = await session.scalar(
        select(MesbakChallenge).where(
            MesbakChallenge.user_id == user_id, MesbakChallenge.status == "active"
        )
    )
    if challenge is None:
        return None, 0
    days = await completed_day_set(session, user_id)
    progress = challenge_progress(days, challenge.starts_on, min(today, challenge.ends_on))
    if progress >= challenge.duration:
        challenge.status = "completed"
    elif challenge_failed(days, challenge.starts_on, challenge.ends_on, today):
        challenge.status = "cancelled"
    return challenge, progress


async def cancel_challenge(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(
        update(MesbakChallenge)
        .where(MesbakChallenge.user_id == user_id, MesbakChallenge.status == "active")
        .values(status="cancelled")
    )
    return result.rowcount == 1


async def create_buddy_invite(
    session: AsyncSession,
    inviter_id: int,
    token_hash: str,
    expires_at: datetime,
) -> bool:
    await session.execute(select(func.pg_advisory_xact_lock(_MESBAK_MATCH_LOCK_ID)))
    profile = await session.scalar(
        select(MesbakProfile).where(
            MesbakProfile.user_id == inviter_id, MesbakProfile.enabled.is_(True)
        )
    )
    if profile is None:
        return False
    queued = await session.scalar(
        select(MesbakBuddyQueue.user_id).where(MesbakBuddyQueue.user_id == inviter_id)
    )
    if queued is not None:
        return False
    session.add(
        MesbakBuddyInvite(token_hash=token_hash, inviter_id=inviter_id, expires_at=expires_at)
    )
    await session.flush()
    return True


async def redeem_buddy_invite(
    session: AsyncSession,
    token_hash: str,
    recipient_id: int,
    now: datetime,
) -> tuple[str, int | None]:
    await session.execute(select(func.pg_advisory_xact_lock(_MESBAK_MATCH_LOCK_ID)))
    invite = await session.scalar(
        select(MesbakBuddyInvite)
        .where(MesbakBuddyInvite.token_hash == token_hash)
        .with_for_update()
    )
    if invite is None or invite.expires_at <= now:
        return "unavailable", None
    inviter_id = invite.inviter_id
    if inviter_id == recipient_id:
        return "self", inviter_id
    profile_ids = await session.scalars(
        select(MesbakProfile.user_id)
        .where(
            MesbakProfile.user_id.in_((inviter_id, recipient_id)),
            MesbakProfile.enabled.is_(True),
        )
        .order_by(MesbakProfile.user_id)
        .with_for_update()
    )
    if set(profile_ids) != {inviter_id, recipient_id}:
        return "inactive", inviter_id
    queued_ids = set(
        await session.scalars(
            select(MesbakBuddyQueue.user_id).where(
                MesbakBuddyQueue.user_id.in_((inviter_id, recipient_id))
            )
        )
    )
    if queued_ids:
        return "busy", inviter_id
    user_a, user_b = sorted((inviter_id, recipient_id))
    existing = await session.scalar(
        select(MesbakBuddyPair.id).where(
            MesbakBuddyPair.user_a == user_a,
            MesbakBuddyPair.user_b == user_b,
            MesbakBuddyPair.status == "active",
        )
    )
    if existing is not None:
        await session.delete(invite)
        return "already", inviter_id
    statement = insert(MesbakBuddyPair).values(user_a=user_a, user_b=user_b, status="active")
    result = await session.execute(
        statement.on_conflict_do_nothing(
            index_elements=[MesbakBuddyPair.user_a, MesbakBuddyPair.user_b],
            index_where=text("status = 'active'"),
        )
    )
    await session.delete(invite)
    return ("accepted" if result.rowcount else "already"), inviter_id


async def join_random_buddy_queue(session: AsyncSession, user_id: int) -> tuple[str, int | None]:
    await session.execute(select(func.pg_advisory_xact_lock(_MESBAK_MATCH_LOCK_ID)))
    profile = await session.scalar(
        select(MesbakProfile)
        .where(MesbakProfile.user_id == user_id, MesbakProfile.enabled.is_(True))
        .with_for_update()
    )
    if profile is None:
        return "inactive", None

    statement = insert(MesbakBuddyQueue).values(user_id=user_id)
    await session.execute(
        statement.on_conflict_do_nothing(index_elements=[MesbakBuddyQueue.user_id])
    )
    paired_with_me = select(MesbakBuddyPair.id).where(
        MesbakBuddyPair.status == "active",
        or_(
            (MesbakBuddyPair.user_a == user_id)
            & (MesbakBuddyPair.user_b == MesbakBuddyQueue.user_id),
            (MesbakBuddyPair.user_b == user_id)
            & (MesbakBuddyPair.user_a == MesbakBuddyQueue.user_id),
        ),
    )
    partner_id = await session.scalar(
        select(MesbakBuddyQueue.user_id)
        .join(MesbakProfile, MesbakProfile.user_id == MesbakBuddyQueue.user_id)
        .where(
            MesbakBuddyQueue.user_id != user_id,
            MesbakProfile.enabled.is_(True),
            ~paired_with_me.exists(),
        )
        .order_by(MesbakBuddyQueue.joined_at, MesbakBuddyQueue.user_id)
        .with_for_update(of=MesbakBuddyQueue, skip_locked=True)
        .limit(1)
    )
    if partner_id is None:
        return "waiting", None

    user_a, user_b = sorted((user_id, partner_id))
    session.add(
        MesbakBuddyPair(
            user_a=user_a,
            user_b=user_b,
            pair_type="random",
            status="active",
        )
    )
    await session.execute(
        delete(MesbakBuddyQueue).where(MesbakBuddyQueue.user_id.in_((user_id, partner_id)))
    )
    return "matched", partner_id


async def leave_random_buddy_queue(session: AsyncSession, user_id: int) -> bool:
    await session.execute(select(func.pg_advisory_xact_lock(_MESBAK_MATCH_LOCK_ID)))
    result = await session.execute(
        delete(MesbakBuddyQueue)
        .where(MesbakBuddyQueue.user_id == user_id)
        .returning(MesbakBuddyQueue.user_id)
    )
    return result.first() is not None


async def is_random_buddy_queued(session: AsyncSession, user_id: int) -> bool:
    return (
        await session.scalar(
            select(MesbakBuddyQueue.user_id).where(MesbakBuddyQueue.user_id == user_id)
        )
        is not None
    )


async def buddy_rows(session: AsyncSession, user_id: int) -> list[tuple[int, int, str, str]]:
    friend_id = case(
        (MesbakBuddyPair.user_a == user_id, MesbakBuddyPair.user_b),
        else_=MesbakBuddyPair.user_a,
    )
    result = await session.execute(
        select(MesbakBuddyPair.id, User.id, User.display_name, MesbakBuddyPair.pair_type)
        .join(User, User.id == friend_id)
        .where(
            MesbakBuddyPair.status == "active",
            or_(MesbakBuddyPair.user_a == user_id, MesbakBuddyPair.user_b == user_id),
        )
        .order_by(User.display_name, User.id)
    )
    return [
        (pair_id, friend_id, display_name or "کاربر", pair_type)
        for pair_id, friend_id, display_name, pair_type in result
    ]


async def buddy_users(session: AsyncSession, user_id: int) -> list[tuple[MesbakBuddyPair, User]]:
    """همهٔ رفیق‌های فعال با آبجکت User؛ مرتب بر اساس نام نمایشی."""
    friend_id = case(
        (MesbakBuddyPair.user_a == user_id, MesbakBuddyPair.user_b),
        else_=MesbakBuddyPair.user_a,
    )
    rows = await session.execute(
        select(MesbakBuddyPair, User)
        .join(User, User.id == friend_id)
        .where(
            MesbakBuddyPair.status == "active",
            or_(MesbakBuddyPair.user_a == user_id, MesbakBuddyPair.user_b == user_id),
        )
        .order_by(User.display_name, User.id)
    )
    return [(pair, buddy) for pair, buddy in rows]


async def users_completed_on_days(
    session: AsyncSession, user_days: list[tuple[int, date]]
) -> set[int]:
    """کاربرهایی که در روز محلی خودشان هدف مسباک را کامل کرده‌اند (کوئری دسته‌ای)."""
    if not user_days:
        return set()
    result = await session.scalars(
        select(MesbakEntry.user_id)
        .where(tuple_(MesbakEntry.user_id, MesbakEntry.day).in_(user_days))
        .group_by(MesbakEntry.user_id, MesbakEntry.day)
        .having(
            func.count() >= func.max(MesbakEntry.daily_goal),
            func.max(MesbakEntry.daily_goal).between(1, 5),
        )
    )
    return set(result)


async def buddy_pair_for_user(
    session: AsyncSession, user_id: int, pair_id: int
) -> tuple[MesbakBuddyPair, User] | None:
    friend_id = case(
        (MesbakBuddyPair.user_a == user_id, MesbakBuddyPair.user_b),
        else_=MesbakBuddyPair.user_a,
    )
    row = await session.execute(
        select(MesbakBuddyPair, User)
        .join(User, User.id == friend_id)
        .where(
            MesbakBuddyPair.id == pair_id,
            MesbakBuddyPair.status == "active",
            or_(MesbakBuddyPair.user_a == user_id, MesbakBuddyPair.user_b == user_id),
        )
    )
    found = row.first()
    return (found[0], found[1]) if found else None


async def end_buddy_pair(
    session: AsyncSession, user_id: int, pair_id: int, now: datetime
) -> int | None:
    """End one active pair; return the partner's user id, or None if nothing ended."""
    await session.execute(select(func.pg_advisory_xact_lock(_MESBAK_MATCH_LOCK_ID)))
    row = await session.execute(
        update(MesbakBuddyPair)
        .where(
            MesbakBuddyPair.id == pair_id,
            MesbakBuddyPair.status == "active",
            or_(MesbakBuddyPair.user_a == user_id, MesbakBuddyPair.user_b == user_id),
        )
        .values(status="ended", ended_at=now)
        .returning(
            case(
                (MesbakBuddyPair.user_a == user_id, MesbakBuddyPair.user_b),
                else_=MesbakBuddyPair.user_a,
            )
        )
    )
    return row.scalar_one_or_none()


async def claim_buddy_nudge(
    session: AsyncSession, user_id: int, pair_id: int, today: date
) -> tuple[str, int | None, str | None]:
    pair = await session.scalar(
        select(MesbakBuddyPair)
        .where(
            MesbakBuddyPair.id == pair_id,
            MesbakBuddyPair.status == "active",
            or_(MesbakBuddyPair.user_a == user_id, MesbakBuddyPair.user_b == user_id),
        )
        .with_for_update()
    )
    if pair is None:
        return "unavailable", None, None
    recipient_id = pair.user_b if pair.user_a == user_id else pair.user_a
    if pair.last_nudge_on == today:
        return "limit", recipient_id, pair.pair_type
    recipient_active = await session.scalar(
        select(MesbakProfile.user_id).where(
            MesbakProfile.user_id == recipient_id, MesbakProfile.enabled.is_(True)
        )
    )
    if recipient_active is None:
        return "inactive", recipient_id, pair.pair_type
    pair.last_nudge_on = today
    return "ok", recipient_id, pair.pair_type


def _activate_due_goal(profile: MesbakProfile, today: date) -> None:
    if (
        profile.next_daily_goal is not None
        and profile.goal_effective_on is not None
        and profile.goal_effective_on <= today
    ):
        profile.daily_goal = profile.next_daily_goal
        profile.next_daily_goal = None
        profile.goal_effective_on = None
