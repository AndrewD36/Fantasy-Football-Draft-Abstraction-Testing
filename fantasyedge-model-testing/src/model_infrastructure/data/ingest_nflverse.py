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

# Kicker stat columns in nflverse weekly data; null for non-kicker rows.
# nflverse splits by distance band: 0-19, 20-29, 30-39, 40-49, 50-59, 60+.
# We collapse to the three scoring tiers: 0-39, 40-49, 50+.
OPTIONAL_K_COLUMNS = {
    "fg_made_0_19", "fg_made_20_29", "fg_made_30_39",
    "fg_made_40_49",
    "fg_made_50_59", "fg_made_60_",
    "pat_made",
}

# Minimal PBP columns needed to compute team DST stats per week.
DST_PBP_COLUMNS = [
    "season", "week", "game_id",
    "posteam", "defteam",
    "sack",
    "interception",
    "fumble_lost",
    "fumble_recovery_1_team",   # correct nflverse column name
    "safety",
    "td_team",
    "touchdown",
    "return_touchdown",
]


def ingest_weekly(years: list[int]) -> None:
    df = pl.from_pandas(nfl.import_weekly_data(years))
    missing = REQUIRED_WEEKLY_COLUMNS - set(df.columns)
    if missing:
        raise RuntimeError(f"Schema drift detected in weekly data: missing columns {missing}")

    for col in OPTIONAL_WEEKLY_COLUMNS | OPTIONAL_K_COLUMNS:
        if col not in df.columns:
            df = df.with_columns(pl.lit(0).cast(pl.Int64).alias(col))

    # Collapse kicker distance bands into the three scoring tiers
    df = df.with_columns([
        (
            pl.col("fg_made_0_19").fill_null(0)
            + pl.col("fg_made_20_29").fill_null(0)
            + pl.col("fg_made_30_39").fill_null(0)
        ).alias("fg_made_0_39"),
        pl.col("fg_made_40_49").fill_null(0).alias("fg_made_40_49"),
        (
            pl.col("fg_made_50_59").fill_null(0)
            + pl.col("fg_made_60_").fill_null(0)
        ).alias("fg_made_50_plus"),
        pl.col("pat_made").fill_null(0).alias("pat_made"),
    ])

    needed = df.select([
        "player_id", "season", "week", "opponent_team",
        "passing_yards", "passing_tds", "interceptions",
        "rushing_yards", "rushing_tds", "carries",
        "receptions", "receiving_yards", "receiving_tds", "targets",
        "fumbles_lost",
        "fg_made_0_39", "fg_made_40_49", "fg_made_50_plus", "pat_made",
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
        + s.pat_made  * pl.col("pat_made").fill_null(0)
        + s.fg_0_39   * pl.col("fg_made_0_39").fill_null(0)
        + s.fg_40_49  * pl.col("fg_made_40_49").fill_null(0)
        + s.fg_50_plus * pl.col("fg_made_50_plus").fill_null(0)
    ).alias("fantasy_points_ppr")
    needed = needed.with_columns(points)

    rows = needed.to_dicts()
    conn = connect()
    with transaction(conn):
        conn.executemany(
            """INSERT OR REPLACE INTO weekly_stats
               (player_id, season, week, opponent, pass_yards, pass_tds, interceptions,
                rush_yards, rush_tds, carries, receptions, rec_yards, rec_tds, targets,
                fumbles_lost, fg_made_0_39, fg_made_40_49, fg_made_50_plus, pat_made,
                fantasy_points_ppr)
               VALUES (:player_id, :season, :week, :opponent_team, :passing_yards, :passing_tds,
                       :interceptions, :rushing_yards, :rushing_tds, :carries, :receptions,
                       :receiving_yards, :receiving_tds, :targets, :fumbles_lost,
                       :fg_made_0_39, :fg_made_40_49, :fg_made_50_plus, :pat_made,
                       :fantasy_points_ppr)""",
            rows,
        )


def ingest_dst_weekly(years: list[int]) -> None:
    """Aggregate team DST stats from PBP data and write to weekly_stats.

    Uses a minimal column selection so the PBP download stays manageable.
    Points_allowed is computed from the schedules table (must be ingested first
    with ingest_schedules so that home_score/away_score are populated).
    """
    # Fetch DST player_id -> nfl_team mapping from the players table
    conn = connect()
    dst_by_team: dict[str, str] = {}
    for r in conn.execute(
        "SELECT player_id, nfl_team FROM players WHERE position = 'DST' AND nfl_team IS NOT NULL"
    ):
        dst_by_team[r["nfl_team"]] = r["player_id"]

    if not dst_by_team:
        print("No DST players with nfl_team in players table — run ingest (sleeper) first.")
        return

    # Points allowed per (team, season, week) from schedule scores
    pts_allowed: dict[tuple[str, int, int], int] = {}
    for r in conn.execute(
        """SELECT home_team, away_team, season, week, home_score, away_score
           FROM schedules
           WHERE home_score IS NOT NULL AND away_score IS NOT NULL"""
    ):
        season, week = int(r["season"]), int(r["week"])
        if r["home_team"]:
            pts_allowed[(r["home_team"], season, week)] = int(r["away_score"])
        if r["away_team"]:
            pts_allowed[(r["away_team"], season, week)] = int(r["home_score"])

    # Aggregate DST stats from play-by-play
    try:
        raw = nfl.import_pbp_data(
            years,
            columns=DST_PBP_COLUMNS,
            downcast=True,
        )
    except TypeError:
        # Older nfl-data-py versions don't support columns= parameter
        raw = nfl.import_pbp_data(years, downcast=True)

    df = pl.from_pandas(raw)

    # Ensure columns exist (older datasets may lack some)
    for col in DST_PBP_COLUMNS:
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).cast(pl.Int64).alias(col))

    df = df.filter(pl.col("defteam").is_not_null())

    agg = df.group_by(["defteam", "season", "week"]).agg([
        pl.col("sack").fill_null(0).sum().cast(pl.Int64).alias("dst_sacks"),
        pl.col("interception").fill_null(0).sum().cast(pl.Int64).alias("dst_int"),
        # fumble_recovery_1_team == defteam  →  defense recovered the fumble
        (
            pl.when(pl.col("fumble_recovery_1_team") == pl.col("defteam"))
            .then(1).otherwise(0)
        ).sum().cast(pl.Int64).alias("dst_fumble_rec"),
        pl.col("safety").fill_null(0).sum().cast(pl.Int64).alias("dst_safety"),
        # td_team == defteam covers INT returns, fumble returns, kick/punt returns
        (
            pl.when(
                (pl.col("td_team") == pl.col("defteam")) & (pl.col("touchdown") == 1)
            ).then(1).otherwise(0)
        ).sum().cast(pl.Int64).alias("dst_td"),
    ])

    s = ScoringRules()
    rows = []
    for r in agg.to_dicts():
        team = r["defteam"]
        if not team:
            continue
        player_id = dst_by_team.get(team)
        if player_id is None:
            continue
        season, week = int(r["season"]), int(r["week"])
        pa = pts_allowed.get((team, season, week), -1)
        pts = (
            s.dst_sack      * r["dst_sacks"]
            + s.dst_int       * r["dst_int"]
            + s.dst_fumble_rec * r["dst_fumble_rec"]
            + s.dst_safety    * r["dst_safety"]
            + s.dst_td        * r["dst_td"]
            + s.dst_points_allowed_bonus(pa)
        )
        rows.append({
            "player_id":         player_id,
            "season":            season,
            "week":              week,
            "opponent":          None,
            "dst_sacks":         r["dst_sacks"],
            "dst_int":           r["dst_int"],
            "dst_fumble_rec":    r["dst_fumble_rec"],
            "dst_safety":        r["dst_safety"],
            "dst_td":            r["dst_td"],
            "dst_points_allowed": pa if pa >= 0 else None,
            "fantasy_points_ppr": pts,
        })

    with transaction(conn):
        conn.executemany(
            """INSERT OR REPLACE INTO weekly_stats
               (player_id, season, week, opponent,
                dst_sacks, dst_int, dst_fumble_rec, dst_safety, dst_td,
                dst_points_allowed, fantasy_points_ppr)
               VALUES (:player_id, :season, :week, :opponent,
                       :dst_sacks, :dst_int, :dst_fumble_rec, :dst_safety, :dst_td,
                       :dst_points_allowed, :fantasy_points_ppr)""",
            rows,
        )

    print(f"DST weekly stats ingested: {len(rows)} team-week rows across {len(years)} season(s).")
    matched = len({r['player_id'] for r in rows})
    print(f"  {matched} distinct DST units matched to Sleeper player IDs.")


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
    # Include scores when available (null for future/incomplete games)
    score_cols = [c for c in ["home_score", "away_score"] if c in df.columns]
    select_cols = ["season", "week", "home_team", "away_team"] + score_cols
    needed = df.select(select_cols)
    # Fill missing score columns so the INSERT always has the key
    for col in ["home_score", "away_score"]:
        if col not in needed.columns:
            needed = needed.with_columns(pl.lit(None).cast(pl.Int64).alias(col))

    rows = needed.to_dicts()
    conn = connect()
    with transaction(conn):
        conn.executemany(
            """INSERT OR REPLACE INTO schedules
               (season, week, home_team, away_team, home_score, away_score)
               VALUES (:season, :week, :home_team, :away_team, :home_score, :away_score)""",
            rows,
        )


def _to_int(v: object) -> int | None:
    if v is None:
        return None
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
