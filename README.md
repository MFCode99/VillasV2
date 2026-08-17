# Villas V2

Foundation for the Villas V2 rewrite.

Stack:
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- Jinja2
- HTMX
- pytest
- MySQL 8
- Uvicorn
- Argon2id

Layout:
- app/ application package
- migrations/ Alembic environment and schema versions
- tests/ unit, integration, regression tests
- scripts/ setup, deploy, backup, restore, migration tooling
- systemd/ service unit template
- nginx/ reverse proxy example
- media/ product media
- logs/ application logs

Safety rules:
- V1 is read-only and untouched
- V2 uses its own database: villas_v2
- V2 test database: villas_v2_test
- Secrets live in .env
- .env is ignored by Git

Common commands:
- bash scripts/setup.sh
- bash scripts/deploy.sh
- bash scripts/backup.sh
- bash scripts/restore.sh --help
- pytest
- alembic upgrade head

Health:
- GET /health
- GET /ready