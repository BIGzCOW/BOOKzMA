import asyncio
import logging
import sys

from BOOKzMA.config import Settings
from BOOKzMA.services.backup import BackupError, run_backup

log = logging.getLogger("BOOKzMA.backup")


async def main_async(settings: Settings) -> int:
    try:
        info = await run_backup(settings)
    except BackupError as exc:
        print(f"خطا در بکاپ: {exc}", file=sys.stderr)
        return 1
    print(
        f"بکاپ انجام شد: {info.name} ({info.size_bytes:,} بایت) در {info.path}"
    )
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings()
    raise SystemExit(asyncio.run(main_async(settings)))


if __name__ == "__main__":
    main()
