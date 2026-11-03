from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import PageLog, User, UserBook


@dataclass(frozen=True)
class BookProgress:
    book: UserBook
    pages_read: int


@dataclass(frozen=True)
class PageLogResult:
    status: str
    progress: BookProgress | None = None


@dataclass(frozen=True)
class ShelfSummary:
    total_count: int
    archived_count: int
    reading_count: int
    finished_count: int
    planned_count: int
    unstarted_count: int
    reading_titles: tuple[str, ...]


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
    total_pages: int | None,
    catalog_message_id: int | None = None,
) -> tuple[str, UserBook | None]:
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())
    if catalog_message_id is not None:
        existing = await session.scalar(
            select(UserBook).where(
                UserBook.user_id == user_id,
                UserBook.catalog_message_id == catalog_message_id,
            )
        )
        if existing is not None:
            return "exists", existing
    book = UserBook(
        user_id=user_id,
        title=title,
        author=author,
        total_pages=total_pages,
        status="planned" if catalog_message_id is not None else "reading",
        catalog_message_id=catalog_message_id,
        page_count_set_at=datetime.now(timezone.utc) if total_pages is not None else None,
    )
    session.add(book)
    await session.flush()
    return "ok", book


async def set_total_pages(
    session: AsyncSession, user_id: int, book_id: int, total_pages: int
) -> tuple[str, BookProgress | None]:
    book = await session.scalar(
        select(UserBook)
        .where(UserBook.id == book_id, UserBook.user_id == user_id)
        .with_for_update()
    )
    if book is None:
        return "missing", None
    current = (
        await session.scalar(
            select(func.coalesce(func.sum(PageLog.pages_read), 0)).where(
                PageLog.user_book_id == book_id
            )
        )
        or 0
    )
    if book.total_pages is not None:
        return "already_set", BookProgress(book, int(current))
    if current > total_pages:
        return "under_progress", BookProgress(book, int(current))
    book.total_pages = total_pages
    book.status = "reading"
    book.page_count_set_at = datetime.now(timezone.utc)
    await session.flush()
    return "ok", BookProgress(book, int(current))


async def visible_count(
    session: AsyncSession, user_id: int, *, archived: bool = False
) -> int:
    status_filter = UserBook.status == "archived" if archived else UserBook.status != "archived"
    return (
        await session.scalar(
            select(func.count())
            .select_from(UserBook)
            .where(UserBook.user_id == user_id, status_filter)
        )
        or 0
    )


async def shelf_summary(
    session: AsyncSession, user_id: int, *, title_limit: int = 5
) -> ShelfSummary:
    page_totals = (
        select(
            PageLog.user_book_id.label("book_id"),
            func.sum(PageLog.pages_read).label("pages_read"),
        )
        .group_by(PageLog.user_book_id)
        .subquery()
    )
    pages_read = func.coalesce(page_totals.c.pages_read, 0)
    counts = (
        await session.execute(
            select(
                func.count(UserBook.id),
                func.count(UserBook.id).filter(UserBook.status == "archived"),
                func.count(UserBook.id).filter(UserBook.status == "finished"),
                func.count(UserBook.id).filter(UserBook.status == "planned"),
                func.count(UserBook.id).filter(
                    and_(UserBook.status == "reading", pages_read > 0)
                ),
                func.count(UserBook.id).filter(
                    and_(UserBook.status == "reading", pages_read == 0)
                ),
            )
            .select_from(UserBook)
            .outerjoin(page_totals, page_totals.c.book_id == UserBook.id)
            .where(UserBook.user_id == user_id)
        )
    ).one()
    titles = await session.scalars(
        select(UserBook.title)
        .join(page_totals, page_totals.c.book_id == UserBook.id)
        .where(
            UserBook.user_id == user_id,
            UserBook.status == "reading",
            page_totals.c.pages_read > 0,
        )
        .order_by(UserBook.created_at.desc(), UserBook.id.desc())
        .limit(title_limit)
    )
    return ShelfSummary(
        total_count=counts[0],
        archived_count=counts[1],
        reading_count=counts[4],
        finished_count=counts[2],
        planned_count=counts[3],
        unstarted_count=counts[5],
        reading_titles=tuple(titles.all()),
    )


async def list_visible(
    session: AsyncSession,
    user_id: int,
    *,
    offset: int,
    limit: int,
    archived: bool = False,
) -> list[BookProgress]:
    pages = func.coalesce(func.sum(PageLog.pages_read), 0).label("pages_read")
    status_filter = UserBook.status == "archived" if archived else UserBook.status != "archived"
    result = await session.execute(
        select(UserBook, pages)
        .outerjoin(PageLog, PageLog.user_book_id == UserBook.id)
        .where(UserBook.user_id == user_id, status_filter)
        .group_by(UserBook.id)
        .order_by(
            case(
                (UserBook.status == "reading", 0),
                (UserBook.status == "planned", 1),
                (UserBook.status == "finished", 2),
                else_=3,
            ),
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
    if book.total_pages is None:
        return PageLogResult("pages_missing", BookProgress(book, int(current)))
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

async def restore(session: AsyncSession, user_id: int, book_id: int) -> bool:
    book = await session.scalar(
        select(UserBook)
        .where(
            UserBook.id == book_id,
            UserBook.user_id == user_id,
            UserBook.status == "archived",
        )
        .with_for_update()
    )
    if book is None:
        return False
    if book.finished_at is not None:
        book.status = "finished"
    elif book.total_pages is None:
        book.status = "planned"
    else:
        book.status = "reading"
    book.restored_at = datetime.now(timezone.utc)
    await session.flush()
    return True
