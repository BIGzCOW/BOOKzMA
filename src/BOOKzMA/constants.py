import os
from dotenv import load_dotenv

load_dotenv()
REQUIRED_CHANNELS = tuple(
    ch.strip() for ch in os.getenv("REQUIRED_CHANNELS", "").split(",") if ch.strip()
)

DEFAULT_TIMEZONE = "Asia/Tehran"

MAX_REMINDERS = 5
PRESET_TIMES = ("08:00", "13:00", "18:00", "21:00", "23:00")
MISWAK_PRESET_TIMES = ("06:30", "13:00", "16:00", "19:00", "22:00")
MILESTONES = {3, 7, 14, 30, 50, 100, 200, 365}

TIMEZONES = [
    ("🇮🇷 تهران", "Asia/Tehran"),
    ("🇦🇫 کابل", "Asia/Kabul"),
    ("🇹🇷 استانبول", "Europe/Istanbul"),
    ("🇦🇪 دبی", "Asia/Dubai"),
    ("🇩🇪 برلین", "Europe/Berlin"),
    ("🇬🇧 لندن", "Europe/London"),
    ("🇨🇦 تورنتو", "America/Toronto"),
    ("🇺🇸 نیویورک", "America/New_York"),
]
TZ_LABELS = {name: label for label, name in TIMEZONES}

# گزینه‌های سؤال «چرا حساب را حذف می‌کنی؟»؛ کد در deleted_accounts.reason ذخیره می‌شود
DELETE_REASONS = (
    ("unused", "دیگه استفاده نمی‌کنم"),
    ("reminders", "یادآورها اذیت می‌کنن"),
    ("privacy", "نگرانی دربارهٔ حریم خصوصی"),
    ("other", "دلیل دیگه"),
)
DELETE_CONFIRM_WORD = "حذف"
