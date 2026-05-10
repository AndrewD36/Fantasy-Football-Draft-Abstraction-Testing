import pytest

from model_infrastructure.config import LeagueConfig, Position, RosterConfig
from model_infrastructure.domain.player import Player


@pytest.fixture
def league() -> LeagueConfig:
    return LeagueConfig()


@pytest.fixture
def roster_cfg() -> RosterConfig:
    return RosterConfig()


@pytest.fixture
def player_pool() -> list[Player]:
    """A synthetic pool large enough for a 12x16 = 192-pick draft. Roughly NFL position mix."""
    pool: list[Player] = []
    counts = {
        Position.QB: 36,
        Position.RB: 80,
        Position.WR: 100,
        Position.TE: 36,
        Position.K: 32,
        Position.DST: 32,
    }
    pid = 0
    for pos, n in counts.items():
        for i in range(n):
            pool.append(
                Player(
                    player_id=f"{pos.value}{i:03d}",
                    name=f"{pos.value} Player {i}",
                    position=pos,
                    team=None,
                    bye_week=(i % 14) + 1,
                    prior_season_points=float(300 - i),
                )
            )
            pid += 1
    return pool
