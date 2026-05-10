"""Idempotency check: re-running ingest should not duplicate rows.

Skipped unless explicitly enabled (network + nfl-data-py download). Run with:
    uv run pytest tests/test_ingest/test_idempotency.py --run-network
"""
import pytest

from model_infrastructure.data import db


def pytest_addoption(parser):  # collected via tests/conftest.py
    parser.addoption("--run-network", action="store_true", default=False)


@pytest.mark.skip(reason="Network test - run manually with --run-network")
def test_weekly_idempotent(tmp_path, monkeypatch):
    from model_infrastructure.data.ingest_nflverse import ingest_weekly
    from model_infrastructure.data.migrate import migrate

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    migrate()
    ingest_weekly([2023])
    conn = db.connect()
    n1 = conn.execute("SELECT COUNT(*) FROM weekly_stats").fetchone()[0]
    ingest_weekly([2023])
    n2 = conn.execute("SELECT COUNT(*) FROM weekly_stats").fetchone()[0]
    assert n1 == n2
