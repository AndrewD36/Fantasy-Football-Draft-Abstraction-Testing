from model_infrastructure.config import Position
from model_infrastructure.data.db import connect
from model_infrastructure.domain.player import Player


def load_players_from_db(season: int | None = None) -> list[Player]:
    """All draftable players. If season is given, attach prior-season actual PPR points
    (used by GreedyProjectionAgent in Phase 0) and bye week from that season's schedule."""
    conn = connect()
    rows = conn.execute(
        """SELECT p.player_id, p.full_name, p.position
           FROM players p
           WHERE p.position IN ('QB','RB','WR','TE','K','DST')"""
    ).fetchall()

    prior: dict[str, float] = {}
    teams: dict[str, str | None] = {}
    byes: dict[str, int | None] = {}
    if season is not None:
        prior = load_prior_year_points(season)
        for r in conn.execute(
            "SELECT player_id, team FROM player_seasons WHERE season = ?",
            (season,),
        ):
            teams[r["player_id"]] = r["team"]
        byes = _load_bye_weeks(season)

    players: list[Player] = []
    for r in rows:
        pid = r["player_id"]
        team = teams.get(pid)
        players.append(
            Player(
                player_id=pid,
                name=r["full_name"],
                position=Position(r["position"]),
                team=team,
                bye_week=byes.get(team) if team is not None else None,
                prior_season_points=prior.get(pid),
            )
        )
    return players


def load_prior_year_points(season: int) -> dict[str, float]:
    """Sum of fantasy_points_ppr by canonical player_id for the given season."""
    conn = connect()
    rows = conn.execute(
        """SELECT player_id, SUM(fantasy_points_ppr) AS pts
           FROM weekly_stats
           WHERE season = ?
           GROUP BY player_id""",
        (season,),
    ).fetchall()
    return {r["player_id"]: float(r["pts"] or 0.0) for r in rows}


def load_weekly_points(season: int) -> dict[tuple[str, int], float]:
    """(player_id, week) -> points for the given season."""
    conn = connect()
    rows = conn.execute(
        "SELECT player_id, week, fantasy_points_ppr FROM weekly_stats WHERE season = ?",
        (season,),
    ).fetchall()
    return {(r["player_id"], int(r["week"])): float(r["fantasy_points_ppr"] or 0.0) for r in rows}


def load_adp_table(season: int, source: str = "fantasypros") -> dict[str, float]:
    """player_id -> ADP overall rank for the most recent snapshot of the given source/season."""
    conn = connect()
    snap = conn.execute(
        "SELECT MAX(snapshot_date) FROM adp WHERE season = ? AND source = ?",
        (season, source),
    ).fetchone()
    if snap is None or snap[0] is None:
        return {}
    rows = conn.execute(
        """SELECT player_id, adp_overall FROM adp
           WHERE season = ? AND source = ? AND snapshot_date = ?""",
        (season, source, snap[0]),
    ).fetchall()
    return {r["player_id"]: float(r["adp_overall"]) for r in rows}


def _load_bye_weeks(season: int) -> dict[str, int]:
    """Derive each team's bye week from the schedule (the missing week for that team)."""
    conn = connect()
    rows = conn.execute(
        "SELECT week, home_team, away_team FROM schedules WHERE season = ?",
        (season,),
    ).fetchall()
    if not rows:
        return {}
    weeks_by_team: dict[str, set[int]] = {}
    all_weeks: set[int] = set()
    for r in rows:
        w = int(r["week"])
        all_weeks.add(w)
        for t in (r["home_team"], r["away_team"]):
            if t:
                weeks_by_team.setdefault(t, set()).add(w)
    byes: dict[str, int] = {}
    for team, played in weeks_by_team.items():
        missing = all_weeks - played
        if len(missing) == 1:
            byes[team] = next(iter(missing))
    return byes
