from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import Settings


def configure_logging(settings: Settings) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.log_dir / 'villas-v2.log'

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s')

    file_handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=5)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(root.level)
    file_handler.addFilter(RequestIdFilter())

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(root.level)
    console.addFilter(RequestIdFilter())

    root.addHandler(file_handler)
    root.addHandler(console)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, 'request_id'):
            record.request_id = '-'
        return True
