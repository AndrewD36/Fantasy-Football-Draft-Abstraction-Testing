from model_infrastructure.agents.adp_agent import ADPAgent
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


def test_adp_picks_legal_player(league: LeagueConfig, player_pool: list[Player]):
    state = _state(league, player_pool)
    adp = {p.player_id: float(i) for i, p in enumerate(player_pool)}
    agent = ADPAgent(adp, temperature=2.0, seed=0)
    pid = agent.pick(state, my_slot=0)
    assert pid in state.available


def test_adp_low_temperature_prefers_low_adp(league: LeagueConfig, player_pool: list[Player]):
    state = _state(league, player_pool)
    adp = {p.player_id: float(i) for i, p in enumerate(player_pool)}
    agent = ADPAgent(adp, temperature=0.05, seed=0)
    counts: dict[str, int] = {}
    for _ in range(50):
        pid = agent.pick(state, my_slot=0)
        counts[pid] = counts.get(pid, 0) + 1
    top_pid = min(adp, key=lambda k: adp[k])
    assert counts.get(top_pid, 0) >= 40


def test_adp_seed_determinism(league: LeagueConfig, player_pool: list[Player]):
    state = _state(league, player_pool)
    adp = {p.player_id: float(i) for i, p in enumerate(player_pool)}
    a = ADPAgent(adp, seed=42)
    b = ADPAgent(adp, seed=42)
    seq_a = [a.pick(state, 0) for _ in range(5)]
    seq_b = [b.pick(state, 0) for _ in range(5)]
    assert seq_a == seq_b
