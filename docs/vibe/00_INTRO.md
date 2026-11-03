# شروع دوباره با BOOKzMA

BOOKzMA یک ربات فارسی مطالعه در تلگرام است و در کد فعلی یک API مبتنی بر FastAPI هم دارد. API و ربات در اجرای Docker داخل یک برنامه بالا می‌آیند. کد مرجع نهایی است؛ مستندات قدیمی در این تغییر با کد تطبیق داده شده‌اند، اما هیچ مستندی جای بررسی فایل واقعی یا تست را نمی‌گیرد. کیفیت کلی کد به‌صورت مستقل ممیزی کامل نشده است.

## پنج قدم برای برگشتن به کار

1. `git status --short --branch` و `git log -5 --oneline` را ببین.
2. `docs/ROADMAP.md` را برای وضعیت‌ها بخوان؛ «ایده» مجوز اجرا نیست.
3. `docs/LOCAL_DEV.md` را بخوان و تفاوت محیط محلی و production را در نظر بگیر.
4. `ruff check . && pytest` را اجرا و نتیجهٔ واقعی را ثبت کن.
5. برای قابلیت جدید spec بساز، بعد با [کتابخانه promptها](PROMPTS.md) برنامه بگیر (P-02).

## دنبال چه چیزی هستی؟

| می‌خواهم بدانم... | فایل |
| --- | --- |
| قانون عامل و دستورهای کار | `AGENTS.md` |
| معماری و جریان فعلی | `ARCHITECTURE.md` |
| فرمان‌ها، callbackها، API، جدول‌ها و env | `BOT_GUIDE.md` |
| تصمیم‌های ثبت‌شده | `docs/DECISIONS.md` |
| ایده‌ها و وضعیت قابلیت‌ها | `docs/ROADMAP.md` |
| اجرای محلی و production | `docs/LOCAL_DEV.md` |
| تست‌ها | `docs/TESTING.md` |
| امنیت | `docs/SECURITY_PRACTICES.md` و `SECURITY.md` |
| عملکرد | `docs/PERFORMANCE.md` |
| طرح بکاپ | `docs/BACKUP.md` |
| ساخت spec | `docs/specs/TEMPLATE.md` |
| راهنمای کار با AI | `docs/vibe/GUIDE.md` |
| prompt آماده | `docs/vibe/PROMPTS.md` |

کد واقعیت را تعیین می‌کند؛ مستندات مسیر پیدا کردن آن را کوتاه می‌کنند. اگر چیزی در docs با implementation ناسازگار است، اول اختلاف را ثبت کن و بعد مستند canonical را اصلاح کن. `dev_run.py` محلی و خصوصی است؛ محتوایش را به AI نده.