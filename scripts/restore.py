#!/usr/bin/env python3
"""بازیابی یک فایل بکاپ BOOKzMA در یک دیتابیس هدف با docker exec.

طراحی‌شده برای «تمرین بازیابی»: اول یک Postgres موقت بالا بیاور، داخلش بازیابی کن،
جدول‌ها و دادهٔ نمونه را چک کن و بعد کانتینر موقت را پاک کن.

مثال تمرین بازیابی:
  docker run --rm -d --name bookzma-restore-test \
      -e POSTGRES_PASSWORD=testonly postgres:16-alpine
  python3 scripts/restore.py --dump /var/backups/bookzma/bookzma-...dump \
      --container bookzma-restore-test --db-user postgres --db-name postgres
  # بررسی جدول‌ها، بعد:
  docker stop bookzma-restore-test

بازیابی روی دیتابیس اصلی سرویس db فقط با پرچم --main-db و تأیید تایپی ممکن است.
فقط کتابخانهٔ استاندارد پایتون؛ نیازی به نصب پروژه نیست.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

NAME_RE = re.compile(r"^bookzma-\d{4}-\d{2}-\d{2}-\d{6}\.dump$")
CONFIRM_WORD = "بازیابی"


def fail(message: str) -> NoReturn:
    print(f"restore failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dump", type=Path, required=True, help="فایل .dump بکاپ")
    parser.add_argument("--container", required=True, help="کانتینر Postgres هدف")
    parser.add_argument("--db-user", default="postgres")
    parser.add_argument("--db-name", default="postgres")
    parser.add_argument(
        "--main-db",
        action="store_true",
        help="اجازهٔ هدف‌گرفتن دیتابیس bookzma (بازگردانی واقعی روی دادهٔ اصلی)",
    )
    parser.add_argument("--yes", action="store_true", help="رد شدن از تأیید تایپی")
    args = parser.parse_args()

    dump = args.dump.expanduser().resolve()
    if not NAME_RE.fullmatch(dump.name):
        fail(f"نام فایل بکاپ معتبر نیست: {dump.name}")
    if not dump.is_file() or dump.stat().st_size == 0:
        fail("فایل بکاپ پیدا نشد یا خالی است")
    if args.db_name == "bookzma" and not args.main_db:
        fail(
            "هدف دیتابیس اصلی bookzma است؛ این فقط برای بازیابی واقعی است. "
            "برای تمرین از دیتابیس موقت استفاده کن، یا عمدی بودنش را با --main-db تأیید کن."
        )

    if not args.yes:
        answer = input(
            f"بازیابی {dump.name} در {args.container}/{args.db_name} دادهٔ فعلی را "
            f"جایگزین می‌کند. برای تأیید «{CONFIRM_WORD}» را بنویس: "
        )
        if answer.strip() != CONFIRM_WORD:
            fail("تأیید نشد؛ لغو شد.")

    cmd = [
        "docker", "exec", "-i", args.container,
        "pg_restore", "--no-owner", "--no-acl", "--clean", "--if-exists",
        "-U", args.db_user, "-d", args.db_name,
    ]
    with dump.open("rb") as fh:
        proc = subprocess.run(cmd, stdin=fh, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace").strip()[-500:]
        fail(f"pg_restore rc={proc.returncode} stderr={stderr}")
    print(f"restore ok file={dump.name} target={args.container}/{args.db_name}")
    print("یادآوری: بعد از بازیابی روی دیتابیس اصلی، docker compose restart bot را اجرا کن.")


if __name__ == "__main__":
    main()
