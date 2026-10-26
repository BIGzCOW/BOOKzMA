import logging
import re
from urllib.parse import urlsplit

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.config import Settings
from BOOKzMA.handlers.common import show
from BOOKzMA.repositories import analytics, broadcasts
from BOOKzMA.services import backup as backup_service
from BOOKzMA.services.backup import BackupError
from BOOKzMA.utils import local_today

router = Router()
log = logging.getLogger(__name__)
MAX_BROADCAST_LENGTH = 3500
RESTORE_INDEX_RE = re.compile(r"admin:restore_(ask|ready):(\d{1,3})")


class NewBroadcast(StatesGroup):
    waiting_for_content = State()
    waiting_for_link = State()


class BackupRestore(StatesGroup):
    waiting_for_confirm = State()


def is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_ids


def _authorize(user_id: int, settings: Settings, action: str) -> bool:
    allowed = is_admin(user_id, settings)
    log.info("admin authorization action=%s actor=%s allowed=%s", action, user_id, allowed)
    return allowed


async def show_admin(event: Message | CallbackQuery, session: AsyncSession) -> None:
    today = local_today("UTC")
    stats = await analytics.dashboard(session, today)
    series = await analytics.activity_series(session, today)
    text = texts.admin_dashboard(stats, series)
    await show(event, text, keyboards.admin_kb())


@router.message(Command("admin"))
@router.message(F.text == "⚙️ مدیریت ربات")
async def on_admin(message: Message, session: AsyncSession, settings: Settings) -> None:
    if not message.from_user or not _authorize(message.from_user.id, settings, "open_panel"):
        await message.answer("این بخش فقط برای مدیر رباته.")
        return
    await show_admin(message, session)


@router.callback_query(F.data == "admin:stats")
async def on_admin_stats(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not _authorize(callback.from_user.id, settings, "view_stats"):
        await callback.answer("دسترسی نداری.", show_alert=True)
        return
    await callback.answer()
    await show_admin(callback, session)


@router.callback_query(F.data == "admin:broadcast")
async def on_broadcast_start(
    callback: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    if not _authorize(callback.from_user.id, settings, "create_broadcast"):
        await callback.answer("دسترسی نداری.", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    await show(
        callback,
        "مخاطب این کمپین رو انتخاب کن:",
        keyboards.broadcast_audience_kb(),
    )


@router.callback_query(F.data.startswith("broadcast:audience:"))
async def on_broadcast_audience(
    callback: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    if not _authorize(callback.from_user.id, settings, "select_broadcast_audience"):
        await callback.answer("دسترسی نداری.", show_alert=True)
        return
    match = re.fullmatch(r"broadcast:audience:(all|miswak)", callback.data or "")
    if match is None:
        await callback.answer("مخاطب معتبر نیست.", show_alert=True)
        return
    await state.update_data(audience=match[1])
    await state.set_state(NewBroadcast.waiting_for_content)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "متن، عکس یا ویدئوی کمپین رو بفرست.\n"
            f"متن حداکثر {MAX_BROADCAST_LENGTH} نویسه و کپشن حداکثر ۱۰۰۰ نویسه."
        )


@router.message(NewBroadcast.waiting_for_content, F.text | F.photo | F.video)
async def on_broadcast_content(
    message: Message, session: AsyncSession, state: FSMContext, settings: Settings
) -> None:
    if not message.from_user or not _authorize(message.from_user.id, settings, "draft_broadcast"):
        await state.clear()
        return
    media_type = None
    media_file_id = None
    text = message.text or message.caption or ""
    if message.photo:
        media_type = "photo"
        media_file_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        media_file_id = message.video.file_id
    max_length = 1000 if media_type else MAX_BROADCAST_LENGTH
    if (not text.strip() and media_type is None) or len(text) > max_length:
        await message.answer("محتوا خالیه یا از سقف طول مجاز بیشتره؛ دوباره بفرست.")
        return
    await state.update_data(text=text, media_type=media_type, media_file_id=media_file_id)
    await state.set_state(NewBroadcast.waiting_for_link)
    await message.answer(
        "اگر دکمهٔ لینک می‌خواهی، آدرس HTTPS را بفرست؛ برای ادامه بدون دکمه «رد» را بفرست."
    )


def _valid_broadcast_url(value: str) -> bool:
    if len(value) > 2048 or any(ord(char) < 32 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.port != 0
        )
    except ValueError:
        return False


@router.message(NewBroadcast.waiting_for_link, F.text)
async def on_broadcast_link(
    message: Message, session: AsyncSession, state: FSMContext, settings: Settings
) -> None:
    if not message.from_user or not _authorize(message.from_user.id, settings, "draft_broadcast"):
        await state.clear()
        return
    raw_link = (message.text or "").strip()
    button_url = None
    button_label = None
    if raw_link.lower() not in {"رد", "بدون لینک"}:
        if not _valid_broadcast_url(raw_link):
            await message.answer("فقط لینک HTTPS معتبر بفرست یا «رد» رو انتخاب کن.")
            return
        button_url = raw_link
        button_label = "مشاهده"

    data = await state.get_data()
    audience = data.get("audience")
    if audience not in {"all", "miswak"}:
        await state.clear()
        await message.answer("پیش‌نویس پیدا نشد؛ از پنل مدیریت دوباره شروع کن.")
        return
    text = str(data.get("text", ""))
    media_type = data.get("media_type")
    media_file_id = data.get("media_file_id")
    campaign_id, recipient_count = await broadcasts.create(
        session,
        message.from_user.id,
        text,
        audience=audience,
        media_type=media_type,
        media_file_id=media_file_id,
        button_label=button_label,
        button_url=button_url,
    )
    await session.commit()
    await state.clear()
    audience_label = "اعضای فعال مسباک" if audience == "miswak" else "همهٔ کاربران"
    content_label = {"photo": "عکس", "video": "ویدئو"}.get(media_type, "متن")
    preview = (
        f"پیش‌نمایش کمپین · {audience_label}\n"
        f"نوع محتوا: {content_label}\n\n{text or 'بدون کپشن'}\n\n"
        f"مخاطب هنگام ساخت: {recipient_count} نفر\n"
        f"دکمهٔ لینک: {'دارد' if button_url else 'ندارد'}\n"
        "برای شروع ارسال تأیید کن."
    )
    await message.answer(
        preview,
        reply_markup=keyboards.broadcast_confirm_kb(campaign_id),
        parse_mode=None,
    )


def _campaign_id(callback_data: str, action: str) -> int | None:
    match = re.fullmatch(rf"broadcast:{action}:(\d{{1,10}})", callback_data)
    if match is None:
        return None
    campaign_id = int(match[1])
    return campaign_id if campaign_id <= 2_147_483_647 else None


@router.callback_query(F.data.startswith("broadcast:status:"))
async def on_broadcast_status(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not _authorize(callback.from_user.id, settings, "broadcast_status"):
        await callback.answer("دسترسی نداری.", show_alert=True)
        return
    campaign_id = _campaign_id(callback.data or "", "status")
    campaign = (
        await broadcasts.owned_campaign(session, campaign_id, callback.from_user.id)
        if campaign_id is not None
        else None
    )
    if campaign is None:
        await callback.answer("کمپین پیدا نشد.", show_alert=True)
        return
    counts = await broadcasts.campaign_counts(session, campaign.id)
    total = sum(counts.values())
    summary = (
        f"وضعیت: {campaign.status}\n"
        f"کل: {total} · ارسال‌شده: {counts.get('sent', 0)} · "
        f"در صف: {counts.get('pending', 0) + counts.get('sending', 0)} · "
        f"ناموفق: {counts.get('failed', 0)} · لغوشده: {counts.get('cancelled', 0)}"
    )
    await callback.answer(summary, show_alert=True)


@router.callback_query(F.data.startswith("broadcast:start:"))
async def on_broadcast_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not _authorize(callback.from_user.id, settings, "confirm_broadcast"):
        await callback.answer("دسترسی نداری.", show_alert=True)
        return
    campaign_id = _campaign_id(callback.data or "", "start")
    if campaign_id is None or not await broadcasts.start(
        session, campaign_id, callback.from_user.id
    ):
        await callback.answer(
            "کمپین پیدا نشد، قبلاً تأیید شده یا یک ارسال دیگر در جریانه.",
            show_alert=True,
        )
        return
    await session.commit()
    await callback.answer("ارسال در صف قرار گرفت.")
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(
            reply_markup=keyboards.broadcast_cancel_kb(campaign_id)
        )


@router.callback_query(F.data.startswith("broadcast:cancel:"))
async def on_broadcast_cancel(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not _authorize(callback.from_user.id, settings, "cancel_broadcast"):
        await callback.answer("دسترسی نداری.", show_alert=True)
        return
    campaign_id = _campaign_id(callback.data or "", "cancel")
    if campaign_id is None or not await broadcasts.cancel(
        session, campaign_id, callback.from_user.id
    ):
        await callback.answer("این کمپین پیدا نشد یا تمام شده.", show_alert=True)
        return
    await session.commit()
    await callback.answer("ارسال لغو شد.")


def _restore_index(callback_data: str, action: str) -> int | None:
    match = re.fullmatch(rf"admin:restore_{action}:(\d{{1,3}})", callback_data or "")
    if match is None:
        return None
    return int(match[1])


def _backup_name(settings: Settings, index: int | None) -> str | None:
    """نام فایل هرگز از ورودی آزاد گرفته نمی‌شود؛ فقط از فهرست واقعی فایل‌ها با ایندکس."""
    if index is None:
        return None
    infos = backup_service.list_backups(settings)
    return infos[index].name if 0 <= index < len(infos) else None


@router.callback_query(F.data == "admin:backup")
async def on_backup_menu(
    callback: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    if not _authorize(callback.from_user.id, settings, "backup_menu"):
        await callback.answer("دسترسی نداری.", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    text = (
        texts.backup_status(backup_service.list_backups(settings))
        + "\n\n"
        + texts.admin_backup_hint()
    )
    await show(callback, text, keyboards.backup_kb())


@router.callback_query(F.data == "admin:backup_now")
async def on_backup_now(callback: CallbackQuery, settings: Settings) -> None:
    if not _authorize(callback.from_user.id, settings, "backup_now"):
        await callback.answer("دسترسی نداری.", show_alert=True)
        return
    await callback.answer(texts.BACKUP_RUNNING)
    log.info("admin backup action=backup_now actor=%s", callback.from_user.id)
    try:
        info = await backup_service.run_backup(settings)
    except BackupError:
        log.exception("admin backup action=backup_now failed actor=%s", callback.from_user.id)
        if isinstance(callback.message, Message):
            await callback.message.answer(texts.BACKUP_FAILED)
        return
    if isinstance(callback.message, Message):
        await callback.message.answer(texts.backup_done(info.name, info.size_bytes))


@router.callback_query(F.data == "admin:backup_restore")
async def on_backup_restore_list(
    callback: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    if not _authorize(callback.from_user.id, settings, "backup_restore_list"):
        await callback.answer("دسترسی نداری.", show_alert=True)
        return
    await state.clear()
    infos = backup_service.list_backups(settings)
    if not infos:
        await callback.answer(texts.BACKUP_NONE, show_alert=True)
        return
    await callback.answer()
    await show(
        callback,
        texts.backup_list(infos),
        keyboards.backup_list_kb([info.name for info in infos]),
    )


@router.callback_query(F.data.startswith("admin:restore_ask:"))
async def on_restore_ask(callback: CallbackQuery, settings: Settings) -> None:
    if not _authorize(callback.from_user.id, settings, "restore_ask"):
        await callback.answer("دسترسی نداری.", show_alert=True)
        return
    index = _restore_index(callback.data or "", "ask")
    name = _backup_name(settings, index)
    if name is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    await callback.answer()
    await show(callback, texts.restore_warn(name), keyboards.restore_warn_kb(index or 0))


@router.callback_query(F.data.startswith("admin:restore_ready:"))
async def on_restore_ready(
    callback: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    if not _authorize(callback.from_user.id, settings, "restore_ready"):
        await callback.answer("دسترسی نداری.", show_alert=True)
        return
    index = _restore_index(callback.data or "", "ready")
    name = _backup_name(settings, index)
    if name is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    await state.set_state(BackupRestore.waiting_for_confirm)
    await state.update_data(restore_file=name)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            texts.RESTORE_CONFIRM, reply_markup=keyboards.restore_confirm_kb()
        )


@router.message(BackupRestore.waiting_for_confirm, F.text)
async def on_restore_confirm(
    message: Message, state: FSMContext, settings: Settings
) -> None:
    if not message.from_user or not _authorize(
        message.from_user.id, settings, "restore_confirm"
    ):
        await state.clear()
        return
    if (message.text or "").strip() != texts.RESTORE_WORD:
        await message.answer(texts.RESTORE_BAD_WORD)
        return
    data = await state.get_data()
    name = data.get("restore_file")
    await state.clear()
    if not isinstance(name, str):
        await message.answer(texts.INVALID_ACTION)
        return
    log.info("admin backup action=restore actor=%s file=%s", message.from_user.id, name)
    await message.answer(texts.RESTORE_RUNNING)
    try:
        await backup_service.run_restore(settings, name)
    except BackupError:
        log.exception(
            "admin backup action=restore failed actor=%s file=%s", message.from_user.id, name
        )
        await message.answer(texts.RESTORE_FAILED)
        return
    log.info("admin backup action=restore done actor=%s file=%s", message.from_user.id, name)
    await message.answer(texts.RESTORE_DONE)
