# مشخصات قابلیت: کتابخانهٔ شخصی و ثبت صفحات مطالعه

## شناسهٔ ROADMAP

S-01، B-03 و B-06

## چرا

ثبت فعلی فقط می‌گوید کاربر امروز مطالعه کرده است. نسخهٔ اول کتابخانه به کاربر اجازه می‌دهد
کتاب در حال مطالعه را با نام، نویسندهٔ اختیاری و تعداد کل صفحات نگه دارد، چند نوبت مطالعه در
یک روز ثبت کند و پیشرفت واقعی را ببیند؛ هر ثبت مثبت همچنان روز مطالعه و استریک فعلی را فعال
می‌کند.

**تأیید مالک (۲۰۲۶-۱۰-۲۸):** ورود تعداد صفحات خوانده‌شده، نویسندهٔ اختیاری، سقف ۱۰ کتاب
فعال، آرشیو به‌جای حذف، شروع پیشرفت از صفر، حفظ دکمهٔ «امروز خوندم» و عدم گسترش API تأیید
شد. چند ثبت برای یک کتاب در یک روز ترجیح داده شد.

## رفتار از دید کاربر

1. «📚 کتابخانهٔ من» از خانه یا کیبورد دائمی در چت خصوصی باز می‌شود؛ در گروه فقط پیام راهنمای
   ورود به چت خصوصی نمایش داده می‌شود، بدون عنوان یا سابقهٔ کتاب‌ها.
2. افزودن کتاب نام الزامی، نویسندهٔ اختیاری و تعداد کل صفحات ۱ تا ۱۰۰٬۰۰۰ را می‌گیرد.
3. هر کاربر حداکثر ۱۰ کتاب `reading` دارد؛ کتاب تمام‌شده یا آرشیوشده در سقف نیست.
4. کاربر یک کتاب فعال را انتخاب و تعداد صفحات همان نوبت را وارد می‌کند. چند پیام مستقل در یک
   روز مجاز است؛ retry همان پیام Telegram دوباره شمرده نمی‌شود.
5. ثبت صفحه و `reading_logs` در یک transaction انجام می‌شوند. ثبت اول روز تمام side effectهای
   موجود مطالعه (freeze، comeback، badge و پیشنهاد تلنگر به رفیق) را اجرا می‌کند.
6. مجموع صفحات از کل کتاب بیشتر نمی‌شود؛ رسیدن دقیق به کل، وضعیت را `finished` می‌کند.
   درصد رو به پایین نمایش داده می‌شود؛ مثلاً ۱۹۹ از ۲۰۰ صفحه برابر ۹۹٪ است.
7. آرشیو با تأیید انجام می‌شود؛ کتاب و لاگ‌ها حذف نمی‌شوند و بازگردانی در نسخهٔ اول وجود ندارد.
8. رفتن به منو، فرمان یا صفحهٔ دیگر فرم ناتمام را می‌بندد. برای ثبت صفحات پس از جابه‌جایی باید
   دوباره دکمهٔ ثبت مطالعهٔ همان کتاب را زد؛ متن منو یا فرمان، نام کتاب/نویسنده محسوب نمی‌شود.

## اثر روی کل محصول

- مسیرهای کاربر: دکمهٔ خانه و reply keyboard، callback/FSM جدید، ثبت روز مطالعه، استریک،
  یادآورها، گزارش هفتگی، نشان/freeze/comeback و پیشنهاد buddy بررسی و هماهنگ می‌شوند.
- API: تغییر نمی‌کند؛ کلاینت فعالی برای کتابخانه تأیید نشده است.
- پروفایل/لیدربورد: از همان `reading_logs` استفاده می‌کنند و قراردادشان تغییر نمی‌کند.
- پنل ادمین: سه KPI تجمیعی و بدون دادهٔ شخصی اضافه می‌شود: کتاب فعال، کتاب تمام‌شده و صفحات
  ثبت‌شده در هفت روز اخیر. action/filter تازه لازم نیست.
  اصلاحات حریم خصوصی و فرم، KPI یا action دیگری لازم ندارند؛ عملیات ردشده دادهٔ کتاب نمی‌سازد.
- scheduler: بعد از ثبت صفحه، `reading_logs` موجود باعث می‌شود یادآور همان روز ارسال نشود.
- کاربران موجود: کتابخانهٔ خالی دارند؛ هیچ backfill لازم نیست و دکمهٔ سادهٔ «امروز خوندم» باقی
  می‌ماند.

## داده و حریم خصوصی

- `user_books`: مالک، نام، نویسندهٔ اختیاری، کل صفحات، وضعیت و زمان‌های ساخت/اتمام/آرشیو.
- `page_logs`: کتاب، روز محلی، صفحات، `source_message_id` برای idempotency و زمان ساخت.
- نام کتاب/نویسنده و سابقهٔ صفحات دادهٔ شخصی کاربر است؛ فقط خود کاربر می‌تواند آن را ببیند.
- حذف حساب با FKهای `ON DELETE CASCADE` هر دو جدول را پاک می‌کند. آرشیو داده را نگه می‌دارد.
- FSM فقط دادهٔ فرم ناتمام را در حافظه نگه می‌دارد و با restart از بین می‌رود. داده‌های پایدار
  مانند بقیهٔ PostgreSQL در backup قرار می‌گیرند.

## حالت‌های خاص

- سقف ۱۰ کتاب با قفل ردیف user در برابر درخواست هم‌زمان محافظت می‌شود.
- `SimpleEventIsolation` آپدیت‌های هر کلید user/chat را قبل از خواندن FSM سریال می‌کند؛ بعد از
  commit، فرم پاک می‌شود. پیام آخر هم‌زمان یا retry آن در همان فرم کتاب تکراری نمی‌سازد؛
  این تضمین برای تک‌پروسس فعلی است و جایگزین dedup پایدار کل آپدیت‌ها نیست.
- ثبت صفحه با قفل ردیف کتاب مجموع را سریال می‌کند؛ unique روی `(user_book_id,
  source_message_id)` retry همان پیام را idempotent می‌کند.
- روز ثبت با timezone کاربر محاسبه می‌شود؛ تغییر timezone سوابق قبلی را جابه‌جا نمی‌کند.
- خطای DB پیش از commit نه page log و نه reading log را نیمه‌کاره باقی نمی‌گذارد.
- restart فرم ناتمام را می‌بندد؛ کاربر از کتابخانه دوباره شروع می‌کند.

## امنیت و مجوز

- همهٔ queryها هم‌زمان `book_id` و `user_id` را بررسی می‌کنند.
- routerهای کتابخانه و فرم فقط چت خصوصی را می‌پذیرند؛ گروه و callback بدون پیام در دسترس،
  پیش از query کتاب با پیام عمومی رد می‌شوند.
- callbackها فقط ID عددی محدود دارند و زیر ۶۴ بایت‌اند.
- نام و نویسنده طول محدود دارند و هنگام نمایش HTML escape می‌شوند؛ صفحات عدد صحیح مثبت و
  محدود است.
- dependency، env یا سرویس خارجی تازه‌ای اضافه نمی‌شود.

## خارج از محدوده

- Open Library/Goodreads، جلد، ISBN، لینک، امتیاز، یادداشت و اشتراک‌گذاری.
- ویرایش ثبت اشتباه، حذف دائمی، بازگردانی آرشیو و پیشرفت اولیهٔ غیرصفر.
- API کتابخانه و آمار شخصی گسترده‌تر.

## تصمیم‌های باز برای مالک

ندارد؛ تصمیم‌های نسخهٔ اول در Issue تأیید شده‌اند.

## معیارهای پذیرش

- [x] رفتار و خطاهای اصلی روشن و آزمون‌پذیر است.
- [x] تست منطق خالص و حالت‌های مرزی تعریف شده است.
- [x] همهٔ مسیرهای ورودی و مصرف‌کننده‌های داده بررسی شده‌اند؛ موارد نامرتبط دلیل دارند.
- [x] اثر بر پنل ادمین و آمار تعیین شده و KPIهای لازم تست دارند.
- [x] Ruff و کل pytest با Python 3.12/PostgreSQL 16 اجرا شده‌اند؛ هیچ تستی skip نشده است.
- [x] Docker build/startup آزمایشی بررسی شد؛ مالک launcher و جریان اصلی تلگرام را اجرا کرد.
- [x] اسناد current behavior و ROADMAP همراه کد به‌روز شده‌اند.
- [x] migration، callback/API، امنیت، کارایی و rollback بررسی شده‌اند.

## تحویل و بررسی قبل از انتشار

شاخه: `feat/personal-library`؛ پیاده‌سازی و اصلاحات فعلاً commit/push نشده‌اند.
چک‌لیست add-feature در بررسی کل مسیرها، حریم خصوصی و حفظ آمار ادمین اعمال شده است.
اصلاحات بازبینی migration یا dependency دیگری اضافه نمی‌کنند؛ کل فیچر همچنان migration
`0017` را نیاز دارد و API، قواعد streak و سرویس‌های deployment جدیدی اضافه نشده‌اند.

نتیجهٔ بررسی نهایی قبل از push — ۲۰۲۶-۱۰-۲۹:

- image اصلی با Dockerfile فعلی و Python **3.12.16** ساخته شد. proxy محلی فقط به‌صورت
  build argument استفاده شد و تنظیمات پروژه/daemon عوض نشد. کاربر runtime برابر UID 10001
  است؛ `.env`، launcher محلی و متغیرهای proxy مربوط به build در image runtime وجود ندارند.
- کل مجموعه در محیط توسعهٔ ساخته‌شده روی همان image، با PostgreSQL 16 واقعی و داده‌های
  ساختگی: **۲۲۰ موفق، صفر شکست، صفر skip، یک هشدار**؛ pytest با گزینه‌های
  `-q --tb=short -p no:cacheprovider` اجرا شد. اجرای قبلی روی Python 3.11 نیز ۲۲۰ موفق بود.
- تنها هشدار مربوط به deprecation استفاده از httpx در Starlette TestClient است؛ برای رفع
  آن dependency تازه‌ای به این فیچر اضافه نشده است.
- migration آنلاین از DB خالی به `0016` و `0017`، سپس downgrade به `0016` و upgrade دوباره
  به head موفق بود. ساختار `user_books` و `page_logs` با مدل‌های SQLAlchemy مطابقت داشت.
- API از image اصلی، با polling خاموش و تنظیمات ساختگی روی DB موقت startup موفق داشت؛
  `/health` و `/openapi.json` برابر ۲۰۰ و درخواست بدون احراز هویت `/api/v1/me` برابر ۴۰۱ بود.
  قرارداد API حفظ شده و endpoint کتابخانه اضافه نشده است.
- `.venv/bin/ruff check .`، `git diff --check` و compileall موفق بودند. اسکن الگوهای پرخطر
  token/private-key در فایل‌های تغییرکرده موردی نیافت؛ این اسکن محدود جای ممیزی کامل secrets
  نیست. فایل `.env` و محتوای `dev_run.py` خوانده نشدند.
- `git fetch origin` انجام شد؛ مبنای شاخه با `origin/main` هم‌سطح بود (ahead/behind: صفر/صفر).
  فایل‌های جدید فیچر هنوز untracked هستند و باید هنگام commit در stage قرار بگیرند.
- بات با توکن واقعی توسط ایجنت اجرا نشد؛ مالک گزارش کرده جریان تست تلگرام کار می‌کند.
  CI پس از بازشدن PR و بازبینی مالک همچنان الزامی است؛ تست محلی جای تأیید CI را نمی‌گیرد.
- DB و کانتینر API آزمایشی مستقل و دارای دادهٔ موقت tmpfs بودند؛ پس از بررسی پاک شدند.
  به volumeها، دیتابیس محلی مالک یا بات در حال اجرای او دست زده نشد.

فایل‌های اصلی فیچر:

- `src/BOOKzMA/handlers/books.py`، `repositories/books.py` و `services/books.py`؛ فرم/ناوبری،
  queryهای مالک‌دار و منطق پیشرفت.
- `services/reading_registration.py` و `handlers/streak.py`؛ ثبت مشترک روز مطالعه.
- `bot.py`، `handlers/__init__.py`، `middlewares/book_flow.py` و `handlers/start.py`؛
  isolation، ترتیب منوها و بستن فرم قدیمی.
- `db/models.py`، `migrations/versions/0017_personal_library.py`، `constants.py`، `utils.py`،
  `texts.py`، `keyboards.py`، `handlers/common.py` و `repositories/analytics.py`.
- `tests/conftest.py`، `tests/test_books.py`، `tests/test_books_flow.py`،
  `tests/test_books_db.py`، `tests/test_bot.py` و `tests/test_account_deletion_db.py`.
- اسناد: `ARCHITECTURE.md`، `BOT_GUIDE.md`، `README.md`، `docs/DECISIONS.md`،
  `docs/LOCAL_DEV.md`، `docs/ROADMAP.md`، `docs/SECURITY_PRACTICES.md`، `docs/TESTING.md`،
  `docs/WORKFLOW.md`، همین spec و `docs/specs/account-deletion.md`.

### اجرای محلی

ابتدا Python 3.12 و requirements توسعه را طبق [LOCAL_DEV](../LOCAL_DEV.md) آماده کن؛ از توکن
بات تست و DB محلی استفاده کن. `.env` موجود را بازنویسی نکن. `POSTGRES_PASSWORD` و
`BOOKZMA_BACKUP_DIR` باید مقدار داشته باشند؛ `DATABASE_URL` برای launcher باید به
`127.0.0.1:5433` و همان رمز محلی اشاره کند.

```sh
git switch feat/personal-library
source .venv/bin/activate
docker compose config --quiet
docker compose up -d db
docker compose stop bot
alembic upgrade head
alembic current
PYTHONPATH=src python dev_run.py
```

انتظار: head برابر `0017`، startup بدون خطا، فقط یک polling consumer. برای اجرای host نیازی
به rebuild بات نیست. برای تست خود image با تنظیمات تست، launcher را متوقف کن و اجرا کن:

```sh
docker compose up -d --build bot
docker compose logs --tail=100 -f bot
```

### تست خودکار و دستی

```sh
ruff check .
pytest -q
git diff --check
```

تست‌های بدون DB و Telegram اکنون `.env` را نمی‌خوانند. برای تست واقعی repositoryها، یک DB
جدا و قابل‌حذف بساز و URL آن را فقط در shell خودت به `TEST_DATABASE_URL` بده؛ مقدار secret
را در issue/log منتشر نکن. پس از اطمینان از آزمایشی‌بودن مقصد:

```sh
DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head
pytest tests/test_books_db.py tests/test_account_deletion_db.py -q
pytest -q
```

موارد smoke با بات تست:

1. کتاب ۱۰۰صفحه‌ای با/بدون نویسنده بساز؛ پیشرفت اولیه صفر و HTML عنوان متن عادی باشد.
2. ۱۰ و سپس ۱۵ صفحه در همان روز ثبت کن؛ پیشرفت ۲۵، یک روز مطالعه و یک بار side effectها.
3. ۷۶ صفحه رد شود؛ ۷۵ صفحه کتاب را تمام کند و یک جای کتاب فعال آزاد شود.
4. کتاب ۲۰۰صفحه‌ای با ۱۹۹ صفحه، ۹۹٪ و وضعیت در حال مطالعه نشان دهد.
5. در هر مرحلهٔ فرم، پروفایل/یادآورها/منوی دیگر را باز کن؛ فرم قدیمی نباید ادامه پیدا کند.
6. ثبت صفحات A را شروع کن، از پیام قدیمی B را باز کن و عدد بفرست؛ برای A ثبت نشود.
7. ۱۰ کتاب فعال مجاز و کتاب یازدهم رد شود؛ آرشیو تأیید بخواهد و داده را نگه دارد.
8. دکمه/فرمان کتابخانه در گروه عنوان یا پیشرفت منتشر نکند.
9. دکمهٔ قدیمی «امروز خوندم»، پروفایل، خلاصه، leaderboard و یادآورهای همان روز درست بمانند.
10. پنل ادمین KPI کتاب فعال/تمام‌شده و صفحات هفته را نشان دهد؛ حذف حساب سوابق کتاب را پاک کند.

### Commit، PR و merge پس از تأیید

تغییرها را با `git status --short` و `git diff` بازبینی کن و فقط فایل‌های همین فیچر را stage کن:

```sh
git add ARCHITECTURE.md BOT_GUIDE.md README.md \
  docs/DECISIONS.md docs/LOCAL_DEV.md docs/ROADMAP.md \
  docs/SECURITY_PRACTICES.md docs/TESTING.md docs/WORKFLOW.md \
  docs/specs/account-deletion.md docs/specs/personal-library-pages.md \
  migrations/versions/0017_personal_library.py \
  src/BOOKzMA/bot.py src/BOOKzMA/constants.py src/BOOKzMA/db/models.py \
  src/BOOKzMA/handlers/__init__.py src/BOOKzMA/handlers/books.py \
  src/BOOKzMA/handlers/common.py src/BOOKzMA/handlers/start.py \
  src/BOOKzMA/handlers/streak.py src/BOOKzMA/keyboards.py \
  src/BOOKzMA/middlewares/book_flow.py src/BOOKzMA/repositories/analytics.py \
  src/BOOKzMA/repositories/books.py src/BOOKzMA/services/books.py \
  src/BOOKzMA/services/reading_registration.py src/BOOKzMA/texts.py src/BOOKzMA/utils.py \
  tests/conftest.py tests/test_books.py tests/test_books_flow.py tests/test_books_db.py \
  tests/test_bot.py tests/test_account_deletion_db.py
git diff --cached --check
git commit -m "feat: add private personal library and page logging"
```

`origin` فعلی به `BIGzCOW/BOOKzMA`، یعنی مخزن مالک، اشاره دارد. اگر دسترسی write نداری،
اول در GitHub از همین مخزن Fork بساز؛ سپس URL معمول HTTPS fork خودت را بدون token وارد کن.
این کار `origin` را تغییر نمی‌دهد. اگر remote با نام `fork` از قبل وجود دارد، فرمان add را
تکرار نکن و مقصد آن را پیش از push بررسی کن:

```sh
read -r -p 'Your fork HTTPS URL: ' bookzma_fork_url
git remote add fork "$bookzma_fork_url"
git push -u fork feat/personal-library
```

در GitHub دکمهٔ Compare & pull request را بزن؛ base برابر `BIGzCOW/BOOKzMA:main` و head
برابر شاخهٔ `feat/personal-library` در fork خودت باشد. عنوان پیشنهادی:
`feat: personal library and page tracking`. بدنه باید رفتار نسخهٔ اول، نتیجهٔ ۲۲۰ تست،
migration `0017` و محدودیت‌های باقی‌مانده را خلاصه کند. اگر دسترسی write مستقیم داری،
به‌جای remote fork می‌توانی `git push -u origin feat/personal-library` اجرا کنی.

PR باید issue تأییدشده را لینک کند؛ شمارهٔ issue در این workspace مشخص نشده و نباید حدس زد.
CLI ابزار `gh` در محیط بررسی نصب نبود؛ ساخت PR، انتظار برای CI و merge از UI گیت‌هاب هم
ممکن است. اگر gh را از قبل داری، فرمان معادل ساخت PR روی fork:

```sh
read -r -p 'Your GitHub username: ' bookzma_fork_owner
gh pr create --repo BIGzCOW/BOOKzMA --base main \
  --head "${bookzma_fork_owner}:feat/personal-library" \
  --title "feat: personal library and page tracking" \
  --body-file docs/specs/personal-library-pages.md
```

پس از CI سبز و review، مالک PR را در GitHub merge می‌کند. اگر gh و مجوز merge داری و روش
merge commit در مخزن مجاز است، پس از واردکردن URL واقعی PR:

```sh
read -r -p 'Approved PR URL: ' bookzma_pr_url
gh pr checks "$bookzma_pr_url" --watch
gh pr merge "$bookzma_pr_url" --merge
git switch main
git pull --ff-only origin main
git branch -d feat/personal-library
git push fork --delete feat/personal-library
```

برای push مستقیم، remote حذف را `origin` بگذار؛ برای fork همان `fork` است. اگر GitHub شاخهٔ
remote را خودکار حذف کرد، فرمان حذف remote لازم نیست. اگر مالک squash را
انتخاب کرد و `git branch -d` رد شد، پیش از حذف اجباری برابری تغییرها با main بررسی شود.

### استقرار پس از merge

قبل از انتشار از پنل ادمین backup بگیر و طبق [BACKUP](../BACKUP.md) قابل‌خواندن‌بودنش را
بررسی کن. تگ release را مالک پس از هماهنگ‌کردن version انتخاب می‌کند؛ این فیچر تگ جدیدی
نساخته است. روی سرور پس از انتخاب تگ تأییدشده:

```sh
git fetch origin --tags
read -r -p 'Approved release tag: ' bookzma_release_tag
git switch --detach "$bookzma_release_tag"
docker compose up -d --build bot
docker compose ps
docker compose logs --tail=200 bot
```

Migration `0017` در startup اجرا می‌شود؛ image بات به‌علت تغییر کد باید rebuild شود.
موفقیت migration، polling و reminder loop بررسی شود؛ فقط یک instance فعال باشد.
در صورت شکست rollout، بدون بررسی backup و سازگاری، downgrade/restore انجام نده؛ downgrade
`0017` دو جدول کتاب و صفحات را حذف می‌کند. `docker compose down -v` برای deploy لازم نیست.
تصمیم محصول باز نداریم؛ تأیید CI، بازبینی PR و انتخاب نسخه/زمان انتشار با مالک است.
