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


def run_migrations() -> None:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    # ConfigParser treats % as interpolation; escape for passwords with encoded chars.
    cfg.set_main_option(
        "sqlalchemy.url", settings.database_url.replace("%", "%%")
    )
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


def _bootstrap_users() -> None:
    if not is_database_empty():
        logger.info("Database already has users — skipping user bootstrap.")
        return

    if settings.auto_seed_admin_on_startup:
        logger.info("Empty database — creating super admin account…")
        from app.seed import seed_admin

        seed_admin()
        logger.info("Super admin bootstrap complete.")

    if not settings.auto_seed_on_startup or settings.is_production:
        if settings.is_production and settings.auto_seed_on_startup:
            logger.warning("Production environment — skipping demo-data seed.")
        return

    logger.info("Empty database — running demo seed…")
    from app.seed import seed

    seed()
    logger.info("Demo seed complete.")


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

    try:
        _bootstrap_users()
    except Exception:
        logger.exception("Database user bootstrap failed")
        raise
