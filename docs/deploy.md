# نصب روی سرور

## اولین بار

Docker و docker compose رو نصب کن، بعد:

```bash
git clone <آدرس ریپو> && cd BOOKzMA
cp .env.sample .env
nano .env        # BOT_TOKEN و POSTGRES_PASSWORD
docker compose up -d --build
docker compose logs --tail=30 bot
```

سرویس FastAPI داخل کانتینر روی پورت `8000` بالا می‌آید؛ روی میزبان فقط از `127.0.0.1:8000` در دسترس است. برای دسترسی عمومی وب‌سایت، آن را پشت reverse proxy با HTTPS قرار بده. مستند تعاملی API در `/docs` است.

توی لاگ باید `reminder loop started` و شروع polling را ببینی. migrationهای Alembic قبل از اجرای برنامه خودکار اجرا می‌شوند.

قبلش مطمئن شو تنظیمات کانال و دسترسی ربات را در `.env` درست کرده‌ای و فقط یک نمونه با توکن production polling می‌کند. محیط توسعهٔ محلی باید از ربات تست با توکن جدا استفاده کند؛ جزئیات launcher محلی در `docs/LOCAL_DEV.md` است.

### کاتالوگ SQLite کانال (اختیاری)

برای جست‌وجوی کاتالوگ، مسیر پوشهٔ دیتابیس SQLite ابزار کانال را در `.env` به مسیر واقعی میزبان بده؛ volume داخل کانتینر فقط‌خواندنی است و خود importer فقط metadata کانال اصلی را به PostgreSQL می‌فرستد:

```dotenv
BOOKZMA_CATALOG_DB_HOST_DIR=/home/bigcow/bookzma-core/core/data
CHANNEL_CATALOG_DB_PATH=/catalog/channel_data.db
CHANNEL_CATALOG_CHANNEL_USERNAME=BOOKzMA
CHANNEL_CATALOG_SYNC_HOUR_UTC=3
```

فایل را به repository یا volume دیتابیس PostgreSQL کپی نکن. اگر مسیر فایل تنظیم نشود یا در دسترس نباشد، sync کاتالوگ اجرا نمی‌شود و bot عادی بالا می‌آید. sync اولیه بعد از startup شروع می‌شود؛ بعد از تمام‌شدن آن، sync بعدی هر روز در ساعت UTC تنظیم‌شده انجام می‌شود. در لاگ، فقط تعداد ردیف‌های upsertشده یا نوع خطا ثبت می‌شود، نه filenameها یا `raw_data`. برای deploy، image سرویس bot را rebuild کن تا migration و task جدید نصب شوند.

## آپدیت

تغییر را اول با PR به `main` merge و نسخه را tag کن. روی سرور پیش از به‌روزرسانی backup بگیر و `.env` را با envهای موردنیاز نسخه هماهنگ کن؛ مقدار secret را وارد Git یا log نکن. سپس tag تأییدشده را deploy کن:

```bash
cd /path/to/BOOKzMA
git fetch origin --tags
git switch --detach vX.Y.Z
docker compose up -d --build bot
docker compose ps
docker compose logs --tail=100 bot
```

این دستور image سرویس bot را rebuild می‌کند و volume دیتابیس را حفظ می‌کند. migrationها در startup اجرا می‌شوند؛ logها را برای migration و شروع polling بررسی کن. برای deploy `docker compose down -v` اجرا نکن. روال کامل در [docs/WORKFLOW.md](WORKFLOW.md) است.

## بکاپ

```bash
docker compose exec -T db pg_dump -U bookzma bookzma | gzip > backup-$(date +%F).sql.gz
```

بکاپ رو جایی غیر از همین سرور هم نگه دار. برای زمان‌بندی روزانه می‌تونی توی crontab بذاریش.

بازیابی روی یه دیتابیس خالی:

```bash
gunzip -c backup-2026-10-21.sql.gz | docker compose exec -T db psql -U bookzma bookzma
```

## نکته‌ها

- `docker compose down -v` دیتابیس رو پاک می‌کنه، فقط وقتی داده مهمی نداری بزنش. `docker compose down` بدون `-v` مشکلی نداره.
- `POSTGRES_PASSWORD` بعد از اولین اجرا عوض نمی‌شه. اگه مجبور شدی، رمز رو با `ALTER USER` توی خود Postgres عوض کن.
- پورت دیتابیس فقط روی `127.0.0.1:5433` باز می‌شه و از بیرون سرور قابل دسترسی نیست.
- از ربات فقط یه نمونه باید با polling اجرا بشه.
