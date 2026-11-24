from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal
from app.logging_conf import configure_logging
from app.config import get_settings
from app.system_monitor import run_monitor


if __name__ == '__main__':
    settings = get_settings()
    configure_logging(settings)
    with SessionLocal() as db:
        result = run_monitor(db, settings)
    raise SystemExit(0 if result['ok'] else 1)
