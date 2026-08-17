import logging
import os
from config.settings import settings


def setup_logging():
    """Configure application logging."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    os.makedirs(os.path.dirname(settings.LOG_FILE) if os.path.dirname(settings.LOG_FILE) else ".", exist_ok=True)

    handlers = [logging.StreamHandler()]
    try:
        handlers.append(
            logging.handlers.RotatingFileHandler(
                settings.LOG_FILE,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
        )
    except Exception:
        pass

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


import logging.handlers