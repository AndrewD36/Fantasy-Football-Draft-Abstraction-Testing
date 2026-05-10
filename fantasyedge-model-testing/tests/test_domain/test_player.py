import pytest

from model_infrastructure.config import Position
from model_infrastructure.domain.player import Player


def test_player_is_hashable():
    p = Player(player_id="1", name="Test", position=Position.RB)
    s = {p, p}
    assert len(s) == 1


def test_player_is_immutable():
    p = Player(player_id="1", name="Test", position=Position.RB)
    with pytest.raises(Exception):
        p.name = "Other"  # type: ignore[misc]


def test_player_repr_includes_position_and_team():
    p = Player(player_id="1", name="Pat Mahomes", position=Position.QB, team="KC")
    assert "Pat Mahomes" in repr(p)
    assert "QB" in repr(p)
    assert "KC" in repr(p)
