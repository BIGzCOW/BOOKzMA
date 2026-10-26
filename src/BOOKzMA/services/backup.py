import asyncio
import importlib.util
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from BOOKzMA.config import Settings

log = logging.getLogger(__name__)

BACKUP_NAME_RE = re.compile(r"^bookzma-(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})(\d{2})\.dump$")
DUMP_TIMEOUT_SEC = 900
RESTORE_TIMEOUT_SEC = 1800
STDERR_LOG_LIMIT = 500


class BackupError(RuntimeError):
    """خطای عملیاتی بکاپ/بازگردانی؛ پیامش برای نمایش به ادمین ایمن است."""


@dataclass(frozen=True)
class DumpTarget:
    host: str
    port: int
    user: str
    dbname: str
    password: str


@dataclass(frozen=True)
class BackupInfo:
    name: str
    size_bytes: int
    created_at: datetime


def backup_filename(now: datetime) -> str:
    return "bookzma-" + now.astimezone(timezone.utc).strftime("%Y-%m-%d-%H%M%S") + ".dump"


def parse_backup_name(name: str) -> datetime | None:
    match = BACKUP_NAME_RE.fullmatch(name)
    if match is None:
        return None
    try:
        return datetime(
            *(int(part) for part in match.groups()), tzinfo=timezone.utc
        )
    except ValueError:
        # الگو درست است ولی تاریخ نامعتبر است (مثل ماه ۱۳)
        return None


def select_to_delete(names: list[str], keep: int) -> list[str]:
    """جدیدترین `keep` بکاپ معتبر می‌ماند؛ بقیهٔ بکاپ‌های معتبر حذف می‌شوند.

    فایل‌های ناآشنا (نامشان با الگوی بکاپ نمی‌خواند) دست ما نیستند و برگردانده نمی‌شوند.
    """
    known = sorted(
        ((parse_backup_name(name), name) for name in names),
        key=lambda pair: pair[0] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    valid = [name for created, name in known if created is not None]
    return valid[max(keep, 0):]


def parse_dump_target(database_url: str) -> DumpTarget:
    parts = urlsplit(database_url)
    if parts.scheme not in {"postgresql", "postgresql+asyncpg"}:
        raise BackupError("آدرس دیتابیس پشتیبانی نمی‌شود.")
    if not parts.hostname or not parts.path.lstrip("/"):
        raise BackupError("آدرس دیتابیس ناقص است.")
    return DumpTarget(
        host=parts.hostname,
        port=parts.port or 5432,
        user=unquote(parts.username or ""),
        dbname=parts.path.lstrip("/"),
        password=unquote(parts.password or ""),
    )


def _source_root() -> Path:
    # find_spec سورس را پیدا می‌کند بدون اینکه پکیج را اجرا کند
    spec = importlib.util.find_spec("BOOKzMA")
    if spec is None or spec.origin is None:
        return Path.cwd()
    return Path(spec.origin).resolve().parent.parent


def is_unsafe_backup_dir(backup_dir: Path | str) -> bool:
    """مسیر بکاپ نباید داخل درخت سورس باشد تا فایل داده هرگز به گیت راه پیدا نکند."""
    root = _source_root()
    try:
        Path(backup_dir).resolve().relative_to(root)
    except ValueError:
        return False
    return True


def list_backups(settings: Settings) -> list[BackupInfo]:
    backup_dir = Path(settings.backup_dir)
    if not backup_dir.is_dir():
        return []
    items = []
    for path in backup_dir.iterdir():
        if path.is_file() and parse_backup_name(path.name) is not None:
            stat = path.stat()
            items.append(
                BackupInfo(
                    name=path.name,
                    size_bytes=stat.st_size,
                    created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                )
            )
    return sorted(items, key=lambda info: info.name, reverse=True)


def _pg_env(target: DumpTarget) -> dict[str, str]:
    return {**os.environ, "PGPASSWORD": target.password}


def _stderr_tail(stderr: bytes) -> str:
    return stderr.decode(errors="replace").strip()[-STDERR_LOG_LIMIT:]


async def _run_pg(args: list[str], target: DumpTarget, *, timeout: int) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        env=_pg_env(target),
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        raise BackupError("عملیات بیش از حد طول کشید و متوقف شد.")
    if proc.returncode != 0:
        raise BackupError("ابزار پایگاه داده با خطا متوقف شد.")
    return stderr


async def run_backup(settings: Settings, *, now: datetime | None = None) -> BackupInfo:
    target = parse_dump_target(settings.database_url)
    backup_dir = Path(settings.backup_dir)
    if is_unsafe_backup_dir(backup_dir):
        raise BackupError("مسیر بکاپ نباید داخل سورس پروژه باشد.")
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = backup_dir / backup_filename(now or datetime.now(timezone.utc))
    try:
        os.chmod(backup_dir, 0o700)
    except OSError:
        log.info("backup dir chmod skipped path=%s", backup_dir)

    log.info("backup start file=%s host=%s db=%s", path.name, target.host, target.dbname)
    with path.open("wb") as out:
        proc = await asyncio.create_subprocess_exec(
            "pg_dump",
            "-h", target.host,
            "-p", str(target.port),
            "-U", target.user,
            "-d", target.dbname,
            "-Fc",
            stdout=out,
            stderr=asyncio.subprocess.PIPE,
            env=_pg_env(target),
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=DUMP_TIMEOUT_SEC)
        except TimeoutError:
            proc.kill()
            path.unlink(missing_ok=True)
            raise BackupError("بکاپ بیش از حد طول کشید و متوقف شد.")
    if proc.returncode != 0 or path.stat().st_size == 0:
        tail = _stderr_tail(stderr)
        log.error("backup failed file=%s rc=%s stderr=%s", path.name, proc.returncode, tail)
        path.unlink(missing_ok=True)
        raise BackupError("گرفتن بکاپ ناموفق بود؛ جزئیات در لاگ.")

    try:
        os.chmod(path, 0o600)
    except OSError:
        log.info("backup file chmod skipped path=%s", path)
    local_names = [p.name for p in backup_dir.iterdir() if p.is_file()]
    for old in select_to_delete(local_names, settings.backup_keep_local):
        (backup_dir / old).unlink(missing_ok=True)
    info = BackupInfo(path.name, path.stat().st_size, datetime.now(timezone.utc))
    log.info("backup done file=%s size=%d", info.name, info.size_bytes)
    return info


async def run_restore(settings: Settings, filename: str) -> None:
    if BACKUP_NAME_RE.fullmatch(filename) is None:
        raise BackupError("نام فایل بکاپ معتبر نیست.")
    path = Path(settings.backup_dir) / filename
    if not path.is_file():
        raise BackupError("این فایل بکاپ الان موجود نیست.")
    target = parse_dump_target(settings.database_url)
    log.info("restore start file=%s host=%s db=%s", filename, target.host, target.dbname)
    stderr = await _run_pg(
        [
            "pg_restore",
            "--no-owner",
            "--no-acl",
            "--clean",
            "--if-exists",
            "-h", target.host,
            "-p", str(target.port),
            "-U", target.user,
            "-d", target.dbname,
            str(path),
        ],
        target,
        timeout=RESTORE_TIMEOUT_SEC,
    )
    if stderr:
        log.info("restore notices file=%s stderr=%s", filename, _stderr_tail(stderr))
    log.info("restore done file=%s", filename)
