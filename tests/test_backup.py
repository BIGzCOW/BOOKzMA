import asyncio
import gzip
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from pydantic import SecretStr

from BOOKzMA.config import Settings
from BOOKzMA.handlers.admin import _restore_index, on_backup_menu
from BOOKzMA.services import backup as backup_service
from BOOKzMA.services.backup import (
    BackupError,
    backup_filename,
    is_unsafe_backup_dir,
    parse_backup_name,
    parse_dump_target,
    select_to_delete,
)


def make_settings(tmp_path, **overrides):
    defaults = {
        "bot_token": SecretStr("test"),
        "admin_telegram_ids": "123",
        "database_url": "postgresql+asyncpg://bookzma:pw@db:5432/bookzma",
        "backup_dir": str(tmp_path / "backups"),
        "backup_keep_local": 3,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_backup_filename_and_parse_roundtrip():
    moment = datetime(2026, 10, 25, 3, 30, 0, tzinfo=timezone.utc)
    name = backup_filename(moment)
    assert name == "pgdump_2026-10-25_0330.sql.gz"
    assert parse_backup_name(name) == moment


def test_parse_backup_name_rejects_non_backup_names():
    assert parse_backup_name("../etc/passwd") is None
    assert parse_backup_name("bookzma-2026-10-25.dump") is None
    assert parse_backup_name("pgdump_2026-13-99_0330.sql.gz") is None
    assert parse_backup_name("other-2026-10-25_0330.sql.gz") is None
    assert parse_backup_name("pgdump_2026-10-25_0330.sql.gz.bak") is None


def test_parse_backup_name_rejects_traversal_and_slashes():
    assert parse_backup_name("pgdump_2026-10-25_0330.sql.gz/../../x.dump") is None
    assert parse_backup_name("..") is None


def test_select_to_delete_keeps_newest_and_ignores_unknown_files():
    names = [
        "pgdump_2026-10-20_0330.sql.gz",
        "pgdump_2026-10-25_0330.sql.gz",
        "pgdump_2026-10-23_0330.sql.gz",
        "unrelated.txt",
    ]
    assert select_to_delete(names, keep=3) == []
    assert select_to_delete(names, keep=2) == ["pgdump_2026-10-20_0330.sql.gz"]


def test_select_to_delete_edge_cases():
    assert select_to_delete([], keep=3) == []
    assert select_to_delete(["pgdump_2026-10-25_0330.sql.gz"], keep=5) == []
    assert select_to_delete(
        [
            "pgdump_2026-10-24_0330.sql.gz",
            "pgdump_2026-10-25_0330.sql.gz",
        ],
        keep=0,
    ) == [
        "pgdump_2026-10-25_0330.sql.gz",
        "pgdump_2026-10-24_0330.sql.gz",
    ]


def test_parse_dump_target_extracts_connection_fields():
    target = parse_dump_target("postgresql+asyncpg://bookzma:pw@db:5433/bookzma")
    fields = (target.host, target.port, target.user, target.dbname)
    assert fields == ("db", 5433, "bookzma", "bookzma")
    assert target.password == "pw"


def test_parse_dump_target_defaults_and_encoding():
    target = parse_dump_target("postgresql://u%40x:p%40ss@host/bookzma")
    assert target.port == 5432
    assert target.user == "u@x"
    assert target.password == "p@ss"


def test_parse_dump_target_rejects_unsupported_urls():
    for bad in [
        "mysql://bookzma:pw@db/bookzma",
        "postgresql+asyncpg://bookzma@/bookzma",
        "postgresql+asyncpg://bookzma:pw@db/",
        "not a url",
    ]:
        try:
            parse_dump_target(bad)
        except BackupError:
            continue
        raise AssertionError(f"expected BackupError for {bad}")


def test_is_unsafe_backup_dir(tmp_path):
    assert is_unsafe_backup_dir(tmp_path / "backups") is False
    import BOOKzMA
    from pathlib import Path

    project_root = Path(BOOKzMA.__file__).resolve().parents[2]
    assert is_unsafe_backup_dir(project_root / "backups") is False
    assert is_unsafe_backup_dir(project_root / "src" / "backups") is True


def test_relative_backup_dir_resolves_from_project_root(monkeypatch, tmp_path):
    import BOOKzMA

    project_root = Path(BOOKzMA.__file__).resolve().parents[2]
    monkeypatch.chdir(tmp_path)
    assert backup_service._resolved_backup_dir("backups") == project_root / "backups"


def patch_subprocess(monkeypatch, returncode=0, stderr=b"", write_bytes=b""):
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)

        class FakeProc:
            pass

        proc = FakeProc()
        proc.returncode = returncode

        async def communicate():
            return (write_bytes, stderr)

        proc.communicate = communicate
        return proc

    monkeypatch.setattr(backup_service.asyncio, "create_subprocess_exec", fake_exec)
    return calls


def test_run_backup_success_rotates_old_dumps(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)
    backup_dir = str(settings.backup_dir)
    old1 = f"{backup_dir}/pgdump_2026-10-23_0330.sql.gz"
    old2 = f"{backup_dir}/pgdump_2026-10-24_0330.sql.gz"
    Path(backup_dir).mkdir(parents=True)
    for path in (old1, old2):
        with open(path, "wb") as fh:
            fh.write(b"old")

    import os as _os

    raw = b"PGDMP-fake-data-" + _os.urandom(1500)
    calls = patch_subprocess(monkeypatch, write_bytes=raw)
    info = asyncio.run(backup_service.run_backup(settings))

    assert len(calls) == 1
    assert calls[0][0] == "pg_dump"
    assert info.name.startswith("pgdump_")
    assert info.name.endswith(".sql.gz")
    files = sorted(
        f for f in _os.listdir(backup_dir)
        if f != "pgbackup.lock"
    )
    assert len(files) == 3
    assert all(f.startswith("pgdump_") and f.endswith(".sql.gz") for f in files)
    with gzip.open(Path(backup_dir) / files[-1], "rb") as fh:
        assert fh.read() == raw


def test_run_backup_missing_pg_dump_is_reported_and_partial_file_removed(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)

    async def missing_executable(*args, **kwargs):
        raise FileNotFoundError("pg_dump")

    monkeypatch.setattr(backup_service.asyncio, "create_subprocess_exec", missing_executable)
    try:
        asyncio.run(backup_service.run_backup(settings))
    except BackupError as exc:
        assert "pg_dump" in str(exc)
    else:
        raise AssertionError("expected BackupError when pg_dump is unavailable")

    assert list(Path(settings.backup_dir).iterdir()) == []


def test_run_backup_failure_removes_partial_file(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)
    calls = patch_subprocess(
        monkeypatch, returncode=1, stderr=b"pg_dump: error", write_bytes=b"partial"
    )
    try:
        asyncio.run(backup_service.run_backup(settings))
    except BackupError:
        pass
    else:
        raise AssertionError("expected BackupError")
    assert len(calls) == 1
    assert list(Path(settings.backup_dir).iterdir()) == []


def test_run_backup_empty_output_is_failure(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)
    patch_subprocess(monkeypatch, returncode=0, write_bytes=b"")
    try:
        asyncio.run(backup_service.run_backup(settings))
    except BackupError:
        pass
    else:
        raise AssertionError("expected BackupError for empty dump")


def test_run_backup_refuses_source_tree_destination(monkeypatch, tmp_path):
    import BOOKzMA

    source_root = BOOKzMA.__file__.rsplit("/", 2)[0]
    settings = make_settings(tmp_path, backup_dir=f"{source_root}/backups")
    calls = patch_subprocess(monkeypatch)
    try:
        asyncio.run(backup_service.run_backup(settings))
    except BackupError:
        pass
    else:
        raise AssertionError("expected BackupError for in-repo backup dir")
    assert calls == []


def test_run_restore_success(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)
    backup_dir = Path(str(settings.backup_dir))
    backup_dir.mkdir(parents=True)
    name = "pgdump_2026-10-25_0330.sql.gz"
    raw = gzip.compress(b"PGDMP-fake")
    with open(backup_dir / name, "wb") as fh:
        fh.write(raw)
    calls = patch_subprocess(monkeypatch)
    asyncio.run(backup_service.run_restore(settings, name))
    assert len(calls) == 1
    args = calls[0]
    assert args[0] == "pg_restore"
    assert "--clean" in args and "--no-owner" in args and "--no-acl" in args


def test_run_restore_missing_pg_restore_is_reported(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)
    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True)
    name = "pgdump_2026-10-25_0330.sql.gz"
    (backup_dir / name).write_bytes(gzip.compress(b"PGDMP-fake"))

    async def missing_executable(*args, **kwargs):
        raise FileNotFoundError("pg_restore")

    monkeypatch.setattr(backup_service.asyncio, "create_subprocess_exec", missing_executable)
    try:
        asyncio.run(backup_service.run_restore(settings, name))
    except BackupError as exc:
        assert "pg_restore" in str(exc)
    else:
        raise AssertionError("expected BackupError when pg_restore is unavailable")


def test_run_restore_logs_postgres_error(monkeypatch, tmp_path, caplog):
    settings = make_settings(tmp_path)
    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True)
    name = "pgdump_2026-10-25_0330.sql.gz"
    (backup_dir / name).write_bytes(gzip.compress(b"PGDMP-fake"))
    patch_subprocess(monkeypatch, returncode=1, stderr=b"permission denied for database")

    try:
        asyncio.run(backup_service.run_restore(settings, name))
    except BackupError:
        pass
    else:
        raise AssertionError("expected BackupError for failed pg_restore")

    assert "permission denied for database" in caplog.text


def test_run_restore_ignores_only_unsupported_transaction_timeout(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)
    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True)
    name = "pgdump_2026-10-25_0330.sql.gz"
    (backup_dir / name).write_bytes(gzip.compress(b"PGDMP-fake"))
    stderr = (
        b"pg_restore: error: could not execute query: ERROR:  unrecognized configuration "
        b'parameter "transaction_timeout"\n'
        b"Command was: SET transaction_timeout = 0;\n"
        b"pg_restore: warning: errors ignored on restore: 1\n"
    )
    patch_subprocess(monkeypatch, returncode=1, stderr=stderr)

    assert asyncio.run(backup_service.run_restore(settings, name)) is None


def test_run_restore_rejects_bad_or_missing_files(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)
    calls = patch_subprocess(monkeypatch)
    for bad in ["../outside.dump", "pgdump_2026-10-25_0330.sql.gz", "x"]:
        try:
            asyncio.run(backup_service.run_restore(settings, bad))
        except BackupError:
            continue
        raise AssertionError(f"expected BackupError for {bad}")
    assert calls == []


def test_restore_index_parsing():
    assert _restore_index("admin:restore_ask:0", "ask") == 0
    assert _restore_index("admin:restore_ready:12", "ready") == 12
    assert _restore_index("admin:restore_ask:9999", "ask") is None
    assert _restore_index("admin:restore_ask:-1", "ask") is None
    assert _restore_index("admin:restore_ready:1:extra", "ready") is None
    assert _restore_index("admin:restore_ask:1", "ready") is None


def test_non_admin_cannot_open_backup_menu(tmp_path):
    async def run_test():
        answers = []

        async def answer(text, show_alert=False):
            answers.append((text, show_alert))

        async def clear():
            answers.append(("clear", False))

        callback = SimpleNamespace(from_user=SimpleNamespace(id=789), answer=answer)
        settings = make_settings(tmp_path)
        await on_backup_menu(callback, SimpleNamespace(clear=clear), settings)
        assert answers == [("دسترسی نداری.", True)]

    asyncio.run(run_test())
