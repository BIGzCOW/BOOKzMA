from pathlib import Path

from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    # جدا از Settings تا alembic بدون توکن هم کار کنه
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://bookzma:bookzma@localhost:5433/bookzma"


class CatalogSettings(DatabaseSettings):
    channel_catalog_db_path: Path | None = None
    channel_catalog_channel_username: str = "BOOKzMA"
    channel_catalog_sync_hour_utc: int = Field(default=3, ge=0, le=23)
    meili_url: AnyHttpUrl | None = None
    meili_api_key: SecretStr | None = None
    meili_eval_api_key: SecretStr | None = None
    meili_index_name: str = Field(default="book_catalog", pattern=r"^[A-Za-z0-9_-]+$")
    meili_matching_strategy: Literal["frequency", "last"] = "frequency"
    meili_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    @field_validator("meili_api_key", "meili_eval_api_key", mode="before")
    @classmethod
    def empty_meili_api_key_is_unset(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def resolve_catalog_path(self) -> "Settings":
        candidates: list[Path] = []
        if self.channel_catalog_db_path is not None:
            candidates.append(self.channel_catalog_db_path)
        candidates.extend(
            [
                Path("/catalog/channel_data.db"),
                Path(__file__).resolve().parents[2]
                / "bookzma-core"
                / "core"
                / "data"
                / "channel_data.db",
                Path(__file__).resolve().parents[2].parent
                / "bookzma-core"
                / "core"
                / "data"
                / "channel_data.db",
            ]
        )
        for candidate in candidates:
            if candidate.exists():
                self.channel_catalog_db_path = candidate
                return self
        return self


class Settings(CatalogSettings):
    bot_token: SecretStr
    telegram_proxy: SecretStr | None = None
    web_origins: str = ""
    admin_telegram_ids: str = ""
    github_url: str = ""
    support_telegram_username: str = ""
    backup_dir: str = "backups"
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
