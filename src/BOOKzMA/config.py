from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    # جدا از Settings تا alembic بدون توکن هم کار کنه
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://bookzma:bookzma@localhost:5433/bookzma"


class Settings(DatabaseSettings):
    bot_token: SecretStr
    telegram_proxy: SecretStr | None = None
    log_level: str = "INFO"
    web_origins: str = ""
    admin_telegram_ids: str = ""
    github_url: str = ""
    support_telegram_username: str = ""
    backup_dir: str = "/backups"
    backup_keep_local: int = 1
    rate_limit_max_updates: int = 20
    rate_limit_window_seconds: int = 10

    @property
    def admin_ids(self) -> frozenset[int]:
        ids: set[int] = set()
        for value in self.admin_telegram_ids.split(","):
            value = value.strip()
            if not value:
                continue
            if not value.isascii() or not value.isdecimal() or len(value) > 20:
                raise ValueError(
                    "ADMIN_TELEGRAM_IDS must contain comma-separated numeric Telegram IDs"
                )
            ids.add(int(value))
        return frozenset(ids)
