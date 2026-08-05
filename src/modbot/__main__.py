"""Console entry point: ``python -m modbot`` (or the ``modbot`` script)."""

from .bot import ModBot
from .config import load_settings
from .logging_config import configure_logging


def main() -> None:
    configure_logging()
    settings = load_settings()
    bot = ModBot(settings)
    # log_handler=None: we configure logging ourselves in configure_logging().
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
