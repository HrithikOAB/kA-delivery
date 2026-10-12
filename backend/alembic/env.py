"""Alembic environment. Uses the app's Base metadata and configured DB URL."""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from app.config import settings
from app.database import Base
import app.models  # noqa: F401  (register all tables on Base.metadata)

config = context.config
# ConfigParser treats % as interpolation; passwords may contain URL-encoded % sequences.
config.set_main_option(
    "sqlalchemy.url", settings.database_url.replace("%", "%%")
)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # SQLite-friendly ALTERs
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from app.database import engine as app_engine

    connectable = app_engine
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
