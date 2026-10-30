# روال شاخه، تست و انتشار

این روال برای هر feature و bug fix اجرا می‌شود. هیچ تغییری مستقیم روی `main` انجام نمی‌شود.

## قاعدهٔ الزامی برای هر ایجنت

هر ایجنتی که روی این پروژه کار می‌کند، در شروع کار **حتماً** یک برنچ جدا از `main` به‌روز می‌سازد و تمام کارش را روی همان انجام می‌دهد. هیچ‌وقت — بدون هیچ استثنایی — روی برنچ اصلی کار، ویرایش یا commit نکن.

## شروع کار

ابتدا branch و worktree را بررسی کن:

```sh
git branch --show-current
git status --short
```

اگر worktree تمیز است، `main` را به‌روز کن و branch تازه بساز:

```sh
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c feat/<short-topic>
```

برای bug fix از `fix/<short-topic>` و برای مستندات از `docs/<short-topic>` استفاده کن. اگر checkout محلی `main` وجود ندارد:

```sh
git switch --track -c main origin/main
```

اگر worktree کثیف است، تغییرهای موجود را پاک، stash یا جابه‌جا نکن. اگر همان کار در حال انجام روی یک branch غیر-main است، همان را ادامه بده؛ اگر مالکیت/ارتباط تغییرها روشن نیست، پیش از جابه‌جایی یا commit از مالک بپرس. روی `main` ویرایش نکن.

## چند مشارکت‌کننده و چند feature

- برای هر issue یک مالک و یک branch اختصاصی تعیین کن؛ روی branch مشترک یا `main` کار نکنید. نام branch شمارهٔ issue داشته باشد، مانند `feat/123-admin-export` یا `fix/456-reminder-time`.
- پیش از شروع، وابستگی و فایل‌های مشترک را در issue اعلام کن. دو feature مستقل می‌توانند موازی باشند، اما feature وابسته باید بعد از merge شدن PR پایه از `main` تازه branch بگیرد.
- هر PR یک موضوع و scope قابل review داشته باشد و با `Closes #123` به issue وصل شود. Conflict را با هماهنگی ownerها حل کن، نه با بازنویسی خاموش تغییر همکار.
- در GitHub repository settings برای `main` یک branch protection rule/ruleset فعال کن: PR اجباری، CI status checks اجباری، منع force-push و حذف branch اصلی. تعداد approval را متناسب با تیم انتخاب کن.
- گزینهٔ **Automatically delete head branches** را در GitHub فعال کن. پس از merge اگر فعال نیست، remote feature branch را دستی حذف کن؛ local branch را هم پس از رفتن به `main` با `git branch -d <branch>` پاک کن.

## تست محلی

`dev_run.py` launcher مشترک و tracked پروژه است؛ تنظیمات خصوصی در `.env` می‌مانند و نباید در
Git یا داخل launcher قرار بگیرند. token/proxy را در پیام یا log منتشر نکن.

```sh
docker compose up -d db
source .venv/bin/activate
alembic upgrade head
PYTHONPATH=src python dev_run.py
```

از bot token جداگانهٔ تست استفاده کن. `pgdata` volume پایدار است؛ DB را پاک یا recreate نکن. `docker compose up -d db` فقط دیتابیس را بالا می‌آورد و image بات را rebuild نمی‌کند. Migration را فقط وقتی `DATABASE_URL` به DB تست/محلی اشاره می‌کند اجرا کن. lifespan مشترک FastAPI migration را در startup اجرا می‌کند؛ قرارداد launcher محلی و تنظیمات لازم در [LOCAL_DEV](LOCAL_DEV.md) آمده است.

تست Docker لازم است وقتی Dockerfile، runtime dependencies، Compose یا خود image تغییر کرده باشد:

```sh
docker compose up -d --build
docker compose logs --tail=100 bot
```

## Commit و Pull Request

بعد از تست و بازبینی:

```sh
git status --short
git diff --check
git add <files-for-this-change>
git commit -m "feat: describe the change"
git push -u origin feat/<short-topic>
```

PR را از feature branch به `main` باز کن. پس از CI/review آن را merge کن؛ مستقیم به `main` push یا force-push نکن. Agent به‌صورت پیش‌فرض commit، push، merge یا tag نمی‌زند؛ دستورهای دقیق و branch واقعی را در تحویل نهایی می‌دهد.

## Tag و استقرار سرور

Tag برای release است، نه هر branch/PR. اگر هر feature بلافاصله قابل deploy است، پس از merge version پروژه را bump و tag annotated بساز. اگر چند feature باهم deploy می‌شوند، یک version/tag برای snapshot ترکیبی کافی است. پیش از tag، مطمئن شو version فایل‌های پروژه با tag هماهنگ است:

```sh
git switch main
git pull --ff-only origin main
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

روی سرور ابتدا backup خارج از repository بگیر و تنظیمات لازم را در `.env` به‌روز کن. سپس tag تأییدشده را deploy کن:

```sh
cd /path/to/BOOKzMA
git fetch origin --tags
git switch --detach vX.Y.Z
docker compose up -d --build bot
docker compose ps
docker compose logs --tail=100 bot
```

این دستور image سرویس bot را rebuild می‌کند و volume دیتابیس را حفظ می‌کند. Migrationها در startup اجرا می‌شوند. Logها را برای موفقیت migration، `polling` و `reminder loop started` بررسی کن؛ فقط یک نمونه با bot token production باید polling کند. اگر startup/migration شکست خورد، rollout را متوقف کن؛ downgrade/restore را بدون backup و بررسی سازگاری انجام نده. برای deploy `docker compose down -v` نزن.

## موارد الزامی در پایان هر کار

هر ایجنتی در پایان هر کار باید تحویل کامل بدهد؛ پایان کار بدون این موارد کامل نیست:

- دستور دقیق اجرای کد محلی (شامل start دیتابیس، migration و در صورت نیاز rebuild Docker).
- روش تست تغییر (چه چیزهایی را دستی بررسی کند) و تست‌ها/checkهای واقعاً اجراشده و خروجی واقعی‌شان و مواردی که اجرا نشده‌اند.
- در صورت تأیید مالک: دستورهای دقیق commit، push، بازکردن PR (با نام branch واقعی)، مرج‌کردن و پاک‌کردن branch محلی و ریموت پس از merge.
- مراحل پس از merge و استقرار (backup، migration، tag) در صورت وجود.
- branch واقعی، dirty/uncommitted بودن worktree و فایل‌های تغییرکرده.
- دستور اجرای bot محلی، نیاز یا عدم نیاز به DB start، migration محلی و rebuild Docker.
- فرمان‌های متناسب commit/push/PR/merge/tag؛ هیچ placeholderی را با branch/version حدسی جایگزین نکن.
- مراحل سرور پس از merge/tag، backup و migration لازم، و نام envهای لازم بدون افشای secret.
