import nfl_data_py as nfl
import polars as pl

from model_infrastructure.config import ScoringRules
from model_infrastructure.data.db import connect, transaction

REQUIRED_WEEKLY_COLUMNS = {
    "player_id", "season", "week", "opponent_team",
    "passing_yards", "passing_tds", "interceptions",
    "rushing_yards", "rushing_tds", "carries",
    "receptions", "receiving_yards", "receiving_tds", "targets",
}

OPTIONAL_WEEKLY_COLUMNS = {"fumbles_lost"}


def ingest_weekly(years: list[int]) -> None:
    df = pl.from_pandas(nfl.import_weekly_data(years))
    missing = REQUIRED_WEEKLY_COLUMNS - set(df.columns)
    if missing:
        raise RuntimeError(f"Schema drift detected in weekly data: missing columns {missing}")

    # Add optional columns as zeros if the data source omits them
    for col in OPTIONAL_WEEKLY_COLUMNS:
        if col not in df.columns:
            df = df.with_columns(pl.lit(0).cast(pl.Int64).alias(col))

    needed = df.select([
        "player_id", "season", "week", "opponent_team",
        "passing_yards", "passing_tds", "interceptions",
        "rushing_yards", "rushing_tds", "carries",
        "receptions", "receiving_yards", "receiving_tds", "targets",
        "fumbles_lost",
    ])

    s = ScoringRules()
    points = (
        s.pass_yd     * pl.col("passing_yards").fill_null(0)
        + s.pass_td   * pl.col("passing_tds").fill_null(0)
        + s.pass_int  * pl.col("interceptions").fill_null(0)
        + s.rush_yd   * pl.col("rushing_yards").fill_null(0)
        + s.rush_td   * pl.col("rushing_tds").fill_null(0)
        + s.rec       * pl.col("receptions").fill_null(0)
        + s.rec_yd    * pl.col("receiving_yards").fill_null(0)
        + s.rec_td    * pl.col("receiving_tds").fill_null(0)
        + s.fumble_lost * pl.col("fumbles_lost").fill_null(0)
    ).alias("fantasy_points_ppr")
    needed = needed.with_columns(points)

    rows = needed.to_dicts()
    conn = connect()
    with transaction(conn):
        conn.executemany(
            """INSERT OR REPLACE INTO weekly_stats
               (player_id, season, week, opponent, pass_yards, pass_tds, interceptions,
                rush_yards, rush_tds, carries, receptions, rec_yards, rec_tds, targets,
                fumbles_lost, fantasy_points_ppr)
               VALUES (:player_id, :season, :week, :opponent_team, :passing_yards, :passing_tds,
                       :interceptions, :rushing_yards, :rushing_tds, :carries, :receptions,
                       :receiving_yards, :receiving_tds, :targets, :fumbles_lost,
                       :fantasy_points_ppr)""",
            rows,
        )


def ingest_seasonal_rosters(years: list[int]) -> None:
    df = pl.from_pandas(nfl.import_seasonal_rosters(years))
    pid_col = "player_id" if "player_id" in df.columns else "gsis_id"
    cols = {pid_col: "player_id", "season": "season", "team": "team"}
    if "age" in df.columns:
        cols["age"] = "age"
    if "depth_chart_position" in df.columns:
        cols["depth_chart_position"] = "depth_chart"
    if "games" in df.columns:
        cols["games"] = "games_played"
    needed = df.select(list(cols.keys())).rename(cols)

    rows = needed.to_dicts()
    conn = connect()
    with transaction(conn):
        for r in rows:
            conn.execute(
                """INSERT OR REPLACE INTO player_seasons
                   (player_id, season, team, age, depth_chart, games_played)
                   VALUES (:player_id, :season, :team, :age, :depth_chart, :games_played)""",
                {
                    "player_id": r["player_id"],
                    "season": r["season"],
                    "team": r.get("team"),
                    "age": r.get("age"),
                    "depth_chart": _to_int(r.get("depth_chart")),
                    "games_played": _to_int(r.get("games_played")),
                },
            )


def ingest_snap_counts(years: list[int]) -> None:
    df = pl.from_pandas(nfl.import_snap_counts(years))
    pid_col = "player_id" if "player_id" in df.columns else "pfr_player_id"
    needed_cols = [pid_col, "season", "week",
                   "offense_snaps", "offense_pct",
                   "defense_snaps", "defense_pct",
                   "st_snaps", "st_pct"]
    have = [c for c in needed_cols if c in df.columns]
    needed = df.select(have).rename({pid_col: "player_id"})

    rows = needed.to_dicts()
    conn = connect()
    with transaction(conn):
        conn.executemany(
            """INSERT OR REPLACE INTO snap_counts
               (player_id, season, week, offense_snaps, offense_pct,
                defense_snaps, defense_pct, st_snaps, st_pct)
               VALUES (:player_id, :season, :week, :offense_snaps, :offense_pct,
                       :defense_snaps, :defense_pct, :st_snaps, :st_pct)""",
            [
                {
                    "player_id": r["player_id"],
                    "season": r["season"],
                    "week": r["week"],
                    "offense_snaps": r.get("offense_snaps"),
                    "offense_pct": r.get("offense_pct"),
                    "defense_snaps": r.get("defense_snaps"),
                    "defense_pct": r.get("defense_pct"),
                    "st_snaps": r.get("st_snaps"),
                    "st_pct": r.get("st_pct"),
                }
                for r in rows
            ],
        )


def ingest_schedules(years: list[int]) -> None:
    df = pl.from_pandas(nfl.import_schedules(years))
    needed = df.select(["season", "week", "home_team", "away_team"])
    rows = needed.to_dicts()
    conn = connect()
    with transaction(conn):
        conn.executemany(
            """INSERT OR REPLACE INTO schedules
               (season, week, home_team, away_team)
               VALUES (:season, :week, :home_team, :away_team)""",
            rows,
        )


def _to_int(v: object) -> int | None:
    if v is None:
        return None
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
