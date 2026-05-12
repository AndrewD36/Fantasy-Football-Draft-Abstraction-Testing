from model_infrastructure.config import LeagueConfig
from model_infrastructure.domain.draft import DraftState, Pick, snake_pick_order
from model_infrastructure.domain.player import Player
from model_infrastructure.domain.roster import Roster
from model_infrastructure.agents.base_agent import Agent

class DraftSimulator:
    def __init__(self, league: LeagueConfig, players: list[Player]):
        self.league = league
        self.players = {p.player_id: p for p in players}
        self._last_picks: list[Pick] = []  # populated by run(); used for hash/replay

    def run(self, agents: list[Agent], seed: int = 0) -> list[Roster]:
        assert len(agents) == self.league.n_teams
        rosters = [Roster(self.league.roster) for _ in range(self.league.n_teams)]
        state = DraftState(
            league=self.league,
            available=dict(self.players),
            rosters=rosters,
        )
        order = snake_pick_order(self.league.n_teams, self.league.roster.total_rounds)
        self._last_picks = []
        for overall, team_slot in enumerate(order, start=1):
            agent = agents[team_slot]
            picked_id = agent.pick(state, team_slot)
            self._validate_pick(picked_id, state, team_slot)
            player = state.available.pop(picked_id)
            rosters[team_slot].add(player)
            pick = Pick(overall=overall, round=(overall - 1) // self.league.n_teams + 1,
                        team_slot=team_slot, player_id=picked_id)
            state.history.append(pick)
            self._last_picks.append(pick)
            for a in agents:
                a.observe(state, pick)
        return rosters

    def _validate_pick(self, pid: str, state: DraftState, slot: int) -> None:
        if pid not in state.available:
            raise ValueError(f"Pick {pid} unavailable")
        if not state.rosters[slot].can_add(state.available[pid]):
            raise ValueError(f"Pick {pid} doesn't fit roster")