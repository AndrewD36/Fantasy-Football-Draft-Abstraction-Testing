import random
from model_infrastructure.config import LeagueConfig
from model_infrastructure.domain.roster import Roster
from model_infrastructure.simulator.lineup import optimal_lineup_score
from model_infrastructure.data.queries import load_weekly_points

def stub_h2h_record(rosters: list[Roster], season: int, league: LeagueConfig,
                    seed: int,
                    weekly_pts: dict[tuple[str, int], float] | None = None) -> list[float]:
    """For each roster, win rate over a randomly-generated 14-week H2H schedule
    using the prior season's actual weekly points."""
    if weekly_pts is None:
        weekly_pts = load_weekly_points(season)
    n = league.n_teams
    weeks = league.regular_season_weeks
    schedule = generate_round_robin(n, weeks, seed)  # list of (week, home_slot, away_slot)
    weekly_team_score = [[0.0] * (weeks + 1) for _ in range(n)]
    for i, r in enumerate(rosters):
        for w in range(1, weeks + 1):
            wpts = {p.player_id: weekly_pts.get((p.player_id, w), 0.0) for p in r.all_players()}
            weekly_team_score[i][w] = optimal_lineup_score(r, wpts, league.roster)
    wins = [0] * n
    for week, home, away in schedule:
        if weekly_team_score[home][week] > weekly_team_score[away][week]:
            wins[home] += 1
        else:
            wins[away] += 1
    return [w / weeks for w in wins]

def generate_round_robin(n: int, weeks: int, seed: int) -> list[tuple[int, int, int]]:
    """A schedule where each team plays each week, against varied opponents."""
    rng = random.Random(seed)
    teams = list(range(n))
    schedule = []
    for w in range(1, weeks + 1):
        rng.shuffle(teams)
        for i in range(0, n, 2):
            schedule.append((w, teams[i], teams[i+1]))
    return schedule