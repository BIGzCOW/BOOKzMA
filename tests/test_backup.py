import asyncio
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
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_backup_filename_and_parse_roundtrip():
    moment = datetime(2026, 10, 25, 3, 30, 0, tzinfo=timezone.utc)
    name = backup_filename(moment)
    assert name == "bookzma-2026-10-25-033000.dump"
    assert parse_backup_name(name) == moment


def test_parse_backup_name_rejects_non_backup_names():
    assert parse_backup_name("../etc/passwd") is None
    assert parse_backup_name("bookzma-2026-10-25.dump") is None
    assert parse_backup_name("bookzma-2026-13-99-033000.dump") is None
    assert parse_backup_name("other-2026-10-25-033000.dump") is None
    assert parse_backup_name("bookzma-2026-10-25-033000.dump.bak") is None


def test_parse_backup_name_rejects_traversal_and_slashes():
    assert parse_backup_name("bookzma-2026-10-25-033000/../../x.dump") is None
    assert parse_backup_name("..") is None


def test_select_to_delete_keeps_newest_and_ignores_unknown_files():
    names = [
        "bookzma-2026-10-20-033000.dump",
        "bookzma-2026-10-25-033000.dump",
        "bookzma-2026-10-23-033000.dump",
        "unrelated.txt",
    ]
    assert select_to_delete(names, keep=1) == [
        "bookzma-2026-10-23-033000.dump",
        "bookzma-2026-10-20-033000.dump",
    ]
    assert select_to_delete(names, keep=2) == ["bookzma-2026-10-20-033000.dump"]


def test_select_to_delete_edge_cases():
    assert select_to_delete([], keep=1) == []
    assert select_to_delete(["bookzma-2026-10-25-033000.dump"], keep=5) == []
    assert select_to_delete(
        [
            "bookzma-2026-10-24-033000.dump",
            "bookzma-2026-10-25-033000.dump",
        ],
        keep=0,
    ) == [
        "bookzma-2026-10-25-033000.dump",
        "bookzma-2026-10-24-033000.dump",
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

    source_root = BOOKzMA.__file__.rsplit("/", 2)[0]  # پوشهٔ src
    assert is_unsafe_backup_dir(f"{source_root}/backups") is True


def fake_pg_proc(returncode=0, stderr=b""):
    class FakeProc:
        pass

    proc = FakeProc()
    proc.returncode = returncode

    async def communicate():
        return (b"", stderr)

    proc.communicate = communicate
    return proc


def patch_subprocess(monkeypatch, returncode=0, stderr=b"", write_bytes=b""):
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        stdout = kwargs.get("stdout")
        if write_bytes and hasattr(stdout, "write"):
            stdout.write(write_bytes)
            stdout.flush()
        return fake_pg_proc(returncode, stderr)

    monkeypatch.setattr(backup_service.asyncio, "create_subprocess_exec", fake_exec)
    return calls


def test_run_backup_success_rotates_old_dumps(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)
    backup_dir = str(settings.backup_dir)
    old1 = f"{backup_dir}/bookzma-2026-10-23-033000.dump"
    old2 = f"{backup_dir}/bookzma-2026-10-24-033000.dump"
    Path(backup_dir).mkdir(parents=True)
    for path in (old1, old2):
        with open(path, "wb") as fh:
            fh.write(b"old")

    calls = patch_subprocess(monkeypatch, write_bytes=b"PGDMP-fake")
    info = asyncio.run(backup_service.run_backup(settings))

    assert len(calls) == 1
    assert calls[0][0] == "pg_dump"
    assert info.size_bytes == len(b"PGDMP-fake")
    import os

    assert os.listdir(backup_dir) == [info.name]


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
    import os

    assert os.listdir(settings.backup_dir) == []


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
    name = "bookzma-2026-10-25-033000.dump"
    with open(backup_dir / name, "wb") as fh:
        fh.write(b"PGDMP-fake")
    calls = patch_subprocess(monkeypatch)
    asyncio.run(backup_service.run_restore(settings, name))
    assert len(calls) == 1
    args = calls[0]
    assert args[0] == "pg_restore"
    assert "--clean" in args and "--no-owner" in args and "--no-acl" in args


def test_run_restore_rejects_bad_or_missing_files(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)
    calls = patch_subprocess(monkeypatch)
    for bad in ["../outside.dump", "bookzma-2026-10-25-033000.dump", "x"]:
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
