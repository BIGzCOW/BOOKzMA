from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import case, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import (
    MiswakBuddyInvite,
    MiswakBuddyPair,
    MiswakBadge,
    MiswakChallenge,
    MiswakEntry,
    MiswakProfile,
    MiswakReminder,
    User,
)
from BOOKzMA.services.miswak import (
    completed_days,
    effective_goal,
    validate_schedule,
)
from BOOKzMA.services.miswak_social import (
    challenge_end_date,
    challenge_failed,
    challenge_progress,
)
from BOOKzMA.utils import local_today


@dataclass(frozen=True)
class RecordResult:
    status: str
    completed_count: int
    daily_goal: int
    day_complete: bool


async def get_profile(
    session: AsyncSession, user_id: int, today: date | None = None
) -> MiswakProfile | None:
    profile = await session.get(MiswakProfile, user_id)
    if profile is not None and today is not None:
        _activate_due_goal(profile, today)
    return profile


async def configure(
    session: AsyncSession,
    user_id: int,
    daily_goal: int,
    times: list[time],
    today: date,
) -> MiswakProfile:
    schedule = validate_schedule(daily_goal, times)
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())
    profile = await session.scalar(
        select(MiswakProfile).where(MiswakProfile.user_id == user_id).with_for_update()
    )
    if profile is None:
        profile = MiswakProfile(user_id=user_id, enabled=True, daily_goal=daily_goal)
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
        statement = insert(MiswakReminder).values(
            user_id=user_id, slot=slot, remind_at=remind_at
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[MiswakReminder.user_id, MiswakReminder.slot],
                set_={"remind_at": statement.excluded.remind_at},
            )
        )
    return profile


async def set_enabled(session: AsyncSession, user_id: int, enabled: bool) -> bool:
    profile = await session.scalar(
        select(MiswakProfile).where(MiswakProfile.user_id == user_id).with_for_update()
    )
    if profile is None:
        return False
    profile.enabled = enabled
    if not enabled:
        profile.league_opt_in = False
        now = datetime.now(timezone.utc)
        await session.execute(
            update(MiswakChallenge)
            .where(
                MiswakChallenge.user_id == user_id,
                MiswakChallenge.status == "active",
            )
            .values(status="cancelled")
        )
        await session.execute(
            update(MiswakBuddyPair)
            .where(
                MiswakBuddyPair.status == "active",
                or_(MiswakBuddyPair.user_a == user_id, MiswakBuddyPair.user_b == user_id),
            )
            .values(status="ended", ended_at=now)
        )
        await session.execute(
            delete(MiswakBuddyInvite).where(MiswakBuddyInvite.inviter_id == user_id)
        )
    return True


async def list_reminders(session: AsyncSession, user_id: int) -> list[MiswakReminder]:
    result = await session.scalars(
        select(MiswakReminder)
        .where(MiswakReminder.user_id == user_id)
        .order_by(MiswakReminder.slot)
    )
    return list(result)


async def set_reminder_time(
    session: AsyncSession, user_id: int, slot: int, remind_at: time
) -> str:
    if not 1 <= slot <= 5:
        raise ValueError("slot must be between 1 and 5")
    profile = await session.scalar(
        select(MiswakProfile)
        .where(MiswakProfile.user_id == user_id, MiswakProfile.enabled.is_(True))
        .with_for_update()
    )
    if profile is None:
        return "inactive"
    duplicate = await session.scalar(
        select(MiswakReminder.slot).where(
            MiswakReminder.user_id == user_id,
            MiswakReminder.slot != slot,
            MiswakReminder.remind_at == remind_at,
        )
    )
    if duplicate is not None:
        return "duplicate"
    statement = insert(MiswakReminder).values(
        user_id=user_id, slot=slot, remind_at=remind_at
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[MiswakReminder.user_id, MiswakReminder.slot],
            set_={"remind_at": statement.excluded.remind_at},
        )
    )
    return "ok"


async def record_occurrence(
    session: AsyncSession, user_id: int, today: date, slot: int
) -> RecordResult:
    profile = await session.scalar(
        select(MiswakProfile).where(MiswakProfile.user_id == user_id).with_for_update()
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
        insert(MiswakEntry)
        .values(user_id=user_id, day=today, slot=slot, daily_goal=goal)
        .on_conflict_do_nothing()
        .returning(MiswakEntry.slot)
    )
    created = (await session.execute(statement)).first() is not None
    count = await session.scalar(
        select(func.count())
        .select_from(MiswakEntry)
        .where(MiswakEntry.user_id == user_id, MiswakEntry.day == today)
    ) or 0
    status = "ok" if created else "duplicate"
    return RecordResult(status, count, goal, count >= goal)


async def entries_for_day(session: AsyncSession, user_id: int, day: date) -> set[int]:
    result = await session.scalars(
        select(MiswakEntry.slot).where(
            MiswakEntry.user_id == user_id, MiswakEntry.day == day
        )
    )
    return set(result)


async def daily_records(
    session: AsyncSession, user_id: int
) -> list[tuple[date, int, int]]:
    result = await session.execute(
        select(MiswakEntry.day, func.count(), func.max(MiswakEntry.daily_goal))
        .where(MiswakEntry.user_id == user_id)
        .group_by(MiswakEntry.day)
        .order_by(MiswakEntry.day)
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
        insert(MiswakBadge)
        .values(user_id=user_id, code=code, awarded_day=day)
        .on_conflict_do_nothing(index_elements=[MiswakBadge.user_id, MiswakBadge.code])
        .returning(MiswakBadge.code)
    )
    result = await session.scalar(statement)
    return [result] if result is not None else []


async def list_badges(session: AsyncSession, user_id: int) -> list[str]:
    result = await session.scalars(
        select(MiswakBadge.code)
        .where(MiswakBadge.user_id == user_id)
        .order_by(MiswakBadge.awarded_day, MiswakBadge.id)
    )
    return list(result)


async def due_reminders(
    session: AsyncSession,
) -> list[tuple[MiswakReminder, MiswakProfile, User]]:
    result = await session.execute(
        select(MiswakReminder, MiswakProfile, User)
        .join(MiswakProfile, MiswakProfile.user_id == MiswakReminder.user_id)
        .join(User, User.id == MiswakProfile.user_id)
        .where(MiswakProfile.enabled.is_(True))
        .order_by(MiswakReminder.user_id, MiswakReminder.slot)
    )
    return [(reminder, profile, user) for reminder, profile, user in result.all()]


async def mark_reminder_sent(
    session: AsyncSession, user_id: int, slot: int, day: date
) -> None:
    reminder = await session.get(MiswakReminder, (user_id, slot))
    if reminder is not None:
        reminder.last_sent_on = day
        reminder.retry_after_until = None


async def delete_reminders(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(MiswakReminder).where(MiswakReminder.user_id == user_id))


async def toggle_league(session: AsyncSession, user_id: int, enabled: bool) -> bool:
    profile = await session.scalar(
        select(MiswakProfile)
        .where(MiswakProfile.user_id == user_id, MiswakProfile.enabled.is_(True))
        .with_for_update()
    )
    if profile is None:
        return False
    profile.league_opt_in = enabled
    return True


async def league_rows(
    session: AsyncSession, today: date
) -> list[tuple[int, str, int]]:
    members = await session.execute(
        select(User.id, User.display_name, User.timezone)
        .join(MiswakProfile, MiswakProfile.user_id == User.id)
        .where(MiswakProfile.enabled.is_(True), MiswakProfile.league_opt_in.is_(True))
    )
    people = members.all()
    if not people:
        return []
    user_ids = [person.id for person in people]
    records = await session.execute(
        select(
            MiswakEntry.user_id,
            MiswakEntry.day,
            func.count(),
            func.max(MiswakEntry.daily_goal),
        )
        .where(
            MiswakEntry.user_id.in_(user_ids),
            MiswakEntry.day.between(today - timedelta(days=8), today + timedelta(days=1)),
        )
        .group_by(MiswakEntry.user_id, MiswakEntry.day)
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
) -> tuple[MiswakChallenge | None, str]:
    if duration not in {7, 30}:
        return None, "invalid"
    profile = await session.scalar(
        select(MiswakProfile)
        .where(MiswakProfile.user_id == user_id, MiswakProfile.enabled.is_(True))
        .with_for_update()
    )
    if profile is None:
        return None, "inactive"
    existing = await session.scalar(
        select(MiswakChallenge)
        .where(MiswakChallenge.user_id == user_id, MiswakChallenge.status == "active")
        .with_for_update()
    )
    if existing is not None:
        return existing, "already_active"
    challenge = MiswakChallenge(
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
) -> tuple[MiswakChallenge | None, int]:
    challenge = await session.scalar(
        select(MiswakChallenge).where(
            MiswakChallenge.user_id == user_id, MiswakChallenge.status == "active"
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
        update(MiswakChallenge)
        .where(MiswakChallenge.user_id == user_id, MiswakChallenge.status == "active")
        .values(status="cancelled")
    )
    return result.rowcount == 1


async def create_buddy_invite(
    session: AsyncSession,
    inviter_id: int,
    token_hash: str,
    expires_at: datetime,
) -> bool:
    profile = await session.scalar(
        select(MiswakProfile).where(
            MiswakProfile.user_id == inviter_id, MiswakProfile.enabled.is_(True)
        )
    )
    if profile is None:
        return False
    session.add(
        MiswakBuddyInvite(token_hash=token_hash, inviter_id=inviter_id, expires_at=expires_at)
    )
    await session.flush()
    return True


async def redeem_buddy_invite(
    session: AsyncSession,
    token_hash: str,
    recipient_id: int,
    now: datetime,
) -> tuple[str, int | None]:
    invite = await session.scalar(
        select(MiswakBuddyInvite)
        .where(MiswakBuddyInvite.token_hash == token_hash)
        .with_for_update()
    )
    if invite is None or invite.expires_at <= now:
        return "unavailable", None
    inviter_id = invite.inviter_id
    if inviter_id == recipient_id:
        return "self", inviter_id
    profile_ids = await session.scalars(
        select(MiswakProfile.user_id)
        .where(
            MiswakProfile.user_id.in_((inviter_id, recipient_id)),
            MiswakProfile.enabled.is_(True),
        )
        .order_by(MiswakProfile.user_id)
        .with_for_update()
    )
    if set(profile_ids) != {inviter_id, recipient_id}:
        return "inactive", inviter_id
    user_a, user_b = sorted((inviter_id, recipient_id))
    existing = await session.scalar(
        select(MiswakBuddyPair.id).where(
            MiswakBuddyPair.user_a == user_a,
            MiswakBuddyPair.user_b == user_b,
            MiswakBuddyPair.status == "active",
        )
    )
    if existing is not None:
        await session.delete(invite)
        return "already", inviter_id
    statement = insert(MiswakBuddyPair).values(
        user_a=user_a, user_b=user_b, status="active"
    )
    result = await session.execute(
        statement.on_conflict_do_nothing(
            index_elements=[MiswakBuddyPair.user_a, MiswakBuddyPair.user_b],
            index_where=text("status = 'active'"),
        )
    )
    await session.delete(invite)
    return ("accepted" if result.rowcount else "already"), inviter_id


async def buddy_rows(
    session: AsyncSession, user_id: int
) -> list[tuple[int, int, str]]:
    friend_id = case(
        (MiswakBuddyPair.user_a == user_id, MiswakBuddyPair.user_b),
        else_=MiswakBuddyPair.user_a,
    )
    result = await session.execute(
        select(MiswakBuddyPair.id, User.id, User.display_name)
        .join(User, User.id == friend_id)
        .where(
            MiswakBuddyPair.status == "active",
            or_(MiswakBuddyPair.user_a == user_id, MiswakBuddyPair.user_b == user_id),
        )
        .order_by(User.display_name, User.id)
    )
    return [
        (pair_id, friend_id, display_name or "کاربر")
        for pair_id, friend_id, display_name in result
    ]


async def end_buddy_pair(
    session: AsyncSession, user_id: int, pair_id: int, now: datetime
) -> bool:
    result = await session.execute(
        update(MiswakBuddyPair)
        .where(
            MiswakBuddyPair.id == pair_id,
            MiswakBuddyPair.status == "active",
            or_(MiswakBuddyPair.user_a == user_id, MiswakBuddyPair.user_b == user_id),
        )
        .values(status="ended", ended_at=now)
    )
    return result.rowcount == 1


async def claim_buddy_nudge(
    session: AsyncSession, user_id: int, pair_id: int, today: date
) -> tuple[str, int | None]:
    pair = await session.scalar(
        select(MiswakBuddyPair)
        .where(
            MiswakBuddyPair.id == pair_id,
            MiswakBuddyPair.status == "active",
            or_(MiswakBuddyPair.user_a == user_id, MiswakBuddyPair.user_b == user_id),
        )
        .with_for_update()
    )
    if pair is None:
        return "unavailable", None
    recipient_id = pair.user_b if pair.user_a == user_id else pair.user_a
    if pair.last_nudge_on == today:
        return "limit", recipient_id
    recipient_active = await session.scalar(
        select(MiswakProfile.user_id).where(
            MiswakProfile.user_id == recipient_id, MiswakProfile.enabled.is_(True)
        )
    )
    if recipient_active is None:
        return "inactive", recipient_id
    pair.last_nudge_on = today
    return "ok", recipient_id


def _activate_due_goal(profile: MiswakProfile, today: date) -> None:
    if (
        profile.next_daily_goal is not None
        and profile.goal_effective_on is not None
        and profile.goal_effective_on <= today
    ):
        profile.daily_goal = profile.next_daily_goal
        profile.next_daily_goal = None
        profile.goal_effective_on = None