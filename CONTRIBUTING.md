# مشارکت

قبل از پیاده‌سازی، برای کار قابل‌تفکیک یک issue با هدف، معیار پذیرش و وابستگی‌ها بساز یا issue موجود را claim کن. هر issue یک مالک و branch خودش را دارد؛ روی branch مشترک کار نکنید و مستقیم روی `main` تغییر ندهید.

```sh
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c feat/123-short-topic
```

برای bug از `fix/123-short-topic` و برای مستندات از `docs/123-short-topic` استفاده کن. شماره را با issue واقعی جایگزین کن. اگر worktree کثیف است، تغییرها را پاک یا جابه‌جا نکن؛ ابتدا مالکیتشان را روشن کن.

هر branch فقط یک موضوع مستقل را پوشش دهد و با PR به `main` برسد. PR باید issue را با `Closes #123` ببندد، تغییرهای مرتبط را توضیح دهد و پس از CI/review merge شود. GitHub branch protection باید direct push/force-push به `main` را ببندد و CI را الزامی کند. فعال‌کردن **Automatically delete head branches** توصیه می‌شود؛ بعد از merge، branch محلی را هم حذف کن.

برای featureهای موازی، فایل‌ها/لایه‌های تحت مالکیت را از ابتدا بین issueها تقسیم کن. اگر feature دوم به اولی وابسته است، اول PR پایه را merge کن، سپس branch بعدی را از `main` به‌روز بساز. اگر overlap پیش‌بینی‌نشده پیش آمد، پیش از resolve کردن conflict با مالک دیگر هماهنگ کن؛ تغییرهای او را بی‌اجازه بازنویسی نکن.

هر feature باید تمام مسیرهای کاربر و پنل ادمین را بررسی کند. metric/actionهای ادمینِ مربوط به feature را همان‌جا به‌روز و تست کن، یا در spec/PR دلیلِ بی‌نیازی را بنویس. migration جدید برای schema لازم است؛ revision اعمال‌شده را ویرایش نکن. متن کاربر در `texts.py` بماند.

پیش از PR:

```sh
ruff check .
pytest
git diff --check
```

نتیجهٔ واقعی تست، تغییرهای schema، روش اجرای محلی و نیاز Docker را در PR بنویس. نسخهٔ هدف Python برای توسعه و CI، 3.12 است. راهنمای کامل branch، تست، merge، tag و deploy در [docs/WORKFLOW.md](docs/WORKFLOW.md) است.

Tag برای release قابل‌استقرار است، نه هر PR. اگر feature بلافاصله release می‌شود، پس از merge version را bump و tag بساز؛ اگر چند feature باهم منتشر می‌شوند، یک tag برای همان release کافی است.
