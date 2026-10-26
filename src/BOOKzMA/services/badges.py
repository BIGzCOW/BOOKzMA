"""منطق نشان‌های دستاورد (G-01): کدام نشان‌ها با این ثبت مطالعه باید اهدا شوند."""

from BOOKzMA.constants import MILESTONES

FIRST_READ = "first_read"
COMEBACK_RESTORED = "comeback_restored"

SPECIAL_LABELS = {
    FIRST_READ: "⭐ اولین مطالعه",
    COMEBACK_RESTORED: "🔁 بازگشت قهرمان",
}


def badge_label(code: str) -> str:
    if code in SPECIAL_LABELS:
        return SPECIAL_LABELS[code]
    if code.startswith("streak_"):
        return f"🔥 {code.removeprefix('streak_')} روز"
    return code


def badges_earned(*, streak: int, total_read_days: int, comeback_restored: bool) -> list[str]:
    """streak = استریک نمایشی بعد از همین ثبت؛ total_read_days شامل امروز."""
    codes: list[str] = []
    if total_read_days == 1:
        codes.append(FIRST_READ)
    if streak in MILESTONES:
        codes.append(f"streak_{streak}")
    if comeback_restored:
        codes.append(COMEBACK_RESTORED)
    return codes
