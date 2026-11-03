from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import SupportBlock, SupportEvent, SupportTicket, User


async def open_ticket(session: AsyncSession, user_id: int) -> SupportTicket:
    ticket = await session.scalar(
        select(SupportTicket)
        .where(SupportTicket.user_id == user_id, SupportTicket.status == "open")
        .order_by(SupportTicket.id.desc())
        .limit(1)
    )
    if ticket is not None:
        return ticket
    ticket = SupportTicket(user_id=user_id)
    session.add(ticket)
    await session.flush()
    return ticket


async def get_ticket(session: AsyncSession, ticket_id: int) -> SupportTicket | None:
    return await session.get(SupportTicket, ticket_id)


async def record_message(
    session: AsyncSession, ticket_id: int, actor_id: int, kind: str
) -> None:
    session.add(
        SupportEvent(ticket_id=ticket_id, actor_id=actor_id, kind=kind)
    )
    await session.execute(
        select(SupportTicket.id)
        .where(SupportTicket.id == ticket_id)
        .with_for_update()
    )
    ticket = await session.get(SupportTicket, ticket_id)
    if ticket is not None:
        ticket.updated_at = datetime.now(timezone.utc)
    await session.flush()


async def is_blocked(session: AsyncSession, user_id: int) -> bool:
    return await session.scalar(
        select(SupportBlock.user_id).where(SupportBlock.user_id == user_id)
    ) is not None


async def toggle_block(
    session: AsyncSession, user_id: int, admin_id: int
) -> bool:
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())
    blocked = await is_blocked(session, user_id)
    if blocked:
        await session.execute(delete(SupportBlock).where(SupportBlock.user_id == user_id))
        return False
    session.add(SupportBlock(user_id=user_id, admin_id=admin_id))
    await session.flush()
    return True