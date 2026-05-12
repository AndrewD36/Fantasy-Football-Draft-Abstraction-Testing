import json
from pathlib import Path

from model_infrastructure.data import db
from model_infrastructure.data.migrate import migrate
from model_infrastructure.tracking import experiments


def _setup_db(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    migrate()


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
    assert json.loads(rows[e1]["config_json"]) == cfg


# ---------------------------------------------------------------------------
# draft_hashes storage
# ---------------------------------------------------------------------------

def test_record_experiment_stores_draft_hashes(tmp_path: Path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    draft_records = [
        {"draft_index": 0, "slot_assignment": "[0,1]", "picks_hash": "abc1234567890123"},
        {"draft_index": 1, "slot_assignment": "[1,0]", "picks_hash": "def4567890123456"},
    ]
    eid = experiments.record_experiment(
        {"agents": "r1,r2", "n_drafts": 2, "seed": 0},
        {"mean": 0.5, "ci_low": 0.45, "ci_high": 0.55},
        draft_records=draft_records,
    )
    conn = db.connect()
    rows = conn.execute(
        "SELECT draft_index, slot_assignment, picks_hash FROM draft_hashes "
        "WHERE experiment_id = ? ORDER BY draft_index",
        (eid,),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["draft_index"] == 0
    assert rows[0]["picks_hash"] == "abc1234567890123"
    assert rows[0]["slot_assignment"] == "[0,1]"
    assert rows[1]["draft_index"] == 1
    assert rows[1]["picks_hash"] == "def4567890123456"


def test_record_experiment_without_draft_hashes(tmp_path: Path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    eid = experiments.record_experiment(
        {"agents": "random", "n_drafts": 10, "seed": 0},
        {"mean": 0.5, "ci_low": 0.45, "ci_high": 0.55},
    )
    conn = db.connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM draft_hashes WHERE experiment_id = ?", (eid,)
    ).fetchone()[0]
    assert n == 0


def test_draft_hashes_are_transactional_with_experiment(tmp_path: Path, monkeypatch):
    """Both the experiment row and its hashes commit together or not at all."""
    _setup_db(tmp_path, monkeypatch)
    draft_records = [{"draft_index": i, "slot_assignment": "[]", "picks_hash": f"{'a'*16}"}
                     for i in range(5)]
    eid = experiments.record_experiment(
        {"agents": "r1", "n_drafts": 5, "seed": 1},
        {"mean": 0.6, "ci_low": 0.5, "ci_high": 0.7},
        draft_records=draft_records,
    )
    conn = db.connect()
    exp_exists = conn.execute(
        "SELECT 1 FROM experiments WHERE experiment_id = ?", (eid,)
    ).fetchone()
    hash_count = conn.execute(
        "SELECT COUNT(*) FROM draft_hashes WHERE experiment_id = ?", (eid,)
    ).fetchone()[0]
    assert exp_exists is not None
    assert hash_count == 5
