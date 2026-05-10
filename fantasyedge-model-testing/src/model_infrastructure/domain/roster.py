from collections import defaultdict
from model_infrastructure.config import Position, RosterSlot, RosterConfig, FLEX_ELIGIBLE
from model_infrastructure.domain.player import Player

_PRIMARY_SLOT: dict[Position, RosterSlot] = {
    Position.QB: RosterSlot.QB,
    Position.RB: RosterSlot.RB,
    Position.WR: RosterSlot.WR,
    Position.TE: RosterSlot.TE,
    Position.K: RosterSlot.K,
    Position.DST: RosterSlot.DST,
}


class Roster:
    def __init__(self, config: RosterConfig):
        self.config = config
        self.slots: dict[RosterSlot, list[Player]] = defaultdict(list)
        self._caps: dict[RosterSlot, int] = {
            RosterSlot.QB: config.qb, RosterSlot.RB: config.rb,
            RosterSlot.WR: config.wr, RosterSlot.TE: config.te,
            RosterSlot.FLEX: config.flex, RosterSlot.K: config.k,
            RosterSlot.DST: config.dst, RosterSlot.BENCH: config.bench,
        }
        # Mutable counts kept in sync with slots — avoids len() on every can_add() call.
        self._counts: dict[RosterSlot, int] = {s: 0 for s in self._caps}

    def open_slots(self) -> dict[RosterSlot, int]:
        return {s: self._caps[s] - self._counts[s] for s in self._caps}

    def can_add(self, player: Player) -> bool:
        return self._target_slot(player) is not None

    def add(self, player: Player) -> RosterSlot:
        slot = self._target_slot(player)
        if slot is None:
            raise ValueError(f"No legal slot for {player}")
        self.slots[slot].append(player)
        self._counts[slot] += 1
        return slot

    def _target_slot(self, player: Player) -> RosterSlot | None:
        primary = _PRIMARY_SLOT[player.position]
        if self._counts[primary] < self._caps[primary]:
            return primary
        if player.position in FLEX_ELIGIBLE and self._counts[RosterSlot.FLEX] < self._caps[RosterSlot.FLEX]:
            return RosterSlot.FLEX
        if self._counts[RosterSlot.BENCH] < self._caps[RosterSlot.BENCH]:
            return RosterSlot.BENCH
        return None

    def all_players(self) -> list[Player]:
        return [p for players in self.slots.values() for p in players]

    def is_full(self) -> bool:
        return all(self._counts[s] >= self._caps[s] for s in self._caps)

    def signature(self) -> dict:
        return {pos: sum(1 for p in self.all_players() if p.position == pos)
                for pos in Position}
