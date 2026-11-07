from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import (
    FreezeGiftOperation,
    FreezeGiftRecipient,
    MesbakProfile,
    StreakFreeze,
    User,
)

FREEZE_CAP = 3
MAX_GIFT_AMOUNT = 1000


@dataclass(frozen=True)
class FreezeGiftSummary:
    status: str
    operation_id: int
    habit: str
    requested_amount: int
    recipients: int
    units: int
    capped: int
    skipped: int


def _summary(operation: FreezeGiftOperation, status: str | None = None) -> FreezeGiftSummary:
    return FreezeGiftSummary(
        status=status or operation.status,
        operation_id=operation.id,
        habit=operation.habit,
        requested_amount=operation.requested_amount,
        recipients=operation.preview_recipients,
        units=operation.preview_units,
        capped=operation.preview_capped,
        skipped=operation.preview_skipped,
    )


async def _eligible_user_ids(
    session: AsyncSession, habit: str, *, user_ids: list[int] | None = None
) -> list[int]:
    if habit == "reading":
        statement = select(User.id)
    else:
        statement = (
            select(User.id)
            .join(MesbakProfile, MesbakProfile.user_id == User.id)
            .where(MesbakProfile.enabled.is_(True))
        )
    if user_ids is not None:
        statement = statement.where(User.id.in_(user_ids))
    return list(await session.scalars(statement.order_by(User.id)))


async def _balances(
    session: AsyncSession, user_ids: list[int], habit: str
) -> dict[int, int]:
    if not user_ids:
        return {}
    credits = func.coalesce(
        func.sum(
            case(
                (StreakFreeze.kind.in_({"earned", "gifted"}), StreakFreeze.quantity),
                else_=0,
            )
        ),
        0,
    )
    used = func.coalesce(
        func.sum(case((StreakFreeze.kind == "used", StreakFreeze.quantity), else_=0)),
        0,
    )
    rows = await session.execute(
        select(StreakFreeze.user_id, credits, used)
        .where(
            StreakFreeze.habit == habit,
            StreakFreeze.user_id.in_(user_ids),
        )
        .group_by(StreakFreeze.user_id)
    )
    return {user_id: max(0, int(earned) - int(spent)) for user_id, earned, spent in rows}


def _grant_units(amount: int, balance: int) -> int:
    return min(amount, max(0, FREEZE_CAP - balance))


async def create_preview(
    session: AsyncSession, admin_id: int, habit: str, amount: int
) -> FreezeGiftSummary:
    if habit not in {"reading", "mesbak"}:
        raise ValueError("invalid Freeze habit")
    if isinstance(amount, bool) or not 1 <= amount <= MAX_GIFT_AMOUNT:
        raise ValueError("Freeze gift amount is out of range")

    audience = "all" if habit == "reading" else "mesbak"
    operation = FreezeGiftOperation(
        admin_id=admin_id,
        habit=habit,
        audience=audience,
        requested_amount=amount,
    )
    session.add(operation)
    await session.flush()

    user_ids = await _eligible_user_ids(session, habit)
    balances = await _balances(session, user_ids, habit)
    recipients = []
    total_units = 0
    capped = 0
    for user_id in user_ids:
        units = _grant_units(amount, balances.get(user_id, 0))
        total_units += units
        capped += units == 0
        recipients.append(
            FreezeGiftRecipient(
                operation_id=operation.id,
                user_id=user_id,
                preview_units=units,
                status="pending" if units else "capped",
            )
        )
    session.add_all(recipients)
    operation.preview_recipients = len(user_ids)
    operation.preview_units = total_units
    operation.preview_capped = capped
    await session.flush()
    return _summary(operation)


async def confirm(
    session: AsyncSession,
    admin_id: int,
    operation_id: int,
    now: datetime,
) -> FreezeGiftSummary | None:
    operation = await session.scalar(
        select(FreezeGiftOperation)
        .where(FreezeGiftOperation.id == operation_id, FreezeGiftOperation.admin_id == admin_id)
        .with_for_update()
    )
    if operation is None:
        return None
    if operation.status != "pending":
        return _summary(operation)

    recipients = list(
        await session.scalars(
            select(FreezeGiftRecipient)
            .where(FreezeGiftRecipient.operation_id == operation.id)
            .order_by(FreezeGiftRecipient.user_id)
            .with_for_update()
        )
    )
    snapshot_ids = [recipient.user_id for recipient in recipients]
    if snapshot_ids:
        await session.scalars(
            select(User.id)
            .where(User.id.in_(snapshot_ids))
            .order_by(User.id)
            .with_for_update()
        )
        if operation.habit == "mesbak":
            await session.scalars(
                select(MesbakProfile.user_id)
                .where(MesbakProfile.user_id.in_(snapshot_ids))
                .order_by(MesbakProfile.user_id)
                .with_for_update()
            )
    eligible_ids = await _eligible_user_ids(
        session, operation.habit, user_ids=snapshot_ids
    )
    eligible = set(eligible_ids)
    balances = await _balances(session, eligible_ids, operation.habit)

    preview_units = 0
    preview_capped = 0
    preview_skipped = 0
    changed = len(eligible_ids) != operation.preview_recipients
    for recipient in recipients:
        if recipient.user_id not in eligible:
            new_units = 0
            new_status = "skipped"
            preview_skipped += 1
        else:
            new_units = _grant_units(
                operation.requested_amount, balances.get(recipient.user_id, 0)
            )
            new_status = "pending" if new_units else "capped"
            preview_units += new_units
            preview_capped += new_units == 0
        if recipient.preview_units != new_units or recipient.status != new_status:
            changed = True
            recipient.preview_units = new_units
            recipient.status = new_status

    if (
        changed
        or preview_units != operation.preview_units
        or preview_capped != operation.preview_capped
        or preview_skipped != operation.preview_skipped
    ):
        operation.preview_recipients = len(eligible_ids)
        operation.preview_units = preview_units
        operation.preview_capped = preview_capped
        operation.preview_skipped = preview_skipped
        return _summary(operation, status="changed")

    for recipient in recipients:
        if recipient.preview_units == 0:
            continue
        session.add(
            StreakFreeze(
                user_id=recipient.user_id,
                habit=operation.habit,
                kind="gifted",
                quantity=recipient.preview_units,
                day=now.date(),
                operation_id=operation.id,
            )
        )
        recipient.credited_units = recipient.preview_units
        recipient.status = "credited"

    operation.status = "completed"
    operation.credited_recipients = sum(item.credited_units > 0 for item in recipients)
    operation.credited_units = sum(item.credited_units for item in recipients)
    operation.capped_recipients = sum(item.status == "capped" for item in recipients)
    operation.skipped_recipients = sum(item.status == "skipped" for item in recipients)
    operation.completed_at = now
    await session.flush()
    return _summary(operation)


async def cancel(
    session: AsyncSession, admin_id: int, operation_id: int
) -> bool:
    operation = await session.scalar(
        select(FreezeGiftOperation)
        .where(FreezeGiftOperation.id == operation_id, FreezeGiftOperation.admin_id == admin_id)
        .with_for_update()
    )
    if operation is None or operation.status != "pending":
        return False
    operation.status = "cancelled"
    await session.flush()
    return True
