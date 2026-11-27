import asyncio
import fcntl
import gzip
import importlib.util
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from BOOKzMA.config import Settings

log = logging.getLogger(__name__)

BACKUP_NAME_RE = re.compile(r"^pgdump_(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})\.sql\.gz$")
LOCK_FILE = "pgbackup.lock"
MIN_BACKUP_SIZE = 1024
DUMP_TIMEOUT_SEC = 900


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
    path: Path


def backup_filename(now: datetime) -> str:
    return "pgdump_" + now.astimezone(timezone.utc).strftime("%Y-%m-%d_%H%M") + ".sql.gz"


def parse_backup_name(name: str) -> datetime | None:
    match = BACKUP_NAME_RE.fullmatch(name)
    if match is None:
        return None
    try:
        return datetime(*(int(part) for part in match.groups()), tzinfo=timezone.utc)
    except ValueError:
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
    return valid[max(keep, 0) :]


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
    spec = importlib.util.find_spec("BOOKzMA")
    if spec is None or spec.origin is None:
        return Path.cwd()
    return Path(spec.origin).resolve().parent.parent.parent


def is_unsafe_backup_dir(backup_dir: Path | str) -> bool:
    root = _source_root()
    resolved = Path(backup_dir).resolve()
    if resolved == root / "backups":
        return False
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return False
    return relative == Path("src") or relative.parts[:1] == ("src",)


def _resolved_backup_dir(backup_dir: Path | str) -> Path:
    path = Path(backup_dir)
    if not path.is_absolute():
        path = _source_root() / path
    return path.resolve()


def list_backups(settings: Settings) -> list[BackupInfo]:
    backup_dir = _resolved_backup_dir(settings.backup_dir)
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
                    path=path,
                )
            )
    return sorted(items, key=lambda info: info.name, reverse=True)


def _pg_env(target: DumpTarget) -> dict[str, str]:
    return {**os.environ, "PGPASSWORD": target.password}


def _is_unsupported_transaction_timeout(stderr: bytes) -> bool:
    expected_error = (
        b"pg_restore: error: could not execute query: ERROR:  unrecognized configuration "
        b'parameter "transaction_timeout"'
    )
    return (
        expected_error in stderr
        and b"Command was: SET transaction_timeout = 0;" in stderr
        and b"pg_restore: warning: errors ignored on restore: 1" in stderr
        and stderr.count(b"pg_restore: error:") == 1
        and stderr.count(b"Command was:") == 1
    )


def _verify_gzip(path: Path) -> bool:
    """سنجش سالم بودن فایل gzip و اندازه حداقل."""
    try:
        if path.stat().st_size < MIN_BACKUP_SIZE:
            return False
        with gzip.open(path, "rb") as f:
            f.read()
        return True
    except Exception:
        return False


async def _run_pg_dump_to_file(target: DumpTarget, out_path: Path, *, timeout: int) -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "pg_dump",
            "-h",
            target.host,
            "-p",
            str(target.port),
            "-U",
            target.user,
            "-d",
            target.dbname,
            "-Fc",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_pg_env(target),
        )
    except FileNotFoundError as exc:
        raise BackupError(
            "ابزار pg_dump پیدا نشد؛ برای بکاپ محلی بستهٔ PostgreSQL client را نصب کن."
        ) from exc
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        raise BackupError("بکاپ بیش از حد طول کشید و متوقف شد.")
    if proc.returncode != 0:
        tail = stderr.decode(errors="replace").strip()[-500:]
        log.error("pg_dump failed rc=%s stderr=%s", proc.returncode, tail)
        raise BackupError("ابزار پایگاه داده با خطا متوقف شد.")
    out_path.write_bytes(stdout)


async def run_backup(settings: Settings, *, now: datetime | None = None) -> BackupInfo:
    target = parse_dump_target(settings.database_url)
    backup_dir = _resolved_backup_dir(settings.backup_dir)
    if is_unsafe_backup_dir(backup_dir):
        raise BackupError("مسیر بکاپ نباید داخل سورس پروژه باشد.")
    backup_dir.mkdir(parents=True, exist_ok=True)

    lock_path = backup_dir / LOCK_FILE
    lock_fd = open(lock_path, "w")
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError("یک بکاپ دیگر در حال اجرا است. کمی بعد دوباره امتحان کن.")

        final_name = backup_filename(now or datetime.now(timezone.utc))
        final_path = backup_dir / final_name

        fd, tmp_str = tempfile.mkstemp(dir=backup_dir, suffix=".tmp")
        os.close(fd)
        tmp_path = Path(tmp_str)
        tmp_sql = backup_dir / (final_name + ".sql.tmp")

        try:
            await _run_pg_dump_to_file(target, tmp_sql, timeout=DUMP_TIMEOUT_SEC)

            with open(tmp_sql, "rb") as f_in:
                with gzip.open(tmp_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            tmp_sql.unlink(missing_ok=True)

            if not _verify_gzip(tmp_path):
                raise BackupError("فایل بکاپ تولید‌شده معتبر نیست.")

            os.replace(tmp_path, final_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            tmp_sql.unlink(missing_ok=True)
            raise

        try:
            os.chmod(final_path, 0o600)
        except OSError:
            log.info("backup file chmod skipped path=%s", final_path)

        log.info(
            "backup start file=%s path=%s host=%s db=%s",
            final_name,
            final_path,
            target.host,
            target.dbname,
        )

        local_names = [
            p.name for p in backup_dir.iterdir() if p.is_file() and parse_backup_name(p.name)
        ]
        for old in select_to_delete(local_names, settings.backup_keep_local):
            (backup_dir / old).unlink(missing_ok=True)

        info = BackupInfo(
            final_name, final_path.stat().st_size, datetime.now(timezone.utc), final_path
        )
        log.info("backup done file=%s path=%s size=%d", info.name, final_path, info.size_bytes)
        return info
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        lock_fd.close()
        lock_path.unlink(missing_ok=True)


async def run_restore(settings: Settings, filename: str) -> None:
    if BACKUP_NAME_RE.fullmatch(filename) is None:
        raise BackupError("نام فایل بکاپ معتبر نیست.")
    path = _resolved_backup_dir(settings.backup_dir) / filename
    if not path.is_file():
        raise BackupError("این فایل بکاپ الان موجود نیست.")
    target = parse_dump_target(settings.database_url)
    backup_dir = _resolved_backup_dir(settings.backup_dir)
    log.info("restore start file=%s host=%s db=%s", filename, target.host, target.dbname)

    decompressed = backup_dir / (filename + ".dec")
    try:
        with gzip.open(path, "rb") as f_in:
            decompressed.write_bytes(f_in.read())

        try:
            proc = await asyncio.create_subprocess_exec(
                "pg_restore",
                "--no-owner",
                "--no-acl",
                "--clean",
                "--if-exists",
                "-h",
                target.host,
                "-p",
                str(target.port),
                "-U",
                target.user,
                "-d",
                target.dbname,
                str(decompressed),
                stderr=asyncio.subprocess.PIPE,
                env=_pg_env(target),
            )
        except FileNotFoundError as exc:
            raise BackupError(
                "ابزار pg_restore پیدا نشد؛ برای بازگردانی محلی بستهٔ PostgreSQL client را نصب کن."
            ) from exc
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=DUMP_TIMEOUT_SEC * 2)
        if proc.returncode != 0:
            if _is_unsupported_transaction_timeout(stderr):
                log.warning(
                    "pg_restore skipped unsupported transaction_timeout setting on target server"
                )
            else:
                tail = stderr.decode(errors="replace").strip()[-500:]
                log.error("pg_restore failed rc=%s stderr=%s", proc.returncode, tail)
                raise BackupError("بازگردانی بکاپ با خطا متوقف شد.")
    finally:
        decompressed.unlink(missing_ok=True)

    log.info("restore done file=%s", filename)
