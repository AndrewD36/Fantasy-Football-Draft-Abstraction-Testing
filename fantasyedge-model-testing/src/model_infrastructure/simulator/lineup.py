from collections import defaultdict

from model_infrastructure.config import FLEX_ELIGIBLE, Position, RosterConfig
from model_infrastructure.domain.roster import Roster


def optimal_lineup_score(
    roster: Roster, weekly_points: dict[str, float], config: RosterConfig
) -> float:
    """Greedy by-position assignment. Exact for our roster shape
    (1QB / 2RB / 2WR / 1TE / 2FLEX / K / DST) because FLEX is the only
    overlap and it takes the best leftover RB/WR/TE - no swap can do better.
    """
    players = roster.all_players()
    points = {p: weekly_points.get(p.player_id, 0.0) for p in players}

    by_pos: dict[Position, list] = defaultdict(list)
    for p in players:
        by_pos[p.position].append(p)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda p: points[p], reverse=True)

    total = 0.0
    used: set = set()

    starter_caps: list[tuple[Position, int]] = [
        (Position.QB, config.qb),
        (Position.RB, config.rb),
        (Position.WR, config.wr),
        (Position.TE, config.te),
        (Position.K, config.k),
        (Position.DST, config.dst),
    ]
    for pos, cap in starter_caps:
        for p in by_pos[pos][:cap]:
            total += points[p]
            used.add(p)

    flex_pool = sorted(
        [p for p in players if p.position in FLEX_ELIGIBLE and p not in used],
        key=lambda p: points[p],
        reverse=True,
    )
    for p in flex_pool[: config.flex]:
        total += points[p]

    return total
