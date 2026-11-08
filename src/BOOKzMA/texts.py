from html import escape

from BOOKzMA.constants import (
    MAX_BOOK_NOTE_LENGTH,
    MAX_BOOK_PAGES,
    MAX_REMINDERS,
    MILESTONES,
    STREAK_LEADERBOARD_LIMIT,
)
from BOOKzMA.services.backup import BackupInfo
from BOOKzMA.services.badges import badge_label
from BOOKzMA.services.books import progress_percent
from BOOKzMA.services.catalog_text import strip_channel_handles
from BOOKzMA.utils import fa

MAX_STREAK_FREEZES = 3
MAX_MESBAK_FREEZES = 3
JOIN_GATE = "برای استفاده از ربات باید عضو کانال‌های زیر باشی. عضو که شدی دکمه «عضو شدم» رو بزن:"
JOIN_FIRST = "اول باید عضو کانال‌ها بشی 🙂"
NOT_JOINED = "هنوز عضو همه کانال‌ها نیستی 🙂"
JOINED = "عضویتت تایید شد ✅"

ADD_RESULT = {
    "ok": "یادآور اضافه شد ✅",
    "dup": "این ساعت رو قبلاً گذاشتی 🙂",
    "limit": "به سقف تعداد یادآورها رسیدی، اول یکی رو حذف کن.",
}
REMINDER_DELETED = "حذف شد 🗑"
BAD_TIME = "فرمت ساعت درست نیست 🤔 مثلاً <code>21:30</code> بفرست."
ALREADY_READ = "امروز رو قبلاً ثبت کردی ✅"
BOOK_ASK_TITLE = "📚 اسم کتاب رو بفرست."
BOOK_BAD_TITLE = "اسم کتاب معتبر نیست؛ یک نام کوتاه‌تر و غیرخالی بفرست."
BOOK_ASK_AUTHOR = "اسم نویسنده رو بفرست یا دکمهٔ «رد کردن» رو بزن."
BOOK_BAD_AUTHOR = "اسم نویسنده معتبر نیست؛ یک نام کوتاه‌تر بفرست یا از دکمهٔ رد کردن استفاده کن."
BOOK_ASK_TOTAL_PAGES = "کتاب در مجموع چند صفحه داره؟ فقط یک عدد مثبت بفرست."
BOOK_BAD_TOTAL_PAGES = f"تعداد کل صفحات باید عددی بین ۱ تا {fa(MAX_BOOK_PAGES)} باشه."
BOOK_BAD_PAGES = f"تعداد صفحات باید عددی بین ۱ تا {fa(MAX_BOOK_PAGES)} باشه."
BOOK_FLOW_LOST = "این مرحله با راه‌اندازی دوبارهٔ ربات بسته شده؛ از کتابخانه دوباره شروع کن."
BOOK_NOT_FOUND = "این کتاب پیدا نشد یا به کتابخانه تو تعلق نداره."
BOOK_NOT_READABLE = "برای این کتاب نمی‌شه مطالعهٔ جدید ثبت کرد."
BOOK_PAGE_COUNT_MISSING = "اول تعداد کل صفحه‌های این کتاب رو مشخص کن."
BOOK_PAGES_DUPLICATE = "این پیام قبلاً ثبت شده و دوباره شمرده نشد."
BOOK_STREAK_ALREADY_RECORDED = "مطالعهٔ امروزت قبلاً برای استریک ثبت شده بود."
BOOK_ARCHIVED = "کتاب آرشیو شد و سابقه‌اش محفوظ موند."
BOOK_RESTORED = "کتاب به کتابخانه برگشت."
BOOK_PRIVATE_ONLY = "برای حفظ حریم خصوصی، کتابخانه رو در گفت‌وگوی خصوصی با ربات باز کن."
CATALOG_ASK_QUERY = "اسم کتاب یا بخشی از توضیحش رو بفرست تا در کتاب‌های کانال بگردم."
CATALOG_BAD_QUERY = "عبارت جست‌وجو معتبر نیست؛ دست‌کم دو حرف بفرست."
CATALOG_NOT_CONFIGURED = "جست‌وجوی کتاب‌های کانال فعلاً در دسترس نیست."
CATALOG_NO_RESULTS = "کتابی با این عبارت پیدا نکردم."
CATALOG_SEARCH_FAILED = "الان جست‌وجو انجام نشد؛ کمی بعد دوباره امتحان کن."
CATALOG_BOOK_MISSING = "این فایل دیگه در فهرست کتاب‌ها نیست."
CATALOG_BOOK_ADDED = "کتاب به کتابخانه‌ات اضافه شد. هر وقت خواستی تعداد صفحه‌هاش رو تعیین کن."
CATALOG_BOOK_EXISTS = "این کتاب از قبل در کتابخانه‌ات هست."
CATALOG_BOOK_ADD_FAILED = "افزودن کتاب انجام نشد؛ دوباره امتحان کن."
CATALOG_FILE_FAILED = "فعلاً نتونستم فایل رو از کانال کپی کنم؛ پست کانال رو ببین."
BOOK_ASK_PAGE_COUNT_LATER = "هر وقت آماده‌ای، تعداد کل صفحه‌های کتاب رو بفرست."
BOOK_PAGE_COUNT_UNDER_PROGRESS = "تعداد کل صفحه‌ها نمی‌تونه از صفحه‌هایی که قبلاً خوندی کمتر باشه."
BOOK_PAGE_COUNT_ALREADY_SET = "تعداد صفحه‌های این کتاب قبلاً ثبت شده."
BOOK_ASK_NOTE = "یادداشت یا توضیحت رو در یک پیام بفرست؛ حداکثر ۳۵۰۰ نویسه."
BOOK_BAD_NOTE = f"یادداشت باید بین ۱ تا {fa(MAX_BOOK_NOTE_LENGTH)} نویسه باشه."
BOOK_NOTE_SAVED = "یادداشت کتاب ذخیره شد."
BOOK_NOTE_CLEARED = "یادداشت پاک شد؛ خود کتاب و سابقه‌اش دست‌نخورده موند."

ACCOUNT_DELETE_WARN = (
    "🗑 <b>حذف حساب</b>\n\n"
    "با حذف حساب، همه‌چیز برای همیشه پاک می‌شه:\n"
    "• استریک و رکوردت\n"
    "• فریزها و روزهای مطالعه\n"
    "• یادآورها و حضورت در لیدربورد\n"
    "• کتاب‌ها و سابقهٔ صفحات مطالعه‌شده\n\n"
    "این کار برگشت‌پذیر نیست. فقط این نکته رو بدون که اطلاعات ممکنه تا وقتی بکاپ‌های قدیمی "
    "پاک بشن، توی همون بکاپ‌ها بمونن.\n\n"
    "مطمئنی ادامه بدی؟"
)
ACCOUNT_DELETE_WHY = "قبل از حذف، بگو چرا می‌خوای بری؟ راستش برای بهتر شدن ربات بهش نیاز داریم 🌱"
ACCOUNT_DELETE_TYPE = (
    "قراره همه‌چیز پاک بشه. اگه هنوز مطمئنی، برای تأیید کلمهٔ <code>حذف</code> رو بنویس و بفرست."
)
ACCOUNT_DELETE_BAD_WORD = (
    "کلمهٔ تأیید درست نیست. فقط کافیه <code>حذف</code> رو بنویسی، یا با دکمهٔ پایین منصرف شو."
)
ACCOUNT_DELETE_FINAL = (
    "آخرین قدم! با زدن دکمهٔ زیر، حسابت و تمام داده‌هات بدون راه برگشت پاک می‌شه."
)
ACCOUNT_DELETED_DONE = (
    "حسابت همراه با همهٔ داده‌هاش پاک شد. 🌙\n"
    "امیدواریم دوباره ببینیمت؛ هر وقت خواستی برگرد."
)
ACCOUNT_DELETE_CANCELLED = "باشه، حذف لغو شد. خوشحالیم که هنوز اینجایی 🙂"
# پیام خنثی برای کاربر سنگ‌قبری؛ نباید به وجود حساب قبلی اشاره کند
ACCOUNT_DELETED_NOTICE = "برای شروع، دکمهٔ زیر رو بزن 👋"
ACCOUNT_RESTORED = "شروع شد! 📚"
INVALID_ACTION = "این دکمه دیگه معتبر نیست. دوباره امتحان کن 🙏"
RATE_LIMITED = "آروم‌تر 🙂 چند لحظه صبر کن و بعد دوباره امتحان کن."

BACKUP_NONE = "هنوز هیچ بکاپی ثبت نشده. با دکمهٔ «بکاپ جدید» یکی بگیر."
BACKUP_MENU_TITLE = "💾 <b>بکاپ دیتابیس</b>\n"
RESTORE_WORD = "بازیابی"


def _fa_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{fa(round(size_bytes / 1024 / 1024))} مگابایت"
    return f"{fa(max(1, round(size_bytes / 1024)))} کیلوبایت"


def backup_status(backups: list[BackupInfo]) -> str:
    if not backups:
        return BACKUP_MENU_TITLE + "\n" + BACKUP_NONE
    newest = backups[0]
    lines = [
        BACKUP_MENU_TITLE,
        f"آخرین بکاپ: <code>{newest.name}</code>",
        f"حجم: {_fa_size(newest.size_bytes)}",
        f"تعداد بکاپ‌های محلی: {fa(len(backups))}",
    ]
    return "\n".join(lines)


def backup_list(backups: list[BackupInfo]) -> str:
    lines = [BACKUP_MENU_TITLE, "بکاپ‌های موجود:", ""]
    for info in backups:
        lines.append(f"• <code>{info.name}</code> ({_fa_size(info.size_bytes)})")
    lines.append("")
    lines.append("برای بازگردانی، یکی رو انتخاب کن.")
    return "\n".join(lines)


def restore_warn(name: str) -> str:
    return (
        f"♻️ <b>بازگردانی از بکاپ</b>\n\n"
        f"فایل: <code>{name}</code>\n\n"
        "⚠️ با این کار <b>همهٔ داده‌های فعلی</b> (استریک‌ها، مطالعه‌ها، یادآورها و حساب‌های جدید) "
        "با محتوای همین بکاپ جایگزین می‌شن و برنمی‌گردن.\n\n"
        "اگه مطمئنی، اول با «بکاپ جدید» از وضعیت الان نسخه بگیر، بعد ادامه بده."
    )


RESTORE_CONFIRM = (
    "برای تأیید بازگردانی، کلمهٔ <code>بازیابی</code> رو بنویس و بفرست.\n"
    "با دکمهٔ پایین می‌تونی منصرف شی."
)
RESTORE_BAD_WORD = (
    "کلمهٔ تأیید درست نبود. فقط کافیه <code>بازیابی</code> رو بنویسی، یا منصرف شی."
)
RESTORE_RUNNING = "⏳ در حال بازگردانی… ممکنه چند ثانیه طول بکشه."
RESTORE_DONE = (
    "✅ بازگردانی انجام شد.\n\n"
    "برای اعمال کامل، روی سرور <code>docker compose restart bot</code> رو اجرا کن."
)
BACKUP_RUNNING = "⏳ در حال گرفتن بکاپ…"
BACKUP_FAILED = "❌ گرفتن بکاپ ناموفق بود. جزئیات در لاگ سرور."
RESTORE_FAILED = "❌ بازگردانی ناموفق بود. جزئیات در لاگ سرور."


def backup_done(name: str, size_bytes: int, path: str) -> str:
    return (
        f"✅ بکاپ گرفته شد: <code>{escape(name)}</code>\n"
        f"حجم: {_fa_size(size_bytes)}\n"
        f"مسیر برنامه: <code>{escape(path)}</code>"
    )


def admin_backup_hint() -> str:
    return "بکاپ روزانهٔ خودکار ساعت ۳:۳۰ با cron سرور انجام می‌شه؛ این بخش برای کار دستیه."


ONBOARDING_WELCOME = (
    "سلام! 👋 خوش اومدی\n\n"
    "اینجا جاییه که عادت کتاب‌خوندن رو باهم می‌سازیم: هر روز که بخونی ثبتش می‌کنیم، "
    "استریک‌ت بالا می‌ره و یادآور هم یادت نمی‌ذاره.\n\n"
    "برای شروع، اولین یادآور روزانه‌ات رو انتخاب کن؛ اگر هم فقط بخش مسباک رو می‌خوای، "
    "گزینهٔ پایین رو بزن:"
)
MAIN_MENU_HINT = "از منوی پایین بخش موردنظرت رو انتخاب کن."
MORE_MENU = "از اینجا به خلاصه، لیدربورد و راه‌های ارتباطی می‌رسی."
PROFILE_SETTINGS_MENU = "تنظیمات پروفایل و برنامهٔ روزانه‌ات رو از اینجا مدیریت کن."
ONBOARDING_DONE = "یادآورت فعاله ⏰ حالا هر روز سر وقت بهت یادآوری می‌کنم."
ONBOARDING_SKIPPED = "باشه! هر وقت خواستی از منوی «⏰ یادآورها» بذار 🙂"
WELCOME_BACK = (
    "چه خوب که برگشتی! 👋\n"
    "هر چقدر هم غیبت شد، مهم نیست؛ از همین امروز دوباره شروع کنیم."
)
COMEBACK_BROKEN = (
    "😌 استریک {days} روزه‌ات تموم شد؛ اتفاق می‌افده. ولی از دست نرفته:\n"
    "۳ روز پشت‌سرهم بخون تا نصفش پس بگیری 💪"
)
COMEBACK_PROGRESS = "🔁 روز {done} از ۳ برای پس‌گرفتن استریک. ادامه بده!"
COMEBACK_RESTORED = (
    "🎉 آفرین! {added} روز به استریکت برگشت؛ الان {total} روزه‌ای."
)
RISK_ALERT = (
    "⚠️ <b>استریکت در خطره!</b>\n"
    "امروز هنوز نخوندی. همین یه مطالعهٔ کوچیک هم روزت رو نجات می‌ده."
)
BUDDY_INTRO = (
    "🤝 <b>رفیق مطالعه</b>\n\n"
    "می‌تونی دوست خودت رو دعوت کنی یا برای پیدا کردن رفیق ناشناس وارد صف بشی.\n"
    "با هم به همدیگه تلنگر ملایم می‌زنید که امروز بخونید.\n\n"
    "• فقط نام نمایشی‌ات برای رفیقت دیده می‌شه\n"
    "• هر وقت بخوای می‌تونی هم‌یاری رو تمام کنی\n"
    "• تلنگر حداکثر روزی یک‌باره\n\n"
    "آماده‌ای؟"
)
BUDDY_INVITE_READY = (
    "لینک یک‌بارمصرفت آماده است؛ تا ۷ روز اعتبار دارد:\n<code>{link}</code>\n\n"
    "فقط کسی که این لینک را برایش می‌فرستی می‌تواند رفیقت شود."
)
BUDDY_INVITE_ACCEPTED = "🤝 دعوت {name} رو پذیرفتی؛ از «رفیق مطالعه» می‌تونی وضعیتش رو ببینی."
BUDDY_INVITE_PEER_ACCEPTED = "🤝 {name} دعوتت رو پذیرفت و رفیق مطالعه‌ات شد."
BUDDY_INVITE_ALREADY_FRIENDS = "شما از قبل رفیق مطالعهٔ هم هستین 🤝"
BUDDY_INVITE_BUSY = (
    "برای پذیرفتن دعوت، هیچ‌کدام نباید توی صف ناشناس باشین. "
    "لینک هنوز مصرف نشده و بعداً می‌تونی دوباره امتحان کنی."
)
BUDDY_INVITE_UNAVAILABLE = "این لینک معتبر نیست، منقضی شده یا قبلاً استفاده شده."
BUDDY_ALREADY_QUEUED = "اول از صف ناشناس خارج شو، بعد می‌تونی لینک دعوت بسازی."
BUDDY_WAITING = (
    "دنبال رفیق می‌گردیم... 🔍\n"
    "به‌محض پیدا شدن، خبرت می‌کنم. این صفحه رو می‌تونی هر وقت ببینی."
)
BUDDY_LEFT_QUEUE = "انتظار لغو شد."
BUDDY_MATCHED_SELF = "🤝 رفیقت پیدا شد: <b>{name}</b>! از «🤝 رفیق مطالعه» وضعیتش رو دنبال کن."
BUDDY_MATCHED_PEER = "🤝 رفیق جدید پیدا شد: <b>{name}</b>! از «🤝 رفیق مطالعه» شروع کن."
NUDGE_PUSH = "🔔 <b>{name}</b> بهت تلنگر زد: یه گوشه بشین و یه کم بخون!"
BUDDY_NUDGE_SENT = "تلنگر رفت 🔔"
BUDDY_NUDGE_LIMIT = "امروز یه تلنگر زدی؛ فردا دوباره 🙂"
BUDDY_ALREADY_READ = "رفیقت امروز مطالعه‌ش رو ثبت کرده؛ تلنگر براش نفرستادم ✅"
BUDDY_NUDGE_PROMPT = "امروز خوندی 👏 دوست داری به رفیق‌هایی که هنوز نخوندن تلنگر بزنی؟"
MESBAK_BUDDY_NUDGE_PROMPT = (
    "آفرین، سهمیهٔ امروز مسباکت کامل شد 👏 "
    "دوست داری به رفیق‌های مسباکت که هنوز کامل نکردن تلنگر بزنی؟"
)
MESBAK_BUDDY_NUDGE_DISMISSED = "باشه؛ هر وقت خواستی از فهرست رفیق‌های مسباک تلنگر بزن."
MESBAK_MENU_HINT = "بخش‌های اصلی مسباک از منوی پایین در دسترس‌اند."
MESBAK_SETTINGS_TITLE = (
    "⚙️ <b>تنظیمات مسباک</b>\n\n"
    "هدف و زمان‌های یادآوری را از دکمه‌های همین صفحه تغییر بده."
)
BUDDY_ENDED = (
    "هم‌یاری تمام شد. بدون دلخوری؛ هر وقت خواستی دوباره می‌تونی رفیق پیدا کنی 👋"
)


def buddy_screen(name: str, streak: int, read_today: bool) -> str:
    if read_today:
        status = "✅ امروزش رو ثبت کرده"
    else:
        status = "⏳ هنوز امروز نخونده"
    return (
        f"🤝 <b>رفیقت: {name}</b>\n\n"
        f"🔥 استریک: {fa(streak)} روز\n"
        f"{status}\n\n"
        "اگه دیر کرد، یه تلنگر دوستانه بزن."
    )


def buddy_overview(names: list[str], queued: bool) -> str:
    if names:
        friends = "\n".join(
            f"{fa(index)}. <b>{buddy_name(name)}</b>" for index, name in enumerate(names, 1)
        )
        text = f"🤝 <b>رفیق‌های مطالعه‌ات</b>\n\n{friends}"
    else:
        text = "🤝 هنوز رفیق مطالعه‌ای نداری."
    if queued:
        text += "\n\n🔍 توی صف پیدا کردن رفیق ناشناس هستی."
    return text


def buddy_name(display_name: str | None) -> str:
    from html import escape

    return escape((display_name or "کتاب‌خوان").replace("\n", " ").strip() or "کتاب‌خوان")


def buddy_button_name(display_name: str | None) -> str:
    name = (display_name or "کتاب‌خوان").replace("\n", " ").strip() or "کتاب‌خوان"
    return name[:40]


def buddy_nudge_summary(sent: int, already_read: int, already_nudged: int, failed: int) -> str:
    if not sent and not already_read and not already_nudged and not failed:
        return "امروز موردی برای تلنگر نبود."
    parts = []
    if sent:
        parts.append(f"به {fa(sent)} نفر تلنگر رفت")
    if already_read:
        parts.append(f"{fa(already_read)} نفر امروز خوانده بودند")
    if already_nudged:
        parts.append(f"به {fa(already_nudged)} نفر امروز قبلاً تلنگر زده بودی")
    if failed:
        parts.append(f"ارسال به {fa(failed)} نفر انجام نشد")
    return "؛ ".join(parts) + "."


def home(
    streak: int,
    best: int,
    strip: str,
    read_today: bool,
    freeze_balance: int,
    mesbak_streak: int | None = None,
    mesbak_freeze_balance: int = 0,
) -> str:
    if streak:
        streak_line = f"🔥 <b>{fa(streak)}</b> روز پشت‌سرهم"
    else:
        streak_line = "🔥 هنوز استریکی نداری"

    if read_today:
        status = "✅ مطالعه‌ی امروزت ثبت شده، آفرین!"
    elif streak:
        status = f"⏳ برای اینکه استریک {fa(streak)} روزه‌ات نسوزه، امروز هم بخون."
    else:
        status = "⏳ امروز هنوز نخوندی. همین الان یه استریک جدید شروع کن!"

    result = (
        "📚 <b>کتابخانه مرجع</b>\n\n"
        f"{streak_line}\n"
        f"🏆 رکورد: {fa(best)} روز\n\n"
        f"🛡️ فریز استریک: {fa(freeze_balance)} از {fa(MAX_STREAK_FREEZES)}\n\n"
        "۷ روز اخیر (آخری = امروز):\n"
        f"{strip}\n\n"
        f"{status}"
    )
    if mesbak_streak is not None:
        result += (
            f"\n\n🪥 استریک مسباک: {fa(mesbak_streak)} روز"
            f"\n🛡️ فریز مسباک: {fa(mesbak_freeze_balance)}/{fa(MAX_MESBAK_FREEZES)}"
        )
    return result


def bookshelf(
    active: int,
    visible: int,
    *,
    archived: bool = False,
    finished: int = 0,
    planned: int = 0,
    unstarted: int = 0,
    archived_count: int = 0,
    total_count: int | None = None,
    reading_titles: tuple[str, ...] = (),
    page: int = 1,
    page_count: int = 1,
) -> str:
    if visible == 0:
        body = "هنوز کتابی آرشیو نکردی." if archived else "هنوز کتابی به کتابخانه‌ات اضافه نکردی."
    else:
        body = "برای دیدن جزئیات یا ثبت مطالعه، یک کتاب رو انتخاب کن."
    title = "🗄 <b>آرشیو کتاب‌ها</b>" if archived else "📚 <b>کتابخانه من</b>"
    total_count = visible + archived_count if total_count is None else total_count
    lines = [title, ""]
    if archived:
        lines.extend(
            [f"کتاب‌های آرشیوشده: {fa(visible)}", f"کل کتاب‌ها: {fa(total_count)}"]
        )
    else:
        lines.extend(
            [
                f"در حال مطالعه (حداقل ۱ صفحه): {fa(active)}",
                f"تمام‌شده: {fa(finished)}",
                f"برنامه‌ریزی‌شده: {fa(planned)}",
                f"شروع‌نشده: {fa(unstarted)}",
                f"آرشیوشده: {fa(archived_count)}",
                f"کل کتاب‌ها: {fa(total_count)}",
            ]
        )
        if reading_titles:
            lines.extend(["", "📖 کتاب‌های شروع‌شده:"])
            lines.extend(f"• {escape(name[:48])}" for name in reading_titles)
            remaining = active - len(reading_titles)
            if remaining > 0:
                lines.append(f"و {fa(remaining)} کتاب دیگر")
    if page_count > 1:
        lines.extend(["", f"صفحه {fa(page)} از {fa(page_count)}"])
    lines.extend(["", body])
    return "\n".join(lines)


def catalog_results(query: str, first: int, last: int) -> str:
    return (
        f"🔎 نتایج جست‌وجو برای <b>{escape(query)}</b>\n"
        f"نتیجه‌های {fa(first)} تا {fa(last)}"
    )


def book_added(title: str, total_pages: int) -> str:
    return (
        "کتاب اضافه شد ✅\n\n"
        f"📖 <b>{escape(title)}</b>\n"
        f"تعداد صفحات: {fa(total_pages)}"
    )


def _format_file_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return ""
    if size_bytes >= 1024 * 1024:
        size_mb = size_bytes / (1024 * 1024)
        readable_size = f"{size_mb:.1f}".rstrip("0").rstrip(".")
        return f"حجم: {fa(readable_size)} مگابایت"
    return f"حجم: {fa(max(1, round(size_bytes / 1024)))} کیلوبایت"


def _format_mime_label(mime_type: str | None) -> str:
    if not mime_type:
        return ""
    normalized = mime_type.strip().lower()
    if "/" in normalized:
        _, ext = normalized.split("/", 1)
    else:
        ext = normalized
    label = ext.strip() or "file"
    return f"فرمت: {escape(label)}"


def catalog_result(
    file_name: str,
    caption_preview: str | None,
    file_size: int | None,
    mime_type: str | None,
) -> str:
    details: list[str] = []
    mime_label = _format_mime_label(mime_type)
    if mime_label:
        details.append(mime_label)
    size_label = _format_file_size(file_size)
    if size_label:
        details.append(size_label)
    detail_line = f"\n{' · '.join(details)}" if details else ""
    clean_name = strip_channel_handles(file_name or "فایل بدون نام")
    clean_caption = strip_channel_handles(caption_preview)
    caption_line = f"\n\n{escape(clean_caption)}" if clean_caption else ""
    return (
        f"📚 <b>{escape(clean_name or 'فایل بدون نام')}</b>"
        f"{detail_line}{caption_line}"
    )


def book_detail(
    title: str,
    author: str | None,
    pages_read: int,
    total_pages: int | None,
    status: str,
) -> str:
    title = strip_channel_handles(title)
    author_line = f"✍️ {escape(author)}\n" if author else ""
    status_label = {
        "planned": "می‌خواهم بخوانم",
        "reading": "در حال مطالعه",
        "finished": "تمام‌شده",
        "archived": "آرشیوشده",
    }.get(status, "در حال مطالعه")
    if total_pages is None:
        return (
            f"📖 <b>{escape(title)}</b>\n"
            f"{author_line}"
            f"وضعیت: {status_label}\n\n"
            "تعداد صفحه‌ها هنوز ثبت نشده. برای شروع مطالعه، تعداد کل صفحه‌ها را تعیین کن."
        )
    remaining = max(0, total_pages - pages_read)
    return (
        f"📖 <b>{escape(title)}</b>\n"
        f"{author_line}"
        f"وضعیت: {status_label}\n\n"
        f"پیشرفت: {fa(pages_read)} از {fa(total_pages)} صفحه "
        f"({fa(progress_percent(pages_read, total_pages))}٪)\n"
        f"باقی‌مانده: {fa(remaining)} صفحه"
    )


def book_note(title: str, note: str | None) -> str:
    clean_title = strip_channel_handles(title)
    content = f"\n\n{escape(note)}" if note else "\n\nهنوز یادداشتی برای این کتاب ننوشتی."
    return f"📝 <b>یادداشت {escape(clean_title)}</b>{content}"


def book_ask_pages(title: str, remaining: int) -> str:
    title = strip_channel_handles(title)
    return (
        f"امروز چند صفحه از <b>{escape(title)}</b> خوندی؟\n"
        f"صفحات باقی‌مانده: {fa(remaining)}"
    )


def book_pages_over(remaining: int) -> str:
    return f"این تعداد از صفحات باقی‌مانده بیشتره؛ حداکثر {fa(remaining)} صفحه وارد کن."


def pages_logged(
    title: str,
    added: int,
    pages_read: int,
    total_pages: int,
    finished: bool,
    reading_message: str,
) -> str:
    title = strip_channel_handles(title)
    finish_line = "\n🎉 کتاب رو تموم کردی!" if finished else ""
    return (
        f"برای <b>{escape(title)}</b>، {fa(added)} صفحه ثبت شد ✅\n"
        f"پیشرفت: {fa(pages_read)} از {fa(total_pages)} صفحه "
        f"({fa(progress_percent(pages_read, total_pages))}٪)"
        f"{finish_line}\n\n{reading_message}"
    )


def book_archive_confirm(title: str) -> str:
    title = strip_channel_handles(title)
    return (
        f"کتاب <b>{escape(title)}</b> آرشیو بشه؟\n\n"
    )


def comeback_line(change, total_streak: int) -> str | None:
    if change is None:
        return None
    if change.bonus_added:
        return COMEBACK_RESTORED.format(added=fa(change.bonus_added), total=fa(total_streak))
    if change.broken_days:
        return COMEBACK_BROKEN.format(days=fa(change.broken_days))
    if change.progress_done:
        return COMEBACK_PROGRESS.format(done=fa(change.progress_done))
    return None


def badge_toast(codes: list[str]) -> str | None:
    if not codes:
        return None
    labels = " · ".join(badge_label(code) for code in codes)
    return f"🏅 نشان جدید گرفتی: {labels}"


def read_toast(
    streak: int,
    created: bool,
    freeze_used: bool = False,
    freeze_earned: bool = False,
    freeze_balance: int = 0,
    comeback: str | None = None,
    badges: list[str] | None = None,
) -> str:
    if not created:
        return ALREADY_READ
    if streak in MILESTONES:
        message = f"🎉 {fa(streak)} روز پشت‌سرهم! عالیه 🔥"
    elif streak == 1:
        message = "شروع خوبیه! استریک ۱ روزه 🔥"
    else:
        message = f"🔥 {fa(streak)} روز پشت‌سرهم، ادامه بده"
    if freeze_used:
        message += "\n🛡️ فریزت دیروز رو پوشش داد و استریکت حفظ شد."
    if freeze_earned:
        message += (
            f"\n🎁 یک فریز جایزه گرفتی؛ موجودی: "
            f"{fa(freeze_balance)}/{fa(MAX_STREAK_FREEZES)}"
        )
    if comeback:
        message += f"\n{comeback}"
    badge_line = badge_toast(badges or [])
    if badge_line:
        message += f"\n{badge_line}"
    return message


def reminders(times: list[str], tz_label: str) -> str:
    listing = "\n".join(f"• {t}" for t in times) if times else "هنوز یادآوری نداری."
    return (
        "⏰ <b>یادآورها</b>\n\n"
        f"هر روز سر این ساعت‌ها بهت پیام می‌دم (به وقت {tz_label}):\n\n"
        f"{listing}\n\n"
        f"حداکثر {fa(MAX_REMINDERS)} تا یادآور می‌تونی داشته باشی."
    )


def custom_time() -> str:
    return (
        "ساعت دلخواهت رو بفرست، مثلاً <code>21:30</code> یا <code>۷:۴۵</code>.\n"
        "(ساعت ۲۴ ساعته و به وقت منطقه زمانی خودت)"
    )


def timezone(tz_label: str) -> str:
    return (
        "🌍 <b>منطقه زمانی</b>\n\n"
        f"الان: {tz_label}\n"
        "یادآورها و «امروز» بر اساس همین حساب می‌شن."
    )


def weekly_summary(days_read: int, streak: int, best: int, freeze_balance: int) -> str:
    return (
        "📊 <b>خلاصهٔ ۷ روز اخیر</b>\n\n"
        f"📚 روزهای مطالعه: {fa(days_read)} از ۷\n"
        f"🔥 استریک فعلی: {fa(streak)} روز\n"
        f"🏆 بهترین استریک: {fa(best)} روز\n"
        f"🛡️ فریزهای موجود: {fa(freeze_balance)}/{fa(MAX_STREAK_FREEZES)}"
    )


def profile(
    streak: int,
    best: int,
    freeze_balance: int,
    opted_out: bool,
    badges: list[str],
    mesbak_streak: int | None = None,
    mesbak_freeze_balance: int = 0,
) -> str:
    participation = "خاموش" if opted_out else "روشن"
    if badges:
        badges_line = " · ".join(badge_label(code) for code in badges)
    else:
        badges_line = "هنوز نشانی نداری؛ اولین مطالعه اولین نشانته ⭐"
    result = (
        "👤 <b>پروفایل من</b>\n\n"
        f"🔥 استریک فعلی: {fa(streak)} روز\n"
        f"🏆 بهترین استریک: {fa(best)} روز\n"
        f"🛡️ فریزهای موجود: {fa(freeze_balance)}/{fa(MAX_STREAK_FREEZES)}\n"
        f"🏅 حضور در لیدربورد: {participation}\n\n"
        f"🎖 نشان‌ها: {badges_line}"
    )
    if mesbak_streak is not None:
        result += (
            f"\n🪥 استریک مسباک: {fa(mesbak_streak)} روز"
            f"\n🛡️ فریز مسباک: {fa(mesbak_freeze_balance)}/{fa(MAX_MESBAK_FREEZES)}"
        )
    return result


def streak_leaderboard(scores: list[tuple[int, str]]) -> str:
    if not scores:
        return "🏅 <b>لیدربورد استریک</b>\n\nهنوز استریکی برای نمایش نیست."
    lines = ["🏅 <b>لیدربورد استریک</b>"]
    for rank, (streak, display_name) in enumerate(scores[:STREAK_LEADERBOARD_LIMIT], 1):
        lines.append(f"{fa(rank)}. {escape(display_name)} · {fa(streak)} روز")
    return "\n".join(lines)


def support() -> str:
    return (
        "💬 <b>پشتیبانی و ارتباط</b>\n\n"
        "برای گزارش مشکل، پیشنهاد یا انتقاد، پیام پشتیبانی بفرست. "
    )


SUPPORT_ASK_MESSAGE = "پیام یا فایل موردنظرت رو بفرست؛ به مدیران پشتیبانی می‌رسه."
SUPPORT_ASK_REPLY = "پاسخت رو بفرست؛ متن، عکس یا فایل هم می‌تونی ارسال کنی."
SUPPORT_RECEIVED = "پیامت به پشتیبانی رسید؛ اگر لازم باشه همین‌جا جواب می‌دیم."
SUPPORT_NOT_CONFIGURED = "پشتیبانی هنوز راه‌اندازی نشده؛ لطفاً کمی بعد دوباره تلاش کن."
SUPPORT_DELIVERY_FAILED = "ارسال پیام انجام نشد؛ کمی بعد دوباره امتحان کن."
SUPPORT_REPLY_SENT = "پاسخ برای کاربر فرستاده شد."
SUPPORT_REPLY_FAILED = "ارسال پاسخ به کاربر انجام نشد."
SUPPORT_REPLY_UNAUTHORIZED = "این دکمه فقط برای مدیران پشتیبانیه."
SUPPORT_TICKET_MISSING = "این تیکت پیدا نشد یا بسته شده."
SUPPORT_USER_BLOCKED = "امکان ارسال پیام به پشتیبانی برای حسابت غیرفعال شده."
SUPPORT_BLOCKED = "کاربر از پشتیبانی مسدود شد."
SUPPORT_UNBLOCKED = "مسدودی کاربر برداشته شد."
SUPPORT_ADMIN_TICKET = (
    "✉️ تیکت #{ticket_id} از <b>{name}</b>\n"
    "شناسه کاربر: <code>{user_id}</code>"
)

FREEZE_GIFT_SELECT = "فریز موردنظر برای هدیه را انتخاب کن:"
FREEZE_GIFT_ASK_AMOUNT = "تعداد فریز موردنظر برای هر کاربر را بفرست؛ عددی بین ۱ تا ۱۰۰۰."
FREEZE_GIFT_BAD_AMOUNT = "یک عدد صحیح بین ۱ تا ۱۰۰۰ بفرست."
FREEZE_GIFT_CANCELLED = "عملیات هدیه لغو شد؛ هیچ فریزی تغییر نکرد."


def freeze_gift_preview(
    habit: str,
    amount: int,
    recipients: int,
    units: int,
    capped: int,
    skipped: int = 0,
    *,
    changed: bool = False,
) -> str:
    habit_label = "مطالعه" if habit == "reading" else "مسباک"
    audience = "کاربران ثبت‌شده" if habit == "reading" else "اعضای فعال مسباک"
    prefix = "پیش‌نمایش تغییر کرد؛ دوباره بررسی کن.\n\n" if changed else ""
    return (
        f"{prefix}🎁 <b>هدیهٔ فریز {habit_label}</b>\n\n"
        f"گیرندگان: {fa(recipients)} · {audience}\n"
        f"درخواست برای هر نفر: {fa(amount)}\n"
        f"اعتبار واقعی با سقف {fa(3)}: {fa(units)} فریز\n"
        f"بدون اعتبار به‌علت سقف: {fa(capped)} نفر\n\n"
        f"خارج‌شده از مخاطب بعد از پیش‌نمایش: {fa(skipped)} نفر\n\n"
        "اعلان برای کاربران ارسال نمی‌شود. تأیید می‌کنی؟"
    )


def freeze_gift_result(
    habit: str, recipients: int, units: int, capped: int, skipped: int = 0
) -> str:
    habit_label = "مطالعه" if habit == "reading" else "مسباک"
    return (
        f"✅ هدیهٔ فریز {habit_label} انجام شد.\n"
        f"اعتبار ثبت‌شده: {fa(units)} برای {fa(recipients)} نفر\n"
        f"در سقف بودند: {fa(capped)} نفر · از مخاطب خارج: {fa(skipped)} نفر"
    )


def admin_dashboard(stats: dict[str, int], series: list[tuple[object, int]]) -> str:
    maximum = max((count for _, count in series), default=0)
    chart = []
    for day, count in series:
        width = round(count / maximum * 10) if maximum else 0
        chart.append(f"{day:%m/%d} {'█' * width or '·'} {fa(count)}")
    return (
        "📊 <b>گزارش بات (UTC)</b>\n\n"
        f"👤 کاربران ثبت‌شده: {fa(stats['users'])}\n"
        f"🚀 شروع‌کننده‌ها: {fa(stats['starters'])}\n"
        f"🎓 آنبردینگ کامل‌شده: {fa(stats['onboarded'])}\n"
        f"🆕 شروع در ۷/۳۰ روز: {fa(stats['starts_7d'])} / {fa(stats['starts_30d'])}\n"
        f"🟢 فعال روزانه/هفتگی/ماهانه: "
        f"{fa(stats['dau'])} / {fa(stats['wau'])} / {fa(stats['mau'])}\n"
        f"⚪ شروع‌کنندهٔ غیرفعال در ۳۰ روز: {fa(stats['inactive_30d'])}\n"
        f"📚 مطالعه‌کننده در ۷/۳۰ روز: "
        f"{fa(stats['readers_7d'])} / {fa(stats['readers_30d'])}\n"
        f"📖 روزهای ثبت مطالعه در ۷/۳۰ روز: "
        f"{fa(stats['reading_days_7d'])} / {fa(stats['reading_days_30d'])}\n"
        f"📚 کتاب‌های فعال/تمام‌شده: {fa(stats['active_books'])} / "
        f"{fa(stats['finished_books'])}\n"
        f"🗄 کتاب‌های آرشیوشده: {fa(stats['archived_books'])} · "
        f"افزوده/آرشیو/بازگردانی در ۷ روز: {fa(stats['books_added_7d'])} / "
        f"{fa(stats['books_archived_7d'])} / {fa(stats['books_restored_7d'])}\n"
        f"📄 نشست/صفحهٔ مطالعه در ۷ روز: {fa(stats['page_sessions_7d'])} / "
        f"{fa(stats['pages_7d'])}\n"
        f"📑 تنظیم تعداد صفحات در ۷ روز: {fa(stats['page_counts_set_7d'])}\n"
        f"💬 پشتیبانی · تیکت باز/جدید: {fa(stats['support_tickets_open'])} / "
        f"{fa(stats['support_tickets_7d'])} · پیام/پاسخ ۷روزه: "
        f"{fa(stats['support_messages_7d'])} / {fa(stats['support_replies_7d'])} · "
        f"مسدود: {fa(stats['support_blocked_users'])}\n"
        f"🔁 بازگشت D1/D7/D30: {fa(stats['retention_d1'])}% / "
        f"{fa(stats['retention_d7'])}% / {fa(stats['retention_d30'])}%\n"
        f"🔥 دارای استریک: {fa(stats['users_with_streak'])} · "
        f"بیشترین جاری/رکورد: {fa(stats['max_current_streak'])} / "
        f"{fa(stats['max_record_streak'])} روز\n"
        f"⏰ یادآورها: {fa(stats['reminders'])}\n"
        f"🪥 مسباک · عضو فعال: {fa(stats['mesbak_members'])} · فعال ۷/۳۰ روز: "
        f"{fa(stats['mesbak_active_7d'])}/{fa(stats['mesbak_active_30d'])} · "
        f"تکمیل هدف ۷روزه: {fa(stats['mesbak_completed_days_7d'])} روز، "
        f"{fa(stats['mesbak_completion_rate_7d'])}% از روزهای دارای ثبت\n"
        f"🤝 رفیق مسباک · جفت فعال: {fa(stats['mesbak_buddy_pairs'])} "
        f"(ناشناس: {fa(stats['mesbak_random_pairs'])}) · "
        f"منتظر در صف: {fa(stats['mesbak_random_waiting'])}\n"
        f"🛡️ فریز مصرف‌شده · مطالعه/مسباک: {fa(stats['freezes_used'])} / "
        f"{fa(stats['mesbak_freezes_used'])}\n"
        f"⚠️ هشدار «استریک در خطر» در ۷ روز: {fa(stats['streak_alerts_7d'])}\n"
        f"🔁 کاربران با پاداش comeback: {fa(stats['comeback_users'])}\n"
        f"🎖 نشان‌ها: {fa(stats['badges_total'])} اهدا به {fa(stats['badge_holders'])} نفر\n"
        f"🤝 جفت‌های رفیق مطالعه: {fa(stats['buddy_pairs_active'])} فعال · "
        f"{fa(stats['buddy_pairs_total'])} کل\n"
        f"🗑 حساب حذف‌شده: {fa(stats['accounts_deleted'])} · ۷ روز اخیر: "
        f"{fa(stats['deletions_7d'])}\n\n"
        "<b>فعالیت ۷ روز اخیر</b>\n" + "\n".join(chart)
    )


def reminder_push(streak: int) -> str:
    if streak:
        return (
            "⏰ <b>وقت مطالعه‌ست!</b>\n"
            f"🔥 استریک {fa(streak)} روزه‌ات منتظرته، امروز هم ادامه بده."
        )
    return "⏰ <b>وقت مطالعه‌ست!</b>\nامروز یه استریک جدید شروع کن 🔥"


mesbak_INTRO = (
    "🪥 <b>بخش مسباک</b>\n\n"
    "هدفت رو از ۱ تا ۵ نوبت در روز انتخاب کن؛ برای هر نوبت یک یادآور داری و فقط با کامل‌کردن "
    "هدفت استریک می‌گیری.\n\n"
    "با عضویت در این بخش، آموزش‌های ادمین هم برایت ارسال می‌شود. برای توقف یادآورها و آموزش‌ها "
    "هر وقت خواستی از بخش خارج شو.\n\n"
    "این بخش کاملاً جدا از استریک مطالعه است."
)
mesbak_BAD_TIME = "ساعت درست نیست؛ مثلاً <code>06:30</code> یا <code>۷:۴۵</code> بفرست."
mesbak_JOINED = "بخش مسباک برایت فعال شد ✅"
mesbak_EXITED = "از بخش مسباک خارج شدی؛ یادآورها و آموزش‌های بعدی متوقف شدند. سابقه‌ات محفوظ است."
mesbak_DUPLICATE = "این نوبت امروز قبلاً ثبت شده ✅"
mesbak_INACTIVE = "برای ثبت نوبت، اول به بخش مسباک بپیوند."
mesbak_STALE_ACTION = "این دکمه برای روز دیگری است؛ صفحه را دوباره باز کن."
mesbak_REMINDER = "⏰ وقت نوبت {slot} مسباکه؛ بعد از انجام، اینجا ثبتش کن."


def mesbak_screen(
    goal: int,
    completed: int,
    streak: int,
    best: int,
    times: list[str],
    pending_goal: int | None,
    pending_date: str | None,
    badges: list[str] | None = None,
    freeze_balance: int = 0,
) -> str:
    lines = [
        "🪥 <b>استریک مسباک</b>",
        "",
        f"امروز: {fa(completed)} از {fa(goal)} نوبت",
        f"🔥 استریک فعلی: {fa(streak)} روز",
        f"🏆 بهترین رکورد: {fa(best)} روز",
        f"🛡️ فریز موجود: {fa(freeze_balance)}/{fa(MAX_MESBAK_FREEZES)}",
        "",
        "⏰ ساعت‌های یادآوری:",
    ]
    lines.extend(f"نوبت {fa(index)} · {value}" for index, value in enumerate(times, 1))
    if pending_goal is not None and pending_date is not None:
        lines.extend(
            ["", f"هدف {fa(pending_goal)} نوبتی از {pending_date} اعمال می‌شود."]
        )
    if completed >= goal:
        lines.extend(["", "🎉 سهمیهٔ امروزت کامل شد!"])
    badge_labels = {"streak_7": "۷ روز", "streak_30": "۳۰ روز", "streak_100": "۱۰۰ روز"}
    earned = [badge_labels[code] for code in badges or [] if code in badge_labels]
    lines.extend(["", "🏅 دستاوردها: " + (" · ".join(earned) if earned else "هنوز نشانی نداری")])
    return "\n".join(lines)


def mesbak_recorded(
    completed: int,
    goal: int,
    streak: int,
    new_badges: list[str] | None = None,
    *,
    freeze_used: bool = False,
    freeze_earned: bool = False,
    freeze_balance: int = 0,
) -> str:
    if completed >= goal:
        message = f"🎉 هدف امروز کامل شد؛ استریک مسباکت {fa(streak)} روزه شد!"
    else:
        message = f"این نوبت ثبت شد ✅ · {fa(completed)} از {fa(goal)}"
    badge_labels = {"streak_7": "هفت روز", "streak_30": "سی روز", "streak_100": "صد روز"}
    if new_badges:
        message += "\n🏅 نشان جدید: " + "، ".join(badge_labels[code] for code in new_badges)
    if freeze_used:
        message += "\n🛡️ یک فریز مسباک برای روز ازدست‌رفته مصرف شد."
    if freeze_earned:
        message += "\n🎁 یک فریز مسباک گرفتی!"
    message += f"\n🛡️ فریز مسباک: {fa(freeze_balance)}/{fa(MAX_MESBAK_FREEZES)}"
    return message


def mesbak_reminder(slot: int) -> str:
    return mesbak_REMINDER.format(slot=fa(slot))


def mesbak_weekly(
    completed_days: int,
    streak: int,
    best: int,
    days: list[str],
    freeze_balance: int = 0,
) -> str:
    return (
        "📊 <b>گزارش مسباک · ۷ روز اخیر</b>\n\n"
        f"روزهای کامل: {fa(completed_days)} از ۷\n"
        f"درصد تکمیل: {fa(round(completed_days * 100 / 7))}%\n"
        f"استریک فعلی: {fa(streak)} روز\n"
        f"بهترین رکورد: {fa(best)} روز\n\n"
        f"فریز موجود: {fa(freeze_balance)}/{fa(MAX_MESBAK_FREEZES)}\n\n"
        + "\n".join(days)
    )


def mesbak_monthly(
    completed_days: int, streak: int, best: int, freeze_balance: int = 0
) -> str:
    return (
        "📅 <b>گزارش مسباک · ۳۰ روز اخیر</b>\n\n"
        f"روزهای کامل: {fa(completed_days)} از ۳۰\n"
        f"درصد تکمیل: {fa(round(completed_days * 100 / 30))}%\n"
        f"استریک فعلی: {fa(streak)} روز\n"
        f"بهترین رکورد: {fa(best)} روز\n"
        f"فریز موجود: {fa(freeze_balance)}/{fa(MAX_MESBAK_FREEZES)}"
    )


def mesbak_challenge(duration: int, progress: int, ends_on: str) -> str:
    from datetime import date

    from BOOKzMA.utils import fa

    if progress >= duration:
        status = "🎉 چالش رو کامل کردی!"
    else:
        status = f"روزهای کامل و پشت‌سرهم: {fa(progress)} از {fa(duration)}"
    return (
        f"🏁 <b>چالش {fa(duration)} روزهٔ مسباک</b>\n\n"
        f"{status}\n"
        f"پایان: {date.fromisoformat(ends_on).strftime('%Y/%m/%d')}"
    )


def mesbak_league(rows: list[tuple[int, str, int]], opted_in: bool) -> str:
    from html import escape

    if not rows:
        return "🏆 <b>لیگ مسباک</b>\n\nهنوز کسی در لیگ نیست؛ اولین نفر تو باش!"
    lines = ["🏆 <b>لیگ هفتگی مسباک</b>"]
    for rank, (_user_id, name, completed) in enumerate(
        rows[:STREAK_LEADERBOARD_LIMIT], 1
    ):
        safe_name = escape(name.replace("\n", " ")[:48])
        lines.append(f"{fa(rank)}. {safe_name} · {fa(completed)} روز کامل")
    if not opted_in:
        lines.append("\nبرای نمایش نام و رتبه‌ات، عضویت در لیگ رو فعال کن.")
    return "\n".join(lines)


def mesbak_buddies(rows: list[tuple[int, str]], queued: bool = False) -> str:
    if not rows and queued:
        return (
            "🤝 <b>رفیق‌های مسباک</b>\n\n"
            "در صف پیدا کردن رفیق ناشناس هستی؛ به‌محض match شدن خبرت می‌کنیم."
        )
    if not rows:
        return (
            "🤝 <b>رفیق‌های مسباک</b>\n\n"
            "هنوز رفیقی نداری؛ دوستت رو دعوت کن یا رفیق ناشناس پیدا کن."
        )
    friends = "\n".join(
        f"{fa(index)}. <b>{mesbak_buddy_name(name)}</b>"
        for index, (_pid, name) in enumerate(rows, 1)
    )
    waiting = "\n\n🔍 در صف پیدا کردن رفیق ناشناس هم هستی." if queued else ""
    return f"🤝 <b>رفیق‌های مسباک</b>\n\n{friends}{waiting}\n\nبرای دیدن هر رفیق، روی اسمش بزن."


MESBAK_RANDOM_WAITING = "🔍 در صف پیدا کردن رفیق ناشناس قرار گرفتی؛ به‌محض match شدن خبرت می‌کنیم."
MESBAK_RANDOM_MATCHED_SELF = (
    "🤝 رفیقت پیدا شد: <b>{name}</b>! از «🤝 رفیق‌های مسباک» وضعیتش رو دنبال کن."
)
MESBAK_RANDOM_MATCHED_PEER = (
    "🤝 رفیق جدید مسباک پیدا شد: <b>{name}</b>! از «🤝 رفیق‌های مسباک» شروع کن."
)
MESBAK_RANDOM_QUEUE_BUSY = "اول از صف پیدا کردن رفیق ناشناس خارج شو، بعد لینک دعوت بساز."
MESBAK_RANDOM_LEFT_QUEUE = "از صف پیدا کردن رفیق ناشناس خارج شدی."
MESBAK_RANDOM_INACTIVE = "برای پیدا کردن رفیق، اول باید عضو فعال مسباک باشی."
MESBAK_BUDDY_ENDED = "رفاقت مسباک تمام شد. بدون دلخوری؛ هر وقت خواستی دوباره رفیق پیدا کن 👋"


def mesbak_buddy_nudge_summary(
    sent: int, already_done: int, already_nudged: int, failed: int
) -> str:
    if not sent and not already_done and not already_nudged and not failed:
        return "امروز موردی برای تلنگر نبود."
    parts = []
    if sent:
        parts.append(f"به {fa(sent)} نفر تلنگر رفت")
    if already_done:
        parts.append(f"{fa(already_done)} نفر امروز مسباکشون رو کامل کرده بودند")
    if already_nudged:
        parts.append(f"به {fa(already_nudged)} نفر امروز قبلاً تلنگر زده بودی")
    if failed:
        parts.append(f"ارسال به {fa(failed)} نفر انجام نشد")
    return "؛ ".join(parts) + "."


def mesbak_buddy_name(display_name: str | None) -> str:
    from html import escape

    return escape((display_name or "کاربر").replace("\n", " ").strip() or "کاربر")


def mesbak_buddy_screen(name: str, completed_days: int, done_today: bool) -> str:
    if done_today:
        status = "✅ امروز مسباکش رو کامل کرده"
    else:
        status = "⏳ امروز هنوز کامل نکرده"
    return (
        f"🤝 <b>رفیقت: {name}</b>\n\n"
        f"🔥 روزهای کامل: {fa(completed_days)}\n"
        f"{status}\n\n"
        "اگه دیر کرد، یه تلنگر دوستانه بزن."
    )


def mesbak_buddy_invite_ready(link: str) -> str:
    return f"لینک دعوت یک‌بارمصرفت تا ۷ روز معتبره:\n<code>{link}</code>"


def mesbak_buddy_nudge(name: str) -> str:
    from html import escape

    return f"🔔 <b>{escape(name)}</b> برات یک تلنگر مسباک فرستاد."


mesbak_BUDDY_ACCEPTED = "رفاقت مسباک برقرار شد 🤝"
mesbak_BUDDY_ALREADY = "شما از قبل رفیق مسباک هم هستین."
mesbak_BUDDY_INACTIVE = "برای پذیرش دعوت، هر دو نفر باید عضو فعال بخش مسباک باشید."
mesbak_BUDDY_UNAVAILABLE = "این دعوت معتبر نیست، منقضی شده یا قبلاً استفاده شده."
mesbak_BUDDY_SELF = "نمی‌تونی دعوت خودت رو بپذیری."
