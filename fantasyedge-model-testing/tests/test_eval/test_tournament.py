import numpy as np

from model_infrastructure.agents.random_agent import RandomAgent
from model_infrastructure.config import LeagueConfig
from model_infrastructure.domain.player import Player
from model_infrastructure.eval import metrics, tournament


class _RandomFactory:
    def __call__(self, seed: int):
        return RandomAgent(seed=seed)


def _patch_metric(monkeypatch, league: LeagueConfig):
    def fake_record(rosters, season, league, seed):
        rng = np.random.default_rng(seed)
        return rng.uniform(0.0, 1.0, size=len(rosters)).tolist()
    monkeypatch.setattr(tournament, "stub_h2h_record", fake_record)


def test_paired_bootstrap_ci_shape():
    arr = np.random.default_rng(0).uniform(0, 1, size=(50, 3))
    cis = tournament.paired_bootstrap_ci(arr, n_resamples=200)
    assert cis.shape == (3, 2)
    for low, high in cis:
        assert low <= high


def test_tournament_reproducible(monkeypatch, league: LeagueConfig, player_pool: list[Player]):
    _patch_metric(monkeypatch, league)
    factories = {"r1": _RandomFactory(), "r2": _RandomFactory()}
    a = tournament.run_tournament(
        factories=factories, n_drafts=8, league=league, players=player_pool,
        eval_season=2024, n_workers=1, base_seed=42,
    )
    b = tournament.run_tournament(
        factories=factories, n_drafts=8, league=league, players=player_pool,
        eval_season=2024, n_workers=1, base_seed=42,
    )
    assert a == b


def test_tournament_returns_keys_for_all_factories(monkeypatch, league, player_pool):
    _patch_metric(monkeypatch, league)
    factories = {"r1": _RandomFactory(), "r2": _RandomFactory(), "r3": _RandomFactory()}
    out = tournament.run_tournament(
        factories=factories, n_drafts=4, league=league, players=player_pool,
        eval_season=2024, n_workers=1, base_seed=0,
    )
    assert set(out.keys()) == {"r1", "r2", "r3"}
    for v in out.values():
        assert "mean" in v and "ci_low" in v and "ci_high" in v
        assert v["ci_low"] <= v["mean"] <= v["ci_high"]
