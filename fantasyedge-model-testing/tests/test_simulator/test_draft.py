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
