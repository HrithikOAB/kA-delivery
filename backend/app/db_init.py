"""Database bootstrap for fresh deployments.

On startup the API can run Alembic migrations and seed demo data when the
database is empty. This avoids manual ``alembic upgrade head`` / ``python -m
app.seed`` steps on a new server.
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.config import settings
from app.database import SessionLocal, engine

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _ensure_sqlite_parent_dir() -> None:
    url = settings.database_url
    if not url.startswith("sqlite"):
        return
    if ":memory:" in url:
        return
    path_part = url.split("///", 1)[-1] if "///" in url else url.replace("sqlite:///", "")
    if not path_part:
        return
    Path(path_part).resolve().parent.mkdir(parents=True, exist_ok=True)


def run_migrations() -> None:
    _ensure_sqlite_parent_dir()
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    logger.info("Running database migrations (alembic upgrade head)…")
    command.upgrade(cfg, "head")
    logger.info("Database migrations complete.")


def is_database_empty() -> bool:
    inspector = inspect(engine)
    if not inspector.has_table("users"):
        return True
    with SessionLocal() as db:
        count = db.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
        return int(count) == 0


def init_database() -> None:
    """Apply migrations and seed when configured and the DB has no users."""
    if not settings.auto_migrate_on_startup:
        logger.info("auto_migrate_on_startup disabled — skipping DB bootstrap")
        return

    try:
        run_migrations()
    except Exception:
        logger.exception("Database migration failed")
        raise

    if not settings.auto_seed_on_startup:
        return

    if settings.is_production:
        logger.warning("Production environment — skipping demo-data seed.")
        return

    try:
        if is_database_empty():
            logger.info("Empty database detected — running seed…")
            from app.seed import seed

            seed()
            logger.info("Database seed complete.")
        else:
            logger.info("Database already has users — skipping seed.")
    except Exception:
        logger.exception("Database seed failed")
        raise
