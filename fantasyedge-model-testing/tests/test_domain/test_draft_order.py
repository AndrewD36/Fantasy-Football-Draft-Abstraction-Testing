from model_infrastructure.domain.draft import snake_pick_order


def test_snake_order_length():
    order = snake_pick_order(n_teams=12, n_rounds=16)
    assert len(order) == 192


def test_snake_round_one_forward():
    order = snake_pick_order(n_teams=12, n_rounds=16)
    assert order[:12] == list(range(12))


def test_snake_round_two_reverse():
    order = snake_pick_order(n_teams=12, n_rounds=16)
    assert order[12:24] == list(range(11, -1, -1))


def test_snake_pivot_picks():
    order = snake_pick_order(n_teams=12, n_rounds=16)
    # 1-indexed picks 12 and 13 (round 1 last, round 2 first) both go to slot 11.
    assert order[11] == 11
    assert order[12] == 11
    # picks 24 and 25 (round 2 last, round 3 first) both go to slot 0.
    assert order[23] == 0
    assert order[24] == 0


def test_snake_round_three_forward():
    order = snake_pick_order(n_teams=12, n_rounds=16)
    assert order[24:36] == list(range(12))
