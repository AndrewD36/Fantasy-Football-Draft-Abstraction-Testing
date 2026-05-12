import pytest

from model_infrastructure.data.db import DB_PATH, connect

KNOWN_GOOD = [
    # (player_name, season, week, expected_ppr_points)
    # Verified against actual DB: 22 car/152 rush yds/1 TD + 3 rec/17 yds = 25.9
    ("Christian McCaffrey", 2023, 1, 25.9),
    # Verified against actual DB: 6 rec/76 yds = 13.6
    ("Tyreek Hill", 2023, 17, 13.6),
    # Add more hand-checked entries here as ingestion stabilizes.
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
