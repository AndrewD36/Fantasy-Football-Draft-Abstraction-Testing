from pydantic import BaseModel
from model_infrastructure.config import Position

class Player(BaseModel, frozen=True):
    player_id: str
    name: str
    position: Position
    team: str | None = None
    bye_week: int | None = None
    # Phase 1 will add projection_mean, projection_std etc.
    prior_season_points: float | None = None  # stub for Week 3 GreedyAgent

    def __repr__(self) -> str:
        return f"{self.name} ({self.position} {self.team})"