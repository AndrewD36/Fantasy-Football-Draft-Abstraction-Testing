import pytest

from model_infrastructure.agents.random_agent import RandomAgent
from model_infrastructure.config import LeagueConfig
from model_infrastructure.domain.player import Player
from model_infrastructure.simulator.draft import DraftSimulator


def test_full_draft_completes(league: LeagueConfig, player_pool: list[Player]):
    sim = DraftSimulator(league, player_pool)
    agents = [RandomAgent(seed=i) for i in range(league.n_teams)]
    rosters = sim.run(agents, seed=42)
    assert len(rosters) == league.n_teams
    for r in rosters:
        assert r.is_full()


def test_no_duplicate_picks(league: LeagueConfig, player_pool: list[Player]):
    sim = DraftSimulator(league, player_pool)
    agents = [RandomAgent(seed=i) for i in range(league.n_teams)]
    rosters = sim.run(agents, seed=42)
    all_pids = [p.player_id for r in rosters for p in r.all_players()]
    assert len(all_pids) == len(set(all_pids))


def test_determinism(league: LeagueConfig, player_pool: list[Player]):
    sim1 = DraftSimulator(league, player_pool)
    sim2 = DraftSimulator(league, player_pool)
    agents1 = [RandomAgent(seed=i) for i in range(league.n_teams)]
    agents2 = [RandomAgent(seed=i) for i in range(league.n_teams)]
    r1 = sim1.run(agents1, seed=42)
    r2 = sim2.run(agents2, seed=42)
    pids1 = [p.player_id for r in r1 for p in r.all_players()]
    pids2 = [p.player_id for r in r2 for p in r.all_players()]
    assert pids1 == pids2


def test_invalid_pick_raises(league: LeagueConfig, player_pool: list[Player]):
    class BadAgent:
        name = "bad"

        def pick(self, state, my_slot):
            return "does-not-exist"

        def observe(self, state, pick):
            pass

    sim = DraftSimulator(league, player_pool)
    agents = [BadAgent()] + [RandomAgent(seed=i) for i in range(1, league.n_teams)]
    with pytest.raises(ValueError):
        sim.run(agents, seed=0)


# ---------------------------------------------------------------------------
# _last_picks
# ---------------------------------------------------------------------------

def test_last_picks_populated_after_run(league: LeagueConfig, player_pool: list[Player]):
    sim = DraftSimulator(league, player_pool)
    agents = [RandomAgent(seed=i) for i in range(league.n_teams)]
    sim.run(agents, seed=42)
    expected = league.n_teams * league.roster.total_rounds
    assert len(sim._last_picks) == expected


def test_last_picks_sequential_overall_numbers(league: LeagueConfig, player_pool: list[Player]):
    sim = DraftSimulator(league, player_pool)
    agents = [RandomAgent(seed=i) for i in range(league.n_teams)]
    sim.run(agents, seed=42)
    for i, pick in enumerate(sim._last_picks, start=1):
        assert pick.overall == i


def test_last_picks_all_unique_players(league: LeagueConfig, player_pool: list[Player]):
    sim = DraftSimulator(league, player_pool)
    agents = [RandomAgent(seed=i) for i in range(league.n_teams)]
    sim.run(agents, seed=42)
    pids = [p.player_id for p in sim._last_picks]
    assert len(pids) == len(set(pids))


def test_last_picks_reset_on_second_run(league: LeagueConfig, player_pool: list[Player]):
    sim = DraftSimulator(league, player_pool)
    agents = [RandomAgent(seed=i) for i in range(league.n_teams)]
    sim.run(agents, seed=42)
    first_pid = sim._last_picks[0].player_id

    # Different seed → different first pick (random agents)
    sim.run(agents, seed=999)
    second_pid = sim._last_picks[0].player_id

    # Both runs produce a full pick list
    assert len(sim._last_picks) == league.n_teams * league.roster.total_rounds
    # Picks should differ (same agents but different draft seed changes ordering)
    assert first_pid != second_pid


def test_last_picks_empty_before_first_run(league: LeagueConfig, player_pool: list[Player]):
    sim = DraftSimulator(league, player_pool)
    assert sim._last_picks == []
