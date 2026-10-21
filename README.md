# کتابخونه مرجع
درود
ربات تلگرام برای استریک مطالعه. هر روز دکمه «امروز خوندم» رو می‌زنی و ربات سر ساعتی که گذاشتی یادآوری می‌کنه.

برای استفاده باید عضو @BOOKzMA و @ReferenceLibrary باشی.

## اجرا

‍‍cp .env.sample .env
docker compose up -d --build


توی `.env` مقدار `BOT_TOKEN` و `POSTGRES_PASSWORD` رو بذار. ربات باید ادمین هر دو کانال باشه.

پایتون، aiogram، Postgres، Alembic.