#!/usr/bin/env python3
"""بکاپ روزانهٔ دیتابیس از روی هاست (بیرون از ربات).

pg_dump را داخل سرویس db اجرا می‌کند، خروجی را در مقصد امن می‌نویسد،
قدیمی‌ها را می‌چرخاند و اگر خواسته باشی با rclone به گوگل‌درایو آپلود می‌کند.

مثال cron (هر روز ۳:۳۰):
  30 3 * * * python3 /path/to/BOOKzMA/scripts/backup.py \
      --project /path/to/BOOKzMA --dest /var/backups/bookzma \
      --rclone gdrive:bookzma-backups >> /var/log/bookzma-backup.log 2>&1

فقط کتابخانهٔ استاندارد پایتون؛ نیازی به نصب پروژه نیست.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

NAME_RE = re.compile(r"^bookzma-\d{4}-\d{2}-\d{2}-\d{6}\.dump$")
DB_USER = "bookzma"
DB_NAME = "bookzma"


def fail(message: str) -> NoReturn:
    print(f"backup failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return start


def rotate(directory: Path, keep: int) -> list[str]:
    names = sorted(
        (path.name for path in directory.iterdir() if NAME_RE.fullmatch(path.name)),
        reverse=True,
    )
    deleted = []
    for name in names[max(keep, 0):]:
        (directory / name).unlink(missing_ok=True)
        deleted.append(name)
    return deleted


def rclone_upload(path: Path, remote: str) -> None:
    subprocess.run(
        ["rclone", "copy", str(path), remote], check=True, capture_output=True
    )


def rclone_rotate(remote: str, keep: int) -> list[str]:
    result = subprocess.run(
        ["rclone", "lsf", remote], check=True, capture_output=True, text=True
    )
    names = sorted(
        line.strip()
        for line in result.stdout.splitlines()
        if NAME_RE.fullmatch(line.strip())
    )
    deleted = []
    for name in names[max(keep, 0):]:
        subprocess.run(
            ["rclone", "deletefile", f"{remote.rstrip('/')}/{name}"],
            check=True,
            capture_output=True,
        )
        deleted.append(name)
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", type=Path, help="پوشهٔ پروژهٔ docker compose")
    parser.add_argument("--dest", type=Path, required=True, help="پوشهٔ مقصد (خارج از مخزن)")
    parser.add_argument("--keep", type=int, default=1, help="تعداد بکاپ محلی (پیش‌فرض ۱)")
    parser.add_argument("--rclone", metavar="REMOTE:PATH", help="مثلاً gdrive:bookzma-backups")
    parser.add_argument("--remote-keep", type=int, default=14, help="تعداد بکاپ در ریموت")
    args = parser.parse_args()

    project = (args.project or Path.cwd()).resolve()
    compose_file = project / "docker-compose.yml"
    if not compose_file.is_file():
        fail(f"docker-compose.yml در {project} پیدا نشد")

    dest = args.dest.expanduser().resolve()
    repo_root = find_repo_root(project)
    if dest == repo_root or repo_root in dest.parents:
        fail("مقصد بکاپ نباید داخل مخزن باشد")
    dest.mkdir(parents=True, exist_ok=True)

    name = "bookzma-" + datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S") + ".dump"
    path = dest / name
    cmd = [
        "docker", "compose", f"--project-directory={project}", "exec", "-T",
        "db", "pg_dump", "-U", DB_USER, "-Fc", DB_NAME,
    ]
    with path.open("wb") as out:
        proc = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE)
    if proc.returncode != 0 or path.stat().st_size == 0:
        stderr = proc.stderr.decode(errors="replace").strip()[-500:]
        path.unlink(missing_ok=True)
        fail(f"pg_dump rc={proc.returncode} stderr={stderr}")
    os.chmod(path, 0o600)
    try:
        os.chmod(dest, 0o700)
    except OSError:
        pass
    print(f"backup ok file={name} size={path.stat().st_size}")

    local_deleted = rotate(dest, args.keep)
    if local_deleted:
        print(f"local rotation removed={','.join(local_deleted)}")

    if args.rclone:
        if shutil.which("rclone") is None:
            fail("rclone نصب نیست؛ یا نصبش کن یا --rclone رو بردار")
        try:
            rclone_upload(path, args.rclone)
            remote_deleted = rclone_rotate(args.rclone, args.remote_keep)
        except subprocess.CalledProcessError as error:
            fail(f"rclone step failed: {error}")
        print(f"rclone upload ok remote={args.rclone}")
        if remote_deleted:
            print(f"remote rotation removed={','.join(remote_deleted)}")

    print("backup finished")


if __name__ == "__main__":
    main()
