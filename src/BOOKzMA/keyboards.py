from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from urllib.parse import quote, urlencode

from BOOKzMA.constants import (
    DELETE_REASONS,
    MAX_REMINDERS,
    MESBAK_PRESET_TIMES,
    PRESET_TIMES,
    TIMEZONES,
)


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def join_kb(missing: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"عضویت در {ch}", url=f"https://t.me/{ch.lstrip('@')}")]
        for ch in missing
    ]
    rows.append([_btn("✅ عضو شدم", "check_join")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def home_kb(read_today: bool, mesbak_active: bool = False) -> InlineKeyboardMarkup:
    read_text = "✅ امروز ثبت شد" if read_today else "📖 امروز خوندم"
    rows = [
        [_btn(read_text, "read")],
        [_btn("📚 کتابخانهٔ من", "books")],
        [_btn("📊 خلاصهٔ هفتگی", "weekly")],
        [_btn("⏰ یادآورها", "rem"), _btn("🌍 منطقه زمانی", "tz")],
    ]
    if mesbak_active:
        rows.append([_btn("🪥 استریک مسباک", "mesbak:open")])
    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def menu_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🏠 خانه"), KeyboardButton(text="👤 پروفایل")],
        [KeyboardButton(text="📚 کتابخانهٔ من")],
        [KeyboardButton(text="⏰ یادآورها"), KeyboardButton(text="🌍 منطقه زمانی")],
        [KeyboardButton(text="🤝 رفیق مطالعه")],
        [KeyboardButton(text="🪥 مسباک")],
        [KeyboardButton(text="💚 حمایت از پروژه")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="⚙️ مدیریت ربات")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def bookshelf_kb(
    items: list[tuple[int, str, str]],
    *,
    page: int,
    has_previous: bool,
    has_next: bool,
    can_add: bool,
) -> InlineKeyboardMarkup:
    rows = [
        [_btn(f"{'📖' if status == 'reading' else '✅'} {title[:32]}", f"book:open:{book_id}")]
        for book_id, title, status in items
    ]
    if can_add:
        rows.append([_btn("➕ افزودن کتاب", "book:add")])
    pagination = []
    if has_previous:
        pagination.append(_btn("قبلی", f"books:p:{page - 1}"))
    if has_next:
        pagination.append(_btn("بعدی", f"books:p:{page + 1}"))
    if pagination:
        rows.append(pagination)
    rows.append([_btn("🏠 منوی اصلی", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def books_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("🔙 انصراف", "books")]])


def book_author_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("رد کردن نام نویسنده", "book:author_skip")],
            [_btn("🔙 انصراف", "books")],
        ]
    )


def book_detail_kb(book_id: int, status: str) -> InlineKeyboardMarkup:
    rows = []
    if status == "reading":
        rows.append([_btn("📖 ثبت صفحات مطالعه‌شده", f"book:log:{book_id}")])
    rows.extend(
        [
            [_btn("🗄 آرشیو کتاب", f"book:archive:{book_id}")],
            [_btn("🔙 کتابخانهٔ من", "books")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def book_archive_confirm_kb(book_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("بله، آرشیو شود", f"book:archive_go:{book_id}")],
            [_btn("🔙 برگشت", f"book:open:{book_id}")],
        ]
    )


def profile_kb(opt_out: bool, mesbak_active: bool = False) -> InlineKeyboardMarkup:
    toggle_text = "➖ خروج از لیدربورد" if not opt_out else "➕ حضور در لیدربورد"
    rows = [
        [_btn(toggle_text, "leaderboard:toggle")],
        [_btn("🏅 لیدربورد استریک", "leaderboard")],
    ]
    if mesbak_active:
        rows.append([_btn("🪥 استریک مسباک", "mesbak:open")])
    rows.extend([[_btn("🗑 حذف حساب", "account_del:start")], [_btn("🏠 منوی اصلی", "home")]])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def account_delete_warn_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("ادامه می‌دم", "account_del:why")],
            [_btn("🔙 انصراف", "account_del:cancel")],
        ]
    )


def account_delete_reasons_kb() -> InlineKeyboardMarkup:
    buttons = [
        _btn(label, f"account_del:reason:{i}") for i, (_code, label) in enumerate(DELETE_REASONS)
    ]
    rows = _chunk(buttons, 2)
    rows.append([_btn("🔙 انصراف", "account_del:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def account_delete_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("🔙 انصراف", "account_del:cancel")]])


def account_delete_final_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("بله، همه‌چیز پاک شود", "account_del:go")],
            [_btn("🔙 انصراف", "account_del:cancel")],
        ]
    )


def restore_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("شروع", "account_restore")]])


def support_kb(github_url: str, support_url: str) -> InlineKeyboardMarkup:
    rows = []
    if github_url:
        rows.append([InlineKeyboardButton(text="⭐ گیت‌هاب پروژه", url=github_url)])
    if support_url:
        rows.append([InlineKeyboardButton(text="💌 حمایت مالی", url=support_url)])
    rows.append([_btn("🏠 منوی اصلی", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("📊 آمار بات", "admin:stats"), _btn("💾 بکاپ", "admin:backup")],
            [_btn("📣 پیام همگانی", "admin:broadcast")],
        ]
    )


def broadcast_audience_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("👥 همهٔ کاربران", "broadcast:audience:all")],
            [_btn("🪥 اعضای فعال مسباک", "broadcast:audience:mesbak")],
            [_btn("🔙 برگشت", "admin:stats")],
        ]
    )


def backup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("💾 بکاپ جدید", "admin:backup_now")],
            [_btn("♻️ بازگردانی از بکاپ", "admin:backup_restore")],
            [_btn("🔙 برگشت", "admin:stats")],
        ]
    )


def backup_list_kb(names: list[str]) -> InlineKeyboardMarkup:
    # ایندکس به ترتیب list_backups (جدیدترین اول) اشاره می‌کند؛ هندلر همین فهرست را دوباره می‌سازد
    rows = [
        [_btn(f"♻️ {name}", f"admin:restore_ask:{i}")] for i, name in enumerate(names)
    ]
    rows.append([_btn("🔙 برگشت", "admin:backup")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def restore_warn_kb(index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("ادامه می‌دم", f"admin:restore_ready:{index}")],
            [_btn("🔙 انصراف", "admin:backup")],
        ]
    )


def restore_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("🔙 انصراف", "admin:backup")]])


def broadcast_confirm_kb(campaign_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("✅ تأیید و شروع", f"broadcast:start:{campaign_id}")],
            [_btn("لغو", f"broadcast:cancel:{campaign_id}")],
        ]
    )


def broadcast_cancel_kb(campaign_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("📊 وضعیت ارسال", f"broadcast:status:{campaign_id}")],
            [_btn("⏹ لغو ارسال", f"broadcast:cancel:{campaign_id}")],
        ]
    )


def mesbak_intro_kb() -> InlineKeyboardMarkup:
    rows = [
        [_btn(f"شروع با هدف {goal} نوبت در روز", f"mesbak:join:{goal}")]
        for goal in range(1, 6)
    ]
    rows.append([_btn("🏠 منوی اصلی", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mesbak_goal_kb() -> InlineKeyboardMarkup:
    rows = _chunk([_btn(str(goal), f"mesbak:goal:{goal}") for goal in range(1, 6)], 5)
    rows.append([_btn("🔙 برگشت", "mesbak:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mesbak_screen_kb(
    goal: int,
    reminders: list[tuple[int, str]],
    completed_slots: set[int],
    today: str,
    enabled: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    reminder_times = dict(reminders)
    for slot in range(1, goal + 1):
        if slot in completed_slots:
            rows.append([_btn(f"✅ نوبت {slot} ثبت شد", "mesbak:open")])
        else:
            rows.append(
                [_btn(f"ثبت نوبت {slot}", f"mesbak:done:{today}:{slot}")]
            )
        rows.append(
            [_btn(f"⏰ نوبت {slot}: {reminder_times.get(slot, 'تنظیم نشده')} · تغییر ساعت",
                  f"mesbak:time:{slot}")]
        )
    rows.append(
        [_btn("📊 گزارش ۷ روز", "mesbak:weekly"), _btn("📅 گزارش ۳۰ روز", "mesbak:monthly")]
    )
    rows.append(
        [_btn("🏁 چالش ۷ روز", "mesbak:challenge:start:7"),
         _btn("🏁 چالش ۳۰ روز", "mesbak:challenge:start:30")]
    )
    rows.append([_btn("🏆 لیگ مسباک", "mesbak:league"), _btn("🤝 رفیق مسباک", "mesbak:buddies")])
    rows.append([_btn("🎯 تغییر هدف روزانه", "mesbak:choose_goal")])
    if enabled:
        rows.append([_btn("خروج از بخش مسباک", "mesbak:exit")])
    rows.append([_btn("🏠 منوی اصلی", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mesbak_time_kb(slot: int, existing: set[str]) -> InlineKeyboardMarkup:
    presets = [
        _btn(value, f"mesbak:settime:{slot}:{value.replace(':', '')}")
        for value in MESBAK_PRESET_TIMES
        if value not in existing
    ]
    rows = _chunk(presets, 3)
    rows.append([_btn("✏️ ساعت دلخواه", f"mesbak:customtime:{slot}")])
    rows.append([_btn("🔙 برگشت", "mesbak:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mesbak_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("🔙 انصراف", "mesbak:open")]])


def mesbak_reminder_push_kb(day: str, slot: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("✅ ثبت این نوبت", f"mesbak:done:{day}:{slot}")]]
    )


def mesbak_challenge_kb(active: bool) -> InlineKeyboardMarkup:
    rows = []
    if active:
        rows.append([_btn("لغو چالش", "mesbak:challenge:cancel")])
    rows.append([_btn("🔙 برگشت", "mesbak:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mesbak_league_kb(opted_in: bool) -> InlineKeyboardMarkup:
    label = "➖ خروج از لیگ" if opted_in else "➕ عضویت در لیگ"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(label, "mesbak:league:toggle")],
            [_btn("🔙 برگشت", "mesbak:open")],
        ]
    )


def mesbak_buddy_invite_kb(share_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📨 فرستادن برای دوست", url=share_url)],
            [_btn("🔙 برگشت", "mesbak:buddies")],
        ]
    )


def mesbak_buddy_list_kb(
    rows: list[tuple[int, str]], queued: bool = False
) -> InlineKeyboardMarkup:
    buttons = [
        _btn(
            f"👤 {(name.replace(chr(10), ' ').replace(chr(13), ' ').strip() or 'کاربر')[:40]}",
            f"mesbak:buddy:open:{pair_id}",
        )
        for pair_id, name in rows
    ]
    keyboard = _chunk(buttons, 1)
    if buttons:
        keyboard.insert(0, [_btn("🔔 تلنگر به همهٔ مسباک‌نزده‌ها", "mesbak:buddy:nudge:all")])
    if queued:
        keyboard.append([_btn("لغو انتظار ناشناس", "mesbak:buddy:random:leave")])
    else:
        keyboard.append([_btn("🔍 پیدا کردن رفیق ناشناس", "mesbak:buddy:random:join")])
    keyboard.append([_btn("🔗 دعوت دوست با لینک", "mesbak:buddy:invite")])
    keyboard.append([_btn("🔙 برگشت", "mesbak:open")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def mesbak_buddy_pair_kb(pair_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("🔔 تلنگر بزن", f"mesbak:buddy:nudge:{pair_id}")],
            [_btn("👋 پایان رفاقت", f"mesbak:buddy:end:{pair_id}")],
            [_btn("🔙 فهرست رفیق‌ها", "mesbak:buddies")],
        ]
    )


def reminders_kb(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """items: لیست (id, "HH:MM")"""
    existing = {t for _, t in items}
    rows: list[list[InlineKeyboardButton]] = []
    if items:
        rows.extend(_chunk([_btn(f"🗑 {t}", f"rem_del:{rid}") for rid, t in items], 3))
    if len(items) < MAX_REMINDERS:
        presets = [
            _btn(f"➕ {t}", f"rem_add:{t.replace(':', '')}")
            for t in PRESET_TIMES
            if t not in existing
        ]
        rows.extend(_chunk(presets, 3))
        rows.append([_btn("✏️ ساعت دلخواه", "rem_custom")])
    rows.append([_btn("🔙 برگشت", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("🔙 انصراف", "rem")]])


def timezone_kb() -> InlineKeyboardMarkup:
    buttons = [_btn(label, f"tz_set:{i}") for i, (label, _) in enumerate(TIMEZONES)]
    rows = _chunk(buttons, 2)
    rows.append([_btn("🔙 برگشت", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_push_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("📖 امروز خوندم", "read"), _btn("🏠 منو", "home")]]
    )


def weekly_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("🔙 برگشت", "home")]])


def onboarding_time_kb() -> InlineKeyboardMarkup:
    presets = [_btn(f"⏰ {t}", f"onb:{t.replace(':', '')}") for t in PRESET_TIMES]
    rows = _chunk(presets, 2)
    rows.append([_btn("فعلاً نه", "onb:skip")])
    rows.append([_btn("🪥 فقط استفاده از مسباک", "mesbak:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def buddy_intro_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("🔗 دعوت دوست با لینک", "buddy:invite")],
            [_btn("🔍 پیدا کردن رفیق ناشناس", "buddy:join")],
            [_btn("🔙 برگشت", "home")],
        ]
    )


def buddy_invite_kb(deep_link: str) -> InlineKeyboardMarkup:
    share_url = "https://t.me/share/url?" + urlencode(
        {"url": deep_link, "text": "بیا رفیق مطالعه‌ام شو 🤝"}, quote_via=quote
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📨 فرستادن برای دوست", url=share_url)],
            [_btn("🔙 برگشت", "home")],
        ]
    )


def buddy_list_kb(buddies: list[tuple[int, str]], queued: bool) -> InlineKeyboardMarkup:
    rows = []
    if buddies:
        rows.append([_btn("🔔 تلنگر به همهٔ نخوانده‌ها", "buddy:nudge:all")])
    rows.extend([[_btn(f"👤 {name}", f"buddy:open:{pair_id}")] for pair_id, name in buddies])
    if queued:
        rows.append([_btn("لغو انتظار ناشناس", "buddy:leave")])
    else:
        rows.extend(
            [
                [_btn("🔗 دعوت دوست با لینک", "buddy:invite")],
                [_btn("🔍 پیدا کردن رفیق ناشناس", "buddy:join")],
            ]
        )
    rows.append([_btn("🔙 برگشت", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def buddy_nudge_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("🔔 تلنگر به همهٔ نخوانده‌ها", "buddy:nudge:all")],
            [_btn("فعلاً نه", "buddy:nudge:dismiss")],
        ]
    )


def buddy_pair_kb(pair_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("🔔 تلنگر بزن", f"buddy:nudge:{pair_id}")],
            [_btn("👋 پایان هم‌یاری", f"buddy:end:{pair_id}")],
            [_btn("🔙 فهرست رفیق‌ها", "buddy:list")],
        ]
    )


def buddy_waiting_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("لغو انتظار", "buddy:leave")], [_btn("🔙 برگشت", "home")]]
    )
