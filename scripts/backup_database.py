from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    url = make_url(settings.database_url)
    output_dir = Path('backups') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output_dir.mkdir(parents=True, exist_ok=False)
    command = [
        'mysqldump',
        '--single-transaction',
        '--routines',
        '--triggers',
        '--events',
        f'--host={url.host or "localhost"}',
        f'--port={url.port or 3306}',
        f'--user={url.username or ""}',
        url.database or '',
    ]
    process_env = dict(os.environ)
    process_env['MYSQL_PWD'] = url.password or ''
    with (output_dir / 'database.sql').open('wb') as output:
        subprocess.run(command, stdout=output, stderr=subprocess.PIPE, env=process_env, check=True)
    print(output_dir)


if __name__ == '__main__':
    main()
