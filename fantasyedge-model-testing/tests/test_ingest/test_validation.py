import pytest

from model_infrastructure.data.db import DB_PATH, connect

KNOWN_GOOD = [
    # (player_name, season, week, expected_ppr_points)
    ("Christian McCaffrey", 2023, 1, 28.4),
    ("Tyreek Hill", 2023, 17, 20.7),
    # Add 8-10 hand-checked entries here as ingestion stabilizes.
]


@pytest.mark.skipif(not DB_PATH.exists(), reason="No ingested DB at data/fantasyedge.db")
@pytest.mark.parametrize("name,season,week,expected", KNOWN_GOOD)
def test_ppr_known_good(name: str, season: int, week: int, expected: float):
    conn = connect()
    row = conn.execute(
        """SELECT w.fantasy_points_ppr FROM weekly_stats w
           JOIN players p ON p.player_id = w.player_id
           WHERE p.full_name = ? AND w.season = ? AND w.week = ?""",
        (name, season, week),
    ).fetchone()
    assert row is not None, f"No data for {name} {season} W{week}"
    assert abs(row["fantasy_points_ppr"] - expected) < 0.5
