"""Tests for validate.py — check_id_reconciliation and check_data_sanity K/DST additions."""
from pathlib import Path

import pytest

from model_infrastructure.data import db
from model_infrastructure.data.migrate import migrate
from model_infrastructure.eval.validate import check_data_sanity, check_id_reconciliation


def _setup_db(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    migrate()


def _insert_player(conn, player_id, full_name, position, nfl_team=None):
    conn.execute(
        "INSERT OR REPLACE INTO players (player_id, full_name, position, nfl_team) "
        "VALUES (?, ?, ?, ?)",
        (player_id, full_name, position, nfl_team),
    )


def _insert_weekly(conn, player_id, season, week, pts):
    conn.execute(
        "INSERT OR REPLACE INTO weekly_stats (player_id, season, week, fantasy_points_ppr) "
        "VALUES (?, ?, ?, ?)",
        (player_id, season, week, pts),
    )


# ---------------------------------------------------------------------------
# check_id_reconciliation
# ---------------------------------------------------------------------------

def test_reconciliation_passes_on_empty_db(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    failures = check_id_reconciliation(2024)
    assert failures == []


def test_reconciliation_passes_when_all_ids_matched(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    conn = db.connect()
    _insert_player(conn, "P001", "CMC", "RB")
    _insert_weekly(conn, "P001", 2024, 1, 25.0)
    conn.commit()
    failures = check_id_reconciliation(2024)
    assert failures == []


def test_reconciliation_detects_orphaned_weekly_stats(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    conn = db.connect()
    # weekly_stats row with a gsis_id that has no players entry
    conn.execute(
        "INSERT INTO weekly_stats (player_id, season, week, fantasy_points_ppr) "
        "VALUES ('ORPHAN-GSIS-00-1234567', 2024, 1, 10.0)"
    )
    conn.commit()
    failures = check_id_reconciliation(2024)
    assert len(failures) > 0
    joined = "\n".join(failures)
    assert "orphaned" in joined.lower() or "ORPHAN-GSIS" in joined


def test_reconciliation_reports_orphan_count(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    conn = db.connect()
    for i in range(3):
        conn.execute(
            "INSERT INTO weekly_stats (player_id, season, week, fantasy_points_ppr) "
            "VALUES (?, 2024, ?, 5.0)",
            (f"ORPHAN-{i:04d}", i + 1),
        )
    conn.commit()
    failures = check_id_reconciliation(2024)
    assert any("3" in f for f in failures)


def test_reconciliation_detects_dst_missing_nfl_team(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    conn = db.connect()
    # DST player with no nfl_team set
    _insert_player(conn, "DST001", "SF 49ers", "DST", nfl_team=None)
    conn.commit()
    failures = check_id_reconciliation(2024)
    assert any("nfl_team" in f for f in failures)


def test_reconciliation_passes_dst_with_nfl_team(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    conn = db.connect()
    _insert_player(conn, "DST001", "SF 49ers", "DST", nfl_team="SF")
    conn.commit()
    failures = check_id_reconciliation(2024)
    # The nfl_team check specifically should not fire
    assert not any("nfl_team" in f for f in failures)


def test_reconciliation_coverage_warning_when_no_season_data(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    conn = db.connect()
    # Add 50 players but none have 2024 stats
    for i in range(50):
        _insert_player(conn, f"P{i:03d}", f"Player {i}", "RB")
    conn.commit()
    failures = check_id_reconciliation(2024)
    # Should warn about 0% coverage
    assert any("%" in f or "0/" in f for f in failures)


# ---------------------------------------------------------------------------
# check_data_sanity — K/DST additions
# ---------------------------------------------------------------------------

def test_data_sanity_no_data_returns_failure(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    failures = check_data_sanity(2024)
    assert any("No weekly_stats" in f for f in failures)


def test_data_sanity_warns_zero_k_points(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    conn = db.connect()
    # Populate enough QB/WR data to pass those thresholds but leave K at zero
    for i in range(20):
        _insert_player(conn, f"QB{i}", f"QB {i}", "QB")
        for w in range(1, 18):
            _insert_weekly(conn, f"QB{i}", 2024, w, 20.0)
    for i in range(40):
        _insert_player(conn, f"WR{i}", f"WR {i}", "WR")
        for w in range(1, 18):
            _insert_weekly(conn, f"WR{i}", 2024, w, 10.0)
    # K player with zero points
    _insert_player(conn, "K001", "Kicker 1", "K")
    _insert_weekly(conn, "K001", 2024, 1, 0.0)
    conn.commit()
    failures = check_data_sanity(2024)
    assert any("K" in f and ("100" in f or "expected" in f.lower()) for f in failures)


def test_data_sanity_warns_zero_dst_points(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    conn = db.connect()
    for i in range(20):
        _insert_player(conn, f"QB{i}", f"QB {i}", "QB")
        for w in range(1, 18):
            _insert_weekly(conn, f"QB{i}", 2024, w, 20.0)
    for i in range(40):
        _insert_player(conn, f"WR{i}", f"WR {i}", "WR")
        for w in range(1, 18):
            _insert_weekly(conn, f"WR{i}", 2024, w, 10.0)
    # DST player with zero points
    _insert_player(conn, "DST001", "SF DST", "DST", nfl_team="SF")
    _insert_weekly(conn, "DST001", 2024, 1, 0.0)
    conn.commit()
    failures = check_data_sanity(2024)
    assert any("DST" in f for f in failures)


def test_data_sanity_passes_with_nonzero_k_dst(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    conn = db.connect()
    # Enough data to pass all thresholds
    for i in range(20):
        _insert_player(conn, f"QB{i}", f"QB {i}", "QB")
        for w in range(1, 18):
            _insert_weekly(conn, f"QB{i}", 2024, w, 20.0)  # 20*17*20 = 6800 QB total
    for i in range(40):
        _insert_player(conn, f"WR{i}", f"WR {i}", "WR")
        for w in range(1, 18):
            _insert_weekly(conn, f"WR{i}", 2024, w, 10.0)  # 10*17*40 = 6800 WR total
    # K with real points
    for i in range(10):
        _insert_player(conn, f"K{i:03d}", f"Kicker {i}", "K")
        for w in range(1, 18):
            _insert_weekly(conn, f"K{i:03d}", 2024, w, 8.0)  # 8*17*10 = 1360 K total
    # DST with real points
    for i in range(5):
        _insert_player(conn, f"DST{i:03d}", f"DST {i}", "DST", nfl_team=f"T{i}")
        for w in range(1, 18):
            _insert_weekly(conn, f"DST{i:03d}", 2024, w, 10.0)
    # Best player has 8*17 = 136 pts — below 300 threshold, so add one star
    _insert_player(conn, "STAR001", "Star Player", "RB")
    for w in range(1, 18):
        _insert_weekly(conn, "STAR001", 2024, w, 25.0)  # 25*17 = 425 pts
    conn.commit()
    failures = check_data_sanity(2024)
    # K and DST warnings should not appear
    assert not any("K" in f and "expected" in f.lower() for f in failures)
    assert not any("DST" in f for f in failures)
