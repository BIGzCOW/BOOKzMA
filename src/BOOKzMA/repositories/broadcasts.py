import asyncio
from datetime import datetime, timezone

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import BroadcastCampaign, BroadcastDelivery, MiswakProfile, User

_START_LOCK = asyncio.Lock()


async def create(
    session: AsyncSession,
    admin_id: int,
    text: str,
    audience: str = "all",
    media_type: str | None = None,
    media_file_id: str | None = None,
    button_label: str | None = None,
    button_url: str | None = None,
) -> tuple[int, int]:
    if audience not in {"all", "miswak"}:
        raise ValueError("unsupported broadcast audience")
    if media_type not in {None, "photo", "video"}:
        raise ValueError("unsupported broadcast media type")
    if media_type is not None and not media_file_id:
        raise ValueError("media file id is required for media campaigns")
    campaign = BroadcastCampaign(
        admin_id=admin_id,
        text=text,
        audience=audience,
        media_type=media_type,
        media_file_id=media_file_id,
        button_label=button_label,
        button_url=button_url,
        status="pending",
    )
    session.add(campaign)
    await session.flush()
    statement = select(User.id).where(User.broadcast_unavailable.is_(False))
    if audience == "miswak":
        statement = statement.join(MiswakProfile, MiswakProfile.user_id == User.id).where(
            MiswakProfile.enabled.is_(True)
        )
    result = await session.scalars(statement.order_by(User.id))
    user_ids = list(result)
    session.add_all(
        BroadcastDelivery(campaign_id=campaign.id, user_id=user_id) for user_id in user_ids
    )
    return campaign.id, len(user_ids)


async def eligible_recipient(
    session: AsyncSession, campaign: BroadcastCampaign, user_id: int
) -> bool:
    statement = select(User.id).where(
        User.id == user_id, User.broadcast_unavailable.is_(False)
    )
    if campaign.audience == "miswak":
        statement = statement.join(MiswakProfile, MiswakProfile.user_id == User.id).where(
            MiswakProfile.enabled.is_(True)
        )
    return await session.scalar(statement) is not None


async def start(session: AsyncSession, campaign_id: int, admin_id: int) -> bool:
    async with _START_LOCK:
        active_campaign = await session.scalar(
            select(BroadcastCampaign.id).where(BroadcastCampaign.status == "sending").limit(1)
        )
        if active_campaign is not None:
            return False
        result = await session.execute(
            update(BroadcastCampaign)
            .where(
                BroadcastCampaign.id == campaign_id,
                BroadcastCampaign.admin_id == admin_id,
                BroadcastCampaign.status == "pending",
            )
            .values(status="sending")
        )
        started = result.rowcount == 1
        if started:
            await session.commit()
        return started


async def next_delivery(
    session: AsyncSession,
) -> tuple[BroadcastCampaign, BroadcastDelivery] | None:
    result = await session.execute(
        select(BroadcastCampaign, BroadcastDelivery)
        .join(BroadcastDelivery, BroadcastDelivery.campaign_id == BroadcastCampaign.id)
        .where(
            BroadcastCampaign.status == "sending",
            BroadcastDelivery.status.in_(("pending", "sending")),
            or_(
                BroadcastDelivery.next_attempt_at.is_(None),
                BroadcastDelivery.next_attempt_at <= datetime.now(timezone.utc),
            ),
        )
        .order_by(BroadcastCampaign.id, BroadcastDelivery.id)
        .limit(1)
    )
    return result.first()


async def set_delivery_state(
    session: AsyncSession,
    delivery_id: int,
    state: str,
    error: str | None = None,
    next_attempt_at: datetime | None = None,
) -> None:
    values: dict[str, object] = {
        "status": state,
        "last_error": error,
        "next_attempt_at": next_attempt_at,
    }
    if state == "sent":
        values["sent_at"] = datetime.now(timezone.utc)
    await session.execute(
        update(BroadcastDelivery)
        .where(BroadcastDelivery.id == delivery_id)
        .values(**values)
    )


async def cancel(session: AsyncSession, campaign_id: int, admin_id: int) -> bool:
    campaign = await session.scalar(
        select(BroadcastCampaign).where(
            BroadcastCampaign.id == campaign_id,
            BroadcastCampaign.admin_id == admin_id,
            BroadcastCampaign.status.in_(("pending", "sending")),
        )
    )
    if campaign is None:
        return False
    campaign.status = "cancelled"
    await session.execute(
        update(BroadcastDelivery)
        .where(
            BroadcastDelivery.campaign_id == campaign_id,
            BroadcastDelivery.status.in_(("pending", "sending")),
        )
        .values(status="cancelled")
    )
    return True


async def campaign_counts(session: AsyncSession, campaign_id: int) -> dict[str, int]:
    rows = await session.execute(
        select(BroadcastDelivery.status, func.count())
        .where(BroadcastDelivery.campaign_id == campaign_id)
        .group_by(BroadcastDelivery.status)
    )
    return {state: count for state, count in rows}


async def owned_campaign(
    session: AsyncSession, campaign_id: int, admin_id: int
) -> BroadcastCampaign | None:
    return await session.scalar(
        select(BroadcastCampaign).where(
            BroadcastCampaign.id == campaign_id,
            BroadcastCampaign.admin_id == admin_id,
        )
    )


async def complete_finished_campaigns(session: AsyncSession) -> None:
    campaigns = await session.scalars(
        select(BroadcastCampaign).where(BroadcastCampaign.status == "sending")
    )
    for campaign in campaigns:
        pending = await session.scalar(
            select(func.count()).where(
                BroadcastDelivery.campaign_id == campaign.id,
                BroadcastDelivery.status.in_(("pending", "sending")),
            )
        )
        if not pending:
            campaign.status = "completed"
            campaign.completed_at = datetime.now(timezone.utc)


async def recover_inflight(session: AsyncSession) -> None:
    await session.execute(
        update(BroadcastDelivery)
        .where(
            BroadcastDelivery.status == "sending",
            BroadcastDelivery.campaign_id.in_(
                select(BroadcastCampaign.id).where(BroadcastCampaign.status == "sending")
            ),
        )
        .values(
            status=case(
                (BroadcastDelivery.attempts >= 3, "failed"),
                else_="pending",
            )
        )
    )