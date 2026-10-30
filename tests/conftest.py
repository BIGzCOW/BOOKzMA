from unittest.mock import patch

from BOOKzMA.config import DatabaseSettings, Settings


def pytest_configure(config):
    """Run tests without loading the developer's private .env file.

    DB tests still opt in through the explicitly exported TEST_DATABASE_URL.
    Run before collection: some modules instantiate Settings at import time.
    """
    for patcher in (
        patch("dotenv.load_dotenv", return_value=False),
        patch.dict(DatabaseSettings.model_config, {"env_file": None}),
        patch.dict(Settings.model_config, {"env_file": None}),
    ):
        patcher.start()
        config.add_cleanup(patcher.stop)
