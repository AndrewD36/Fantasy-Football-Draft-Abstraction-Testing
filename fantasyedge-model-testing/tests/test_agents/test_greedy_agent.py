from model_infrastructure.agents.greedy_projection_agent import GreedyProjectionAgent
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


def test_greedy_picks_highest_prior_legal(league: LeagueConfig, player_pool: list[Player]):
    state = _state(league, player_pool)
    prior = {p.player_id: p.prior_season_points or 0.0 for p in player_pool}
    agent = GreedyProjectionAgent(prior)
    pid = agent.pick(state, my_slot=0)
    expected = max(prior, key=lambda k: prior[k])
    assert pid == expected


def test_greedy_skips_unfittable(league: LeagueConfig, player_pool: list[Player]):
    state = _state(league, player_pool)
    prior = {p.player_id: p.prior_season_points or 0.0 for p in player_pool}
    # Fill the QB slot.
    qbs = [p for p in player_pool if p.position.value == "QB"]
    state.rosters[0].add(qbs[0])
    state.available.pop(qbs[0].player_id)
    # The next QB still has high prior points but we've capped QB at 1.
    # Greedy must still pick *something* legal (it'll fall through to top non-QB).
    agent = GreedyProjectionAgent(prior)
    pid = agent.pick(state, my_slot=0)
    assert state.rosters[0].can_add(state.available[pid])
