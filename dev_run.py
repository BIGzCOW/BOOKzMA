import uvicorn
from aiogram.client.session.aiohttp import AiohttpSession

from BOOKzMA.api import create_app
from BOOKzMA.config import Settings


def main() -> None:
    settings = Settings()
    proxy = settings.telegram_proxy.get_secret_value() if settings.telegram_proxy else None
    bot_session = AiohttpSession(proxy=proxy or None)
    app = create_app(settings=settings, bot_session=bot_session)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        timeout_graceful_shutdown=5,
    )


if __name__ == "__main__":
    main()
