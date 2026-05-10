from model_infrastructure.config import Position, RosterConfig
from model_infrastructure.domain.player import Player
from model_infrastructure.domain.roster import Roster
from model_infrastructure.simulator.lineup import optimal_lineup_score


def _player(pid: str, pos: Position) -> Player:
    return Player(player_id=pid, name=pid, position=pos)


def _build_full_roster(roster_cfg: RosterConfig) -> Roster:
    """A roster shaped exactly like the starter requirements: 1QB/2RB/2WR/1TE/2FLEX/K/DST + bench."""
    r = Roster(roster_cfg)
    r.add(_player("qb1", Position.QB))
    r.add(_player("rb1", Position.RB))
    r.add(_player("rb2", Position.RB))
    r.add(_player("wr1", Position.WR))
    r.add(_player("wr2", Position.WR))
    r.add(_player("te1", Position.TE))
    # Two more flex-eligible -> end up in FLEX
    r.add(_player("rb3_flex", Position.RB))
    r.add(_player("wr3_flex", Position.WR))
    r.add(_player("k1", Position.K))
    r.add(_player("dst1", Position.DST))
    return r


def test_known_optimal_lineup_score(roster_cfg: RosterConfig):
    r = _build_full_roster(roster_cfg)
    pts = {
        "qb1": 25.0,
        "rb1": 18.0, "rb2": 12.0, "rb3_flex": 5.0,
        "wr1": 22.0, "wr2": 14.0, "wr3_flex": 9.0,
        "te1": 11.0,
        "k1": 7.0, "dst1": 8.0,
    }
    # Starters: QB(25) + RB1(18) + RB2(12) + WR1(22) + WR2(14) + TE(11) + K(7) + DST(8) = 117
    # FLEX: 2 best of {rb3_flex=5, wr3_flex=9} -> 9 + 5 = 14
    expected = 117 + 14
    got = optimal_lineup_score(r, pts, roster_cfg)
    assert abs(got - expected) < 1e-6


def test_flex_picks_best_remaining_eligible(roster_cfg: RosterConfig):
    """If the best leftover RB/WR/TE outscores a starting WR2, FLEX should still pick
    only from leftovers - the starter-WR2 is already counted."""
    r = Roster(roster_cfg)
    r.add(_player("qb1", Position.QB))
    r.add(_player("rb1", Position.RB))
    r.add(_player("rb2", Position.RB))
    r.add(_player("wr1", Position.WR))
    r.add(_player("wr2", Position.WR))
    r.add(_player("te1", Position.TE))
    # The "leftover" RB has the highest score of all RBs.
    r.add(_player("rb_bench", Position.RB))
    r.add(_player("wr_bench", Position.WR))
    r.add(_player("k1", Position.K))
    r.add(_player("dst1", Position.DST))
    pts = {
        "qb1": 10.0,
        "rb1": 100.0, "rb2": 1.0, "rb_bench": 50.0,
        "wr1": 10.0, "wr2": 10.0, "wr_bench": 30.0,
        "te1": 10.0, "k1": 5.0, "dst1": 5.0,
    }
    # Starters (no FLEX yet): 10+100+1+10+10+10+5+5 = 151. FLEX2: 50+30 = 80. Total 231.
    expected = 231.0
    assert abs(optimal_lineup_score(r, pts, roster_cfg) - expected) < 1e-6


def test_missing_points_default_to_zero(roster_cfg: RosterConfig):
    r = _build_full_roster(roster_cfg)
    score = optimal_lineup_score(r, {}, roster_cfg)
    assert score == 0.0
