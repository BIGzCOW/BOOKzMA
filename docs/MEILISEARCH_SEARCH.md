# جست‌وجوی کاتالوگ با Meilisearch

تصمیم فنی این تغییر در D-14 ثبت شده است. PostgreSQL همچنان مرجع metadata کتاب‌ها، lookup نتیجه، افزودن به کتابخانه و `catalog_message_id` است. Meilisearch فقط index مشتق‌شدهٔ جستجو است؛ هیچ فایل یا `raw_data` از SQLite در آن ذخیره نمی‌شود.

## راه‌اندازی

Compose از image ثابت `getmeili/meilisearch:v1.56.1` استفاده می‌کند و index را در volume پایدار `meilidata` نگه می‌دارد. پورت فقط روی `127.0.0.1:7700` منتشر می‌شود. در `.env` یک `MEILI_MASTER_KEY` تصادفی با حداقل ۱۶ بایت بگذار؛ برای production از مقدار تازه و قوی استفاده کن. Master key برای مدیریت Meilisearch است و Compose آن را در کانتینر bot خالی می‌کند.

پس از بالا آمدن Meili، با master key یک API key محدود به index بساز. برای runtime، actionهای لازم عبارت‌اند از `search`, `documents.add`, `documents.delete`, `indexes.create`, `indexes.get`, `tasks.get`, `settings.update`, و `stats.get`. دسترسی index را به `book_catalog` و `book_catalog_*` محدود کن تا reindex/evaluation index هم پوشش داده شوند. کلید را در `MEILI_API_KEY` بگذار. برای evaluation یک `MEILI_EVAL_API_KEY` جدا بساز که علاوه بر این‌ها `indexes.delete` داشته باشد؛ این کلید به bot داده نمی‌شود.

متغیرهای اصلی در `.env.sample` آمده‌اند: `MEILI_URL`, `MEILI_API_KEY`, `MEILI_INDEX_NAME`, `MEILI_MATCHING_STRATEGY`, `MEILI_TIMEOUT_SECONDS`, `MEILI_MASTER_KEY`, و `MEILI_MAX_INDEXING_MEMORY`. در Compose آدرس bot به `http://meilisearch:7700` override می‌شود؛ `dev_run.py` روی میزبان باید از `http://127.0.0.1:7700` استفاده کند.

در توسعهٔ محلی:

```sh
docker compose up -d db meilisearch
```

Compose برای اجرای محلی هم `POSTGRES_PASSWORD`, `BOOKZMA_BACKUP_DIR`, و `MEILI_MASTER_KEY` غیرخالی می‌خواهد. ساخت index توسط reindex/evaluator انجام می‌شود؛ startup بات sync یا ساخت ۷۰۰هزار سند را اجرا نمی‌کند.

## ساخت و همگام‌سازی index

ساخت اولیه یا بازیابی دستی، خارج از بازهٔ sync شبانه:

```sh
python -m BOOKzMA.reindex_catalog
```

فرمان از تنظیمات `CatalogSettings` استفاده می‌کند و به `BOT_TOKEN` نیاز ندارد. ابتدا index/settings را آماده می‌کند، SQLite را read-only در batchهای ۱۰٬۰۰۰تایی می‌خواند، PostgreSQL را با source reconcile می‌کند، taskهای Meilisearch را تا پایان دنبال می‌کند و در آخر تعداد سندها را با PostgreSQL می‌سنجد. اجرای مجدد idempotent است. در Compose می‌توان فرمان را داخل کانتینر bot اجرا کرد:

```sh
docker compose exec bot python -m BOOKzMA.reindex_catalog
```

پس از آن، سرویس sync فقط روزی یک بار در `CHANNEL_CATALOG_SYNC_HOUR_UTC` (UTC، پیش‌فرض 03:00) اجرا می‌شود. هر بار کلیدهای `messages.id` را به ترتیب می‌خواند، اما فقط document hash متفاوت را upsert می‌کند؛ حذف یا تغییر `in_main`/duplicate را هم reconcile می‌کند. PostgreSQL تغییر و outbox را در یک transaction ثبت می‌کند. Outbox تا موفقیت Meili task باقی می‌ماند و خطا فقط با نوع exception ثبت می‌شود. SQLite همیشه read-only است و فقط main channel پردازش می‌شود.

اگر Meilisearch هنگام startup در دسترس نباشد، bot و Telegram polling بالا می‌آیند؛ سرچ پیام خطای دوستانه می‌دهد و outbox برای sync بعدی می‌ماند. Meilisearch dependency اجباری `depends_on` برای bot نیست.

## تنظیم relevance و ارزیابی

Index settings فیلدهای `title`, `file_name`, و `caption` را به همین ترتیب جستجو می‌کنند. قواعد ranking پیش‌فرض Meilisearch حفظ شده و `posted_at:desc` در انتها برای tie-break قرار دارد؛ `posted_at` sortable است. typo tolerance فعال است (یک typo از طول ۵ و دو typo از طول ۹)، typo روی اعداد غیرفعال است، stopwordهای فارسی محدودند و synonyms فعلاً خالی است. جستجو با `matchingStrategy=frequency` انجام می‌شود.

مجموعهٔ `tests/catalog_search_cases.json` شامل ۵۱ سناریوی synthetic است و جابه‌جایی ترتیب کلمات، اصطلاحات عمومی، caption-only، typo، گونه‌های املایی/رقم، انگلیسی و query ترکیبی را پوشش می‌دهد. برای مقایسهٔ strategyها از یک index موقت استفاده کن:

```sh
python -m BOOKzMA.evaluate_catalog_search
```

اجرای محلی ۲۰۲۶-۱۱-۰۷ روی ۱۸ سند synthetic و ۵۱ query: هر دو strategy برابر ۵۱/۵۱ (۱۰۰٪) بودند؛ `frequency` p50=3.74ms و p95=7.70ms، در برابر `last` با p50=3.30ms و p95=8.34ms. برای همین `frequency` پیش‌فرض انتخاب شد. این latency مربوط به index کوچک روی Docker محلی است، نه کاتالوگ ۷۰۰هزار‌تایی.

## بازیابی و موارد باز

Meilisearch index دادهٔ مشتق‌شده است و از روی SQLite/PostgreSQL قابل بازسازی است؛ volume آن در `pg_dump` نیست. برای بازیابی، بالا بیاور و reindex را اجرا کن. پیش از deploy واقعی باید SQLite مجاز read-only در دسترس باشد تا schema/اندازه و latency p50/p95 روی corpus واقعی بررسی شود. فایل SQLite در workspace فعلی موجود نبود، پس نتیجهٔ کیفیت و latency روی دادهٔ واقعی هنوز تأیید نشده است.

جستجوی semantic/embedding، transliteration، synonyms محتوایی، استخراج عنوان/نویسنده و OCR خارج از این مرحله‌اند. کتابخانهٔ شخصی کاربر، افزودن کتاب و دریافت خصوصی با `copyMessage` تغییر نکرده‌اند.
