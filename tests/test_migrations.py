"""Tests that the Alembic migrations bootstrap a complete, model-faithful schema."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]

MODEL_TABLES = {"supermercado", "producto", "ticket", "linea_ticket", "job"}


def _migrate_scratch_db(tmp_path, monkeypatch):
    """Run `alembic upgrade head` against a scratch sqlite db and return its URL.

    This is exactly what the Dockerfile CMD does before serving
    (`alembic upgrade head && uvicorn ...`), against a fresh database.
    """
    db_path = tmp_path / "migrations_scratch.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    from app.core import config as config_module

    # env.py lee settings.database_url en tiempo de ejecución del upgrade.
    monkeypatch.setattr(config_module, "settings", Settings(database_url=url))

    alembic_cfg = Config(str(ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(alembic_cfg, "head")
    return url


def test_alembic_upgrade_head_creates_every_model_table(tmp_path, monkeypatch) -> None:
    url = _migrate_scratch_db(tmp_path, monkeypatch)

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
    finally:
        engine.dispose()

    assert MODEL_TABLES <= tables
    assert "alembic_version" in tables


def test_job_migration_matches_the_job_model(tmp_path, monkeypatch) -> None:
    url = _migrate_scratch_db(tmp_path, monkeypatch)

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        columns = {column["name"]: column for column in inspector.get_columns("job")}
        indexes = {index["name"] for index in inspector.get_indexes("job")}
    finally:
        engine.dispose()

    assert set(columns) == {
        "id",
        "batch_id",
        "filename",
        "status",
        "error",
        "ticket_id",
        "created_at",
    }
    assert columns["id"]["type"].length == 36
    assert columns["batch_id"]["type"].length == 36
    assert columns["status"]["type"].length == 20
    assert "ix_job_batch_id" in indexes
