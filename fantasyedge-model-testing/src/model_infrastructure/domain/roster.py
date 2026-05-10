from collections import defaultdict
from model_infrastructure.config import Position, RosterSlot, RosterConfig, FLEX_ELIGIBLE
from model_infrastructure.domain.player import Player

class Roster:
    def __init__(self, config: RosterConfig):
        self.config = config
        self.slots: dict[RosterSlot, list[Player]] = defaultdict(list)

    def open_slots(self) -> dict[RosterSlot, int]:
        cap = {RosterSlot.QB: self.config.qb, RosterSlot.RB: self.config.rb,
               RosterSlot.WR: self.config.wr, RosterSlot.TE: self.config.te,
               RosterSlot.FLEX: self.config.flex, RosterSlot.K: self.config.k,
               RosterSlot.DST: self.config.dst, RosterSlot.BENCH: self.config.bench}
        return {s: cap[s] - len(self.slots[s]) for s in RosterSlot}

    def can_add(self, player: Player) -> bool:
        return self._target_slot(player) is not None

    def add(self, player: Player) -> RosterSlot:
        slot = self._target_slot(player)
        if slot is None:
            raise ValueError(f"No legal slot for {player}")
        self.slots[slot].append(player)
        return slot

    def _target_slot(self, player: Player) -> RosterSlot | None:
        opens = self.open_slots()
        primary = {Position.QB: RosterSlot.QB, Position.RB: RosterSlot.RB,
                   Position.WR: RosterSlot.WR, Position.TE: RosterSlot.TE,
                   Position.K: RosterSlot.K, Position.DST: RosterSlot.DST}[player.position]
        if opens[primary] > 0:
            return primary
        if player.position in FLEX_ELIGIBLE and opens[RosterSlot.FLEX] > 0:
            return RosterSlot.FLEX
        if opens[RosterSlot.BENCH] > 0:
            return RosterSlot.BENCH
        return None

    def all_players(self) -> list[Player]:
        return [p for players in self.slots.values() for p in players]

    def is_full(self) -> bool:
        return all(v == 0 for v in self.open_slots().values())

    def signature(self) -> dict:
        """State-abstraction stub - elaborate in Phase 3."""
        return {pos: sum(1 for p in self.all_players() if p.position == pos)
                for pos in Position}