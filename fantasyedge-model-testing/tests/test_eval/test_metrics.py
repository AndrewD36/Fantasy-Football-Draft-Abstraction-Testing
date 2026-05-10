from model_infrastructure.config import LeagueConfig, Position, RosterConfig
from model_infrastructure.domain.player import Player
from model_infrastructure.domain.roster import Roster
from model_infrastructure.eval import metrics


def _build_full_roster(roster_cfg: RosterConfig) -> Roster:
    r = Roster(roster_cfg)
    spec = [
        ("qb1", Position.QB), ("rb1", Position.RB), ("rb2", Position.RB),
        ("wr1", Position.WR), ("wr2", Position.WR), ("te1", Position.TE),
        ("flex_rb", Position.RB), ("flex_wr", Position.WR),
        ("k1", Position.K), ("dst1", Position.DST),
    ]
    for pid, pos in spec:
        r.add(Player(player_id=pid, name=pid, position=pos))
    return r


def test_round_robin_schedule_shape(league: LeagueConfig):
    sched = metrics.generate_round_robin(n=12, weeks=14, seed=0)
    # 6 matchups per week * 14 weeks = 84.
    assert len(sched) == 84
    assert all(0 <= h < 12 and 0 <= a < 12 and h != a for _, h, a in sched)


def test_stub_h2h_winner_dominates(league: LeagueConfig, monkeypatch):
    """Roster 0 has high-scoring players; everyone else has low. Roster 0 wins everything."""
    # Slot 0 gets unique high-scoring players; slots 1..n_teams-1 share zero-scoring players.
    high_pids = [f"hi_{role}" for role in
                 ("qb", "rb1", "rb2", "wr1", "wr2", "te", "flex_rb", "flex_wr", "k", "dst")]
    low_pids = [f"lo_{role}" for role in
                ("qb", "rb1", "rb2", "wr1", "wr2", "te", "flex_rb", "flex_wr", "k", "dst")]

    def make_roster(pids: list[str]) -> Roster:
        from model_infrastructure.config import Position as P
        positions = [P.QB, P.RB, P.RB, P.WR, P.WR, P.TE, P.RB, P.WR, P.K, P.DST]
        r = Roster(league.roster)
        for pid, pos in zip(pids, positions, strict=True):
            r.add(Player(player_id=pid, name=pid, position=pos))
        return r

    rosters = [make_roster(high_pids)] + [make_roster(low_pids) for _ in range(league.n_teams - 1)]

    def fake_weekly_points(_season: int) -> dict[tuple[str, int], float]:
        out: dict[tuple[str, int], float] = {}
        for w in range(1, league.regular_season_weeks + 1):
            for pid in high_pids:
                out[(pid, w)] = 100.0
            for pid in low_pids:
                out[(pid, w)] = 1.0
        return out

    monkeypatch.setattr(metrics, "load_weekly_points", fake_weekly_points)
    record = metrics.stub_h2h_record(rosters, season=2023, league=league, seed=0)
    assert record[0] == 1.0
    for r in record[1:]:
        assert r < 1.0
