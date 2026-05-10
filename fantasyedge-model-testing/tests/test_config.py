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