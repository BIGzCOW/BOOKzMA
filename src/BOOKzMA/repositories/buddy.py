"""Repository رفیق مطالعه (C-06): صف، جفت‌شدن قفل‌شده، تلنگر و پایان هم‌یاری."""

from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import BuddyInvite, BuddyPair, BuddyQueue, User


async def active_pair(
    session: AsyncSession, user_id: int
) -> tuple[BuddyPair, int] | None:
    """Return one active pair for compatibility with single-pair callers."""
    pairs = await active_pairs(session, user_id)
    return pairs[0] if pairs else None


async def active_pairs(session: AsyncSession, user_id: int) -> list[tuple[BuddyPair, int]]:
    """Return every active pair and the other user's ID."""
    result = await session.scalars(
        select(BuddyPair).where(
            BuddyPair.status == "active",
            (BuddyPair.user_a == user_id) | (BuddyPair.user_b == user_id),
        ).order_by(BuddyPair.id)
    )
    return [
        (pair, pair.user_b if pair.user_a == user_id else pair.user_a) for pair in result
    ]


async def active_buddy_users(session: AsyncSession, user_id: int) -> list[tuple[BuddyPair, User]]:
    pairs = await active_pairs(session, user_id)
    if not pairs:
        return []
    buddy_ids = {buddy_id for _pair, buddy_id in pairs}
    buddies = await session.scalars(select(User).where(User.id.in_(buddy_ids)))
    buddy_by_id = {buddy.id: buddy for buddy in buddies}
    return [(pair, buddy_by_id[buddy_id]) for pair, buddy_id in pairs if buddy_id in buddy_by_id]


async def active_pair_for_user(
    session: AsyncSession, user_id: int, pair_id: int
) -> tuple[BuddyPair, int] | None:
    pair = await session.scalar(
        select(BuddyPair).where(
            BuddyPair.id == pair_id,
            BuddyPair.status == "active",
            (BuddyPair.user_a == user_id) | (BuddyPair.user_b == user_id),
        )
    )
    if pair is None:
        return None
    return pair, pair.user_b if pair.user_a == user_id else pair.user_a


async def is_queued(session: AsyncSession, user_id: int) -> bool:
    return (
        await session.scalar(select(BuddyQueue.user_id).where(BuddyQueue.user_id == user_id))
        is not None
    )


async def join_queue(session: AsyncSession, user_id: int) -> bool:
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())
    await session.execute(
        insert(BuddyQueue).values(user_id=user_id).on_conflict_do_nothing(index_elements=["user_id"])
    )
    return True


async def create_invite(
    session: AsyncSession, inviter_id: int, token_hash: str, expires_at: datetime
) -> bool:
    await session.execute(select(User.id).where(User.id == inviter_id).with_for_update())
    if await is_queued(session, inviter_id):
        return False
    await session.execute(delete(BuddyInvite).where(BuddyInvite.inviter_id == inviter_id))
    session.add(
        BuddyInvite(token_hash=token_hash, inviter_id=inviter_id, expires_at=expires_at)
    )
    return True


async def redeem_invite(
    session: AsyncSession, token_hash: str, recipient_id: int, now: datetime
) -> tuple[str, int | None]:
    snapshot = await session.get(BuddyInvite, token_hash)
    if snapshot is None:
        return "invalid", None

    user_ids = sorted({snapshot.inviter_id, recipient_id})
    locked_ids = await session.scalars(
        select(User.id).where(User.id.in_(user_ids)).order_by(User.id).with_for_update()
    )
    if set(locked_ids) != set(user_ids):
        return "invalid", None

    invite = await session.scalar(
        select(BuddyInvite)
        .where(BuddyInvite.token_hash == token_hash)
        .with_for_update()
    )
    if invite is None:
        return "invalid", None
    if invite.inviter_id == recipient_id:
        return "self", None
    if invite.expires_at <= now:
        await session.execute(delete(BuddyInvite).where(BuddyInvite.token_hash == token_hash))
        return "invalid", None
    if any([await is_queued(session, user_id) for user_id in user_ids]):
        return "busy", None

    inviter_id = invite.inviter_id
    existing_pair_id = await session.scalar(
        select(BuddyPair.id).where(
            BuddyPair.status == "active",
            BuddyPair.user_a == min(inviter_id, recipient_id),
            BuddyPair.user_b == max(inviter_id, recipient_id),
        )
    )
    if existing_pair_id is not None:
        await session.execute(delete(BuddyInvite).where(BuddyInvite.token_hash == token_hash))
        return "already", inviter_id

    await session.execute(delete(BuddyInvite).where(BuddyInvite.token_hash == token_hash))
    session.add(
        BuddyPair(user_a=min(inviter_id, recipient_id), user_b=max(inviter_id, recipient_id))
    )
    return "accepted", inviter_id


async def leave_queue(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(BuddyQueue).where(BuddyQueue.user_id == user_id))


async def try_match(session: AsyncSession, user_id: int) -> int | None:
    """جفت‌کردن کاربر با قدیمی‌ترین نفر صف؛ باید داخل تراکنش قفل‌شده صدا زده شود.

    ردیف‌های صف row-lock می‌شوند تا دو تراکنش هم‌زمان یک نفر را دوبار جفت نکنند.
    """
    existing_pair = select(BuddyPair.id).where(
        BuddyPair.status == "active",
        (
            (BuddyPair.user_a == user_id) & (BuddyPair.user_b == BuddyQueue.user_id)
        )
        | (
            (BuddyPair.user_b == user_id) & (BuddyPair.user_a == BuddyQueue.user_id)
        ),
    )
    rows = await session.scalars(
        select(BuddyQueue.user_id)
        .where(BuddyQueue.user_id != user_id, ~existing_pair.exists())
        .order_by(BuddyQueue.joined_at, BuddyQueue.user_id)
        .with_for_update()
    )
    partner = next(iter(rows), None)
    if partner is None:
        return None
    await session.execute(
        delete(BuddyQueue).where(BuddyQueue.user_id.in_([user_id, partner]))
    )
    session.add(
        BuddyPair(user_a=min(user_id, partner), user_b=max(user_id, partner))
    )
    return partner


async def end_pair(session: AsyncSession, pair: BuddyPair, ended_by: int) -> None:
    await session.execute(
        update(BuddyPair)
        .where(BuddyPair.id == pair.id, BuddyPair.status == "active")
        .values(status="ended", ended_at=datetime.now(timezone.utc), ended_by=ended_by)
    )


async def register_nudge(session: AsyncSession, pair: BuddyPair, day: date) -> bool:
    """سقف روزانه: هر جفت حداکثر یک تلنگر در هر روز محلی."""
    result = await session.execute(
        update(BuddyPair)
        .where(
            BuddyPair.id == pair.id,
            BuddyPair.status == "active",
            (BuddyPair.last_nudge_on.is_(None)) | (BuddyPair.last_nudge_on != day),
        )
        .values(last_nudge_on=day)
        .returning(BuddyPair.id)
    )
    return result.first() is not None


async def stats(session: AsyncSession) -> dict[str, int]:
    """KPI ادمین: جفت‌های فعال و کل جفت‌های تشکیل‌شده."""
    active = (
        await session.scalar(
            select(func.count()).select_from(BuddyPair).where(BuddyPair.status == "active")
        )
        or 0
    )
    total = await session.scalar(select(func.count()).select_from(BuddyPair)) or 0
    return {"buddy_pairs_active": active, "buddy_pairs_total": total}
