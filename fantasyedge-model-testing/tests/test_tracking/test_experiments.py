import json
from pathlib import Path

from model_infrastructure.data import db
from model_infrastructure.tracking import experiments


def _setup_db(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    conn = db.connect(db_path)
    conn.execute(
        """CREATE TABLE experiments (
            experiment_id TEXT PRIMARY KEY, config_hash TEXT, config_json TEXT,
            git_sha TEXT, started_at TIMESTAMP, completed_at TIMESTAMP,
            headline_metric REAL, metric_ci_low REAL, metric_ci_high REAL, notes TEXT, results_json TEXT)"""
    )
    conn.commit()
    conn.close()


def test_record_and_list(tmp_path: Path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    cfg = {"agents": "random,adp", "n_drafts": 100, "seed": 1}
    eid = experiments.record_experiment(
        cfg, {"mean": 0.5, "ci_low": 0.45, "ci_high": 0.55}, notes="smoke"
    )
    rows = experiments.list_experiments()
    assert len(rows) == 1
    assert rows[0]["experiment_id"] == eid
    assert rows[0]["notes"] == "smoke"
    assert abs(rows[0]["headline_metric"] - 0.5) < 1e-9


def test_config_hash_is_stable(tmp_path: Path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    cfg = {"a": 1, "b": [1, 2, 3]}
    headline = {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    e1 = experiments.record_experiment(cfg, headline)
    e2 = experiments.record_experiment(cfg, headline)
    rows = {r["experiment_id"]: r for r in experiments.list_experiments()}
    assert rows[e1]["config_hash"] == rows[e2]["config_hash"]
    # round-trip the JSON to make sure key order didn't matter
    assert json.loads(rows[e1]["config_json"]) == cfg
