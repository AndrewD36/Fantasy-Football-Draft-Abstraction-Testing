from dataclasses import dataclass, field
from fantasyedge_models.config import LeagueConfig
from fantasyedge_models.domain.player import Player

def snake_pick_order(n_teams: int, n_rounds: int) -> list[int]:
    """Returns team-slot indices in pick order. 12 teams, round 1 = 0..11, round 2 = 11..0, etc."""
    order = []
    for rd in range(n_rounds):
        rng = range(n_teams) if rd % 2 == 0 else range(n_teams - 1, -1, -1)
        order.extend(rng)
    return order

@dataclass(frozen=True)
class Pick:
    overall: int            # 1-indexed, 1..192 for 12x16
    round: int              # 1-indexed
    team_slot: int          # 0-indexed
    player_id: str

@dataclass
class DraftState:
    league: LeagueConfig
    available: dict[str, Player]      # player_id -> Player
    history: list[Pick] = field(default_factory=list)
    rosters: list = field(default_factory=list)  # initialized by simulator

    @property
    def overall_pick(self) -> int:
        return len(self.history) + 1

    @property
    def round(self) -> int:
        return ((self.overall_pick - 1) // self.league.n_teams) + 1

    @property
    def picks_remaining(self) -> int:
        return self.league.n_teams * self.league.roster.total_rounds - len(self.history)

    def picks_until_slot(self, my_slot: int) -> int:
        order = snake_pick_order(self.league.n_teams, self.league.roster.total_rounds)
        for i in range(len(self.history), len(order)):
            if order[i] == my_slot:
                return i - len(self.history)
        raise IndexError("Slot not found in remaining order")