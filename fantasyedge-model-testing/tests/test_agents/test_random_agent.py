from model_infrastructure.agents.random_agent import RandomAgent
from model_infrastructure.config import LeagueConfig
from model_infrastructure.domain.draft import DraftState
from model_infrastructure.domain.player import Player
from model_infrastructure.domain.roster import Roster


def _state(league: LeagueConfig, players: list[Player]) -> DraftState:
    return DraftState(
        league=league,
        available={p.player_id: p for p in players},
        rosters=[Roster(league.roster) for _ in range(league.n_teams)],
    )


def test_random_picks_legal_player(league: LeagueConfig, player_pool: list[Player]):
    state = _state(league, player_pool)
    agent = RandomAgent(seed=0)
    pid = agent.pick(state, my_slot=0)
    assert pid in state.available
    assert state.rosters[0].can_add(state.available[pid])


def test_random_is_deterministic_per_seed(league: LeagueConfig, player_pool: list[Player]):
    state = _state(league, player_pool)
    a = RandomAgent(seed=7)
    b = RandomAgent(seed=7)
    assert a.pick(state, 0) == b.pick(state, 0)
