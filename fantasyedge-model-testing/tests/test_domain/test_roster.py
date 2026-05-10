from model_infrastructure.config import Position, RosterConfig, RosterSlot
from model_infrastructure.domain.player import Player
from model_infrastructure.domain.roster import Roster


def _player(pid: str, pos: Position) -> Player:
    return Player(player_id=pid, name=pid, position=pos)


def test_qb_fills_qb_slot(roster_cfg: RosterConfig):
    r = Roster(roster_cfg)
    slot = r.add(_player("q1", Position.QB))
    assert slot == RosterSlot.QB


def test_rb_fills_flex_after_rb_slots_full(roster_cfg: RosterConfig):
    r = Roster(roster_cfg)
    for i in range(roster_cfg.rb):
        r.add(_player(f"rb{i}", Position.RB))
    slot = r.add(_player("rb_flex", Position.RB))
    assert slot == RosterSlot.FLEX


def test_te_falls_to_flex_after_te_full(roster_cfg: RosterConfig):
    r = Roster(roster_cfg)
    for i in range(roster_cfg.te):
        r.add(_player(f"te{i}", Position.TE))
    slot = r.add(_player("te_flex", Position.TE))
    assert slot == RosterSlot.FLEX


def test_k_does_not_go_to_flex(roster_cfg: RosterConfig):
    r = Roster(roster_cfg)
    for i in range(roster_cfg.k):
        r.add(_player(f"k{i}", Position.K))
    slot = r.add(_player("k_extra", Position.K))
    assert slot == RosterSlot.BENCH


def test_full_roster_rejects(roster_cfg: RosterConfig):
    r = Roster(roster_cfg)
    # Build a pool comfortably larger than total_rounds so we can fill every slot
    # (including the 6 bench spots) without running out of any one position.
    pool: list[Player] = []
    for i in range(20):
        pool.append(_player(f"rb{i}", Position.RB))
    for i in range(20):
        pool.append(_player(f"wr{i}", Position.WR))
    for i in range(5):
        pool.append(_player(f"qb{i}", Position.QB))
    for i in range(5):
        pool.append(_player(f"te{i}", Position.TE))
    for i in range(roster_cfg.k):
        pool.append(_player(f"k{i}", Position.K))
    for i in range(roster_cfg.dst):
        pool.append(_player(f"dst{i}", Position.DST))
    for p in pool:
        if r.can_add(p):
            r.add(p)
        if r.is_full():
            break
    assert r.is_full()
    extra = _player("extra_qb", Position.QB)
    assert not r.can_add(extra)


def test_signature_counts_by_position(roster_cfg: RosterConfig):
    r = Roster(roster_cfg)
    r.add(_player("q1", Position.QB))
    r.add(_player("rb1", Position.RB))
    r.add(_player("rb2", Position.RB))
    sig = r.signature()
    assert sig[Position.QB] == 1
    assert sig[Position.RB] == 2
    assert sig[Position.WR] == 0
