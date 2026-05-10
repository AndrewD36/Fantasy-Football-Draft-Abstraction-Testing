"""Simulation correctness checks, called by the `validate-sim` CLI command.

Each check_* function returns a list of failure strings (empty = passed).
All checks use purely synthetic data except check_data_sanity, which queries the DB.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from model_infrastructure.config import FLEX_ELIGIBLE, LeagueConfig, Position, RosterConfig
from model_infrastructure.domain.draft import snake_pick_order
from model_infrastructure.domain.player import Player
from model_infrastructure.domain.roster import Roster
from model_infrastructure.eval.metrics import generate_round_robin
from model_infrastructure.simulator.draft import DraftSimulator
from model_infrastructure.simulator.lineup import optimal_lineup_score


def check_snake_order(league: LeagueConfig) -> list[str]:
    """snake_pick_order must alternate direction and cover all teams every round."""
    n, rounds = league.n_teams, league.roster.total_rounds
    order = snake_pick_order(n, rounds)
    failures: list[str] = []

    if len(order) != n * rounds:
        return [f"snake_order length {len(order)} != {n * rounds}"]

    for rd in range(rounds):
        chunk = order[rd * n : (rd + 1) * n]
        expected = list(range(n)) if rd % 2 == 0 else list(range(n - 1, -1, -1))
        if chunk != expected:
            failures.append(
                f"Round {rd + 1} wrong direction: first 3 = {chunk[:3]}, expected {expected[:3]}"
            )
    return failures


def check_draft_invariants(league: LeagueConfig) -> list[str]:
    """A full synthetic draft must produce complete, non-overlapping rosters."""
    from model_infrastructure.agents.random_agent import RandomAgent

    n, rounds = league.n_teams, league.roster.total_rounds
    r = league.roster

    players: list[Player] = []
    pid = 0
    for pos, count in [
        (Position.QB,  n * (r.qb + 2)),
        (Position.RB,  n * (r.rb + r.flex + 3)),
        (Position.WR,  n * (r.wr + r.flex + 3)),
        (Position.TE,  n * (r.te + 2)),
        (Position.K,   n * (r.k + 2)),
        (Position.DST, n * (r.dst + 2)),
    ]:
        for _ in range(count):
            players.append(Player(player_id=str(pid), name=f"P{pid}", position=pos))
            pid += 1

    agents = [RandomAgent(seed=i) for i in range(n)]
    try:
        rosters = DraftSimulator(league, players).run(agents, seed=42)
    except Exception as exc:
        return [f"Draft raised exception: {exc}"]

    failures: list[str] = []
    all_players = [p for roster in rosters for p in roster.all_players()]

    if len(all_players) != n * rounds:
        failures.append(f"Total picks {len(all_players)} != {n * rounds}")

    dupe_ids = [pid for pid, cnt in Counter(p.player_id for p in all_players).items() if cnt > 1]
    if dupe_ids:
        failures.append(f"Duplicate player IDs drafted: {dupe_ids[:5]}")

    for i, roster in enumerate(rosters):
        if not roster.is_full():
            failures.append(f"Team {i} roster not full after draft")

    return failures


def check_lineup_optimizer(config: RosterConfig) -> list[str]:
    """Known roster + known weekly points must produce the expected optimal score.

    Layout (config defaults: 1QB/2RB/2WR/1TE/2FLEX/1K/1DST/6bench):
    Starters: QB1=50, RB1=40, RB2=30, WR1=35, WR2=25, TE1=28
    FLEX best-2 from leftover RB/WR/TE: RB3=20, WR3=15
    K1=12, DST1=8
    Expected total = 263
    Bench players all score < RB3/WR3 so they must not start.
    """
    roster = Roster(config)
    specs = [
        ("q1",  "QB1",  Position.QB,  50.0),
        ("r1",  "RB1",  Position.RB,  40.0),
        ("r2",  "RB2",  Position.RB,  30.0),
        ("w1",  "WR1",  Position.WR,  35.0),
        ("w2",  "WR2",  Position.WR,  25.0),
        ("t1",  "TE1",  Position.TE,  28.0),
        ("r3",  "RB3",  Position.RB,  20.0),
        ("w3",  "WR3",  Position.WR,  15.0),
        ("k1",  "K1",   Position.K,   12.0),
        ("d1",  "DST1", Position.DST,  8.0),
        # bench — all below the FLEX threshold
        ("r4",  "RB4",  Position.RB,   5.0),
        ("w4",  "WR4",  Position.WR,   3.0),
        ("q2",  "QB2",  Position.QB,   2.0),
        ("t2",  "TE2",  Position.TE,   1.0),
        ("w5",  "WR5",  Position.WR,   0.0),
        ("r5",  "RB5",  Position.RB,   0.0),
    ]
    weekly_pts: dict[str, float] = {}
    for pid, name, pos, pts in specs:
        roster.add(Player(player_id=pid, name=name, position=pos))
        weekly_pts[pid] = pts

    expected = 50 + 40 + 30 + 35 + 25 + 28 + 20 + 15 + 12 + 8  # 263
    got = optimal_lineup_score(roster, weekly_pts, config)

    if abs(got - expected) > 1e-6:
        return [f"Lineup score {got:.4f} != expected {expected}"]
    return []


def check_schedule_balance(league: LeagueConfig) -> list[str]:
    """Every team plays exactly once per week; total wins == n_teams/2 per week."""
    n, weeks = league.n_teams, league.regular_season_weeks
    schedule = generate_round_robin(n, weeks, seed=42)
    failures: list[str] = []

    by_week: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for week, home, away in schedule:
        by_week[week].append((home, away))

    for w in range(1, weeks + 1):
        games = by_week.get(w, [])
        if len(games) != n // 2:
            failures.append(f"Week {w}: {len(games)} games, expected {n // 2}")
            continue
        teams_this_week = [t for g in games for t in g]
        if len(set(teams_this_week)) != n:
            failures.append(f"Week {w}: teams don't cover all {n} slots")
        dupes = [t for t, cnt in Counter(teams_this_week).items() if cnt > 1]
        if dupes:
            failures.append(f"Week {w}: teams play multiple games: {dupes}")

    return failures


def check_data_sanity(season: int) -> list[str]:
    """Spot-check that weekly_stats for the given season has plausible values."""
    from model_infrastructure.data.db import connect

    conn = connect()
    failures: list[str] = []

    rows = conn.execute(
        """SELECT player_id, SUM(fantasy_points_ppr) AS total
           FROM weekly_stats WHERE season = ? GROUP BY player_id""",
        (season,),
    ).fetchall()

    if not rows:
        return [f"No weekly_stats rows for season {season} — run ingest first"]

    totals: dict[str, float] = {r["player_id"]: float(r["total"] or 0) for r in rows}
    nonzero = sum(1 for v in totals.values() if v > 0)
    if nonzero < 200:
        failures.append(f"Only {nonzero} players with >0 PPR points for {season} (expected 200+)")

    # Position-level sanity via player table join
    pos_rows = conn.execute(
        """SELECT p.position, SUM(ws.fantasy_points_ppr) AS total
           FROM weekly_stats ws
           JOIN players p ON p.player_id = ws.player_id
           WHERE ws.season = ?
           GROUP BY p.position
           ORDER BY total DESC""",
        (season,),
    ).fetchall()
    pos_totals = {r["position"]: float(r["total"] or 0) for r in pos_rows}
    if pos_totals.get("QB", 0) < 1000:
        failures.append(f"Total QB PPR for {season} = {pos_totals.get('QB', 0):.0f}, expected 1000+")
    if pos_totals.get("WR", 0) < 3000:
        failures.append(f"Total WR PPR for {season} = {pos_totals.get('WR', 0):.0f}, expected 3000+")

    # Best single player should score > 300 PPR points in a full season
    best = max(totals.values())
    if best < 300:
        failures.append(f"Best player season total {best:.1f} < 300 — data may be incomplete")

    return failures
