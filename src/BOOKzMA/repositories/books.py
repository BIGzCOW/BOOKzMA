from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.constants import MAX_ACTIVE_BOOKS
from BOOKzMA.db.models import PageLog, User, UserBook


@dataclass(frozen=True)
class BookProgress:
    book: UserBook
    pages_read: int


@dataclass(frozen=True)
class PageLogResult:
    status: str
    progress: BookProgress | None = None


async def active_count(session: AsyncSession, user_id: int) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(UserBook)
            .where(UserBook.user_id == user_id, UserBook.status == "reading")
        )
        or 0
    )


async def add(
    session: AsyncSession,
    user_id: int,
    title: str,
    author: str | None,
    total_pages: int,
) -> tuple[str, UserBook | None]:
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())
    if await active_count(session, user_id) >= MAX_ACTIVE_BOOKS:
        return "limit", None
    book = UserBook(
        user_id=user_id,
        title=title,
        author=author,
        total_pages=total_pages,
    )
    session.add(book)
    await session.flush()
    return "ok", book


async def visible_count(session: AsyncSession, user_id: int) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(UserBook)
            .where(UserBook.user_id == user_id, UserBook.status != "archived")
        )
        or 0
    )


async def list_visible(
    session: AsyncSession, user_id: int, *, offset: int, limit: int
) -> list[BookProgress]:
    pages = func.coalesce(func.sum(PageLog.pages_read), 0).label("pages_read")
    result = await session.execute(
        select(UserBook, pages)
        .outerjoin(PageLog, PageLog.user_book_id == UserBook.id)
        .where(UserBook.user_id == user_id, UserBook.status != "archived")
        .group_by(UserBook.id)
        .order_by(
            case((UserBook.status == "reading", 0), else_=1),
            UserBook.created_at.desc(),
            UserBook.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return [BookProgress(book=book, pages_read=int(read)) for book, read in result.all()]


async def get_progress(
    session: AsyncSession, user_id: int, book_id: int
) -> BookProgress | None:
    pages = func.coalesce(func.sum(PageLog.pages_read), 0).label("pages_read")
    row = (
        await session.execute(
            select(UserBook, pages)
            .outerjoin(PageLog, PageLog.user_book_id == UserBook.id)
            .where(UserBook.id == book_id, UserBook.user_id == user_id)
            .group_by(UserBook.id)
        )
    ).one_or_none()
    return BookProgress(book=row[0], pages_read=int(row[1])) if row else None


async def log_pages(
    session: AsyncSession,
    user_id: int,
    book_id: int,
    day: date,
    pages_read: int,
    source_message_id: int,
) -> PageLogResult:
    book = await session.scalar(
        select(UserBook)
        .where(UserBook.id == book_id, UserBook.user_id == user_id)
        .with_for_update()
    )
    if book is None:
        return PageLogResult("missing")

    existing = await session.scalar(
        select(PageLog.id).where(
            PageLog.user_book_id == book.id,
            PageLog.source_message_id == source_message_id,
        )
    )
    current = (
        await session.scalar(
            select(func.coalesce(func.sum(PageLog.pages_read), 0)).where(
                PageLog.user_book_id == book.id
            )
        )
        or 0
    )
    if existing is not None:
        return PageLogResult("duplicate", BookProgress(book, int(current)))
    if book.status != "reading":
        return PageLogResult(book.status, BookProgress(book, int(current)))
    if current + pages_read > book.total_pages:
        return PageLogResult("over", BookProgress(book, int(current)))

    session.add(
        PageLog(
            user_book_id=book.id,
            day=day,
            pages_read=pages_read,
            source_message_id=source_message_id,
        )
    )
    new_total = int(current) + pages_read
    if new_total == book.total_pages:
        book.status = "finished"
        book.finished_at = datetime.now(timezone.utc)
    await session.flush()
    return PageLogResult("ok", BookProgress(book, new_total))


async def archive(session: AsyncSession, user_id: int, book_id: int) -> bool:
    result = await session.execute(
        update(UserBook)
        .where(
            UserBook.id == book_id,
            UserBook.user_id == user_id,
            UserBook.status != "archived",
        )
        .values(status="archived", archived_at=datetime.now(timezone.utc))
    )
    return result.rowcount == 1
