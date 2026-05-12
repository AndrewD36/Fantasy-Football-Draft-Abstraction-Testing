from model_infrastructure.config import LeagueConfig, ScoringRules


def test_total_rounds():
    cfg = LeagueConfig()
    assert cfg.roster.total_rounds == 16


def test_ppr_scoring():
    s = ScoringRules()
    line = {"receptions": 8, "rec_yards": 110, "rec_tds": 1}
    # 8 + 11 + 6 = 25
    assert abs(s.points_for(line) - 25.0) < 1e-6


def test_config_hash_stable():
    a, b = LeagueConfig(), LeagueConfig()
    assert a.config_hash() == b.config_hash()


# ---------------------------------------------------------------------------
# Kicker scoring
# ---------------------------------------------------------------------------

def test_kicker_pat():
    s = ScoringRules()
    assert s.points_for({"pat_made": 3}) == 3.0


def test_kicker_fg_tiers():
    s = ScoringRules()
    assert s.points_for({"fg_made_0_39": 2}) == 6.0
    assert s.points_for({"fg_made_40_49": 1}) == 4.0
    assert s.points_for({"fg_made_50_plus": 1}) == 5.0


def test_kicker_combined():
    s = ScoringRules()
    # 2 PAT + 1 FG<40 + 1 FG 40-49 + 1 FG 50+
    pts = s.points_for({
        "pat_made": 2,
        "fg_made_0_39": 1,
        "fg_made_40_49": 1,
        "fg_made_50_plus": 1,
    })
    assert abs(pts - (2 + 3 + 4 + 5)) < 1e-6


def test_kicker_zero_stats_score_zero():
    s = ScoringRules()
    assert s.points_for({}) == 0.0
    assert s.points_for({"fg_made_0_39": 0, "pat_made": 0}) == 0.0


# ---------------------------------------------------------------------------
# DST scoring
# ---------------------------------------------------------------------------

def test_dst_each_stat_type():
    s = ScoringRules()
    assert s.points_for({"dst_sacks": 1, "dst_points_allowed": -1}) == 1.0
    assert s.points_for({"dst_int": 1, "dst_points_allowed": -1}) == 2.0
    assert s.points_for({"dst_fumble_rec": 1, "dst_points_allowed": -1}) == 2.0
    assert s.points_for({"dst_safety": 1, "dst_points_allowed": -1}) == 2.0
    assert s.points_for({"dst_td": 1, "dst_points_allowed": -1}) == 6.0


def test_dst_combined_with_shutout():
    s = ScoringRules()
    pts = s.points_for({
        "dst_sacks": 3,       # 3
        "dst_int": 2,         # 4
        "dst_fumble_rec": 1,  # 2
        "dst_safety": 1,      # 2
        "dst_td": 1,          # 6
        "dst_points_allowed": 0,  # +10
    })
    assert abs(pts - 27.0) < 1e-6


def test_dst_points_allowed_tier_boundaries():
    s = ScoringRules.dst_points_allowed_bonus
    assert s(0) == 10.0
    assert s(1) == 7.0
    assert s(6) == 7.0
    assert s(7) == 4.0
    assert s(13) == 4.0
    assert s(14) == 1.0
    assert s(20) == 1.0
    assert s(21) == 0.0
    assert s(27) == 0.0
    assert s(28) == -1.0
    assert s(34) == -1.0
    assert s(35) == -4.0
    assert s(50) == -4.0


def test_dst_points_allowed_no_data():
    # -1 signals "no data available" and should contribute 0
    s = ScoringRules()
    assert s.points_for({"dst_points_allowed": -1}) == 0.0
    assert s.points_for({}) == 0.0


def test_dst_high_points_allowed_penalty():
    s = ScoringRules()
    pts = s.points_for({"dst_sacks": 2, "dst_points_allowed": 35})
    assert abs(pts - (2.0 - 4.0)) < 1e-6


# ---------------------------------------------------------------------------
# Offensive scoring still works after additions
# ---------------------------------------------------------------------------

def test_offensive_scoring_unchanged():
    s = ScoringRules()
    line = {
        "pass_yards": 300, "pass_tds": 3, "interceptions": 1,
        "rush_yards": 50, "rush_tds": 1,
        "receptions": 6, "rec_yards": 80, "rec_tds": 1,
    }
    expected = (
        300 * 0.04 + 3 * 4.0 - 1 * 2.0
        + 50 * 0.1 + 1 * 6.0
        + 6 * 1.0 + 80 * 0.1 + 1 * 6.0
    )
    assert abs(s.points_for(line) - expected) < 1e-6
