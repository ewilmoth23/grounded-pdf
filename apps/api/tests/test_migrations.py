from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from alembic import command
from app.db.base import Base
from app.models import entities  # noqa: F401

API_DIR = Path(__file__).resolve().parents[1]


def test_alembic_upgrade_head_matches_model_metadata(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migrations.db'}"
    config = Config(str(API_DIR / "alembic.ini"))
    config.cmd_opts = Namespace(x=[f"db_url={database_url}"])

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            migration_context = MigrationContext.configure(connection, opts={"compare_type": True})
            diff = compare_metadata(migration_context, Base.metadata)
    finally:
        engine.dispose()

    assert diff == []
