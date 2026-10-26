FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# postgresql-client برای pg_dump/pg_restore (بکاپ از داخل کانتینر bot)؛ نسخهٔ کلاینت باید از سرور بزرگ‌تر یا مساوی باشد
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini .

EXPOSE 8000

RUN useradd --create-home --uid 10001 bot
USER bot

CMD ["uvicorn", "BOOKzMA.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
