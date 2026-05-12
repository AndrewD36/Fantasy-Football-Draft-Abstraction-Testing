import json

import numpy as np

from model_infrastructure.agents.random_agent import RandomAgent
from model_infrastructure.config import LeagueConfig
from model_infrastructure.domain.player import Player
from model_infrastructure.eval import metrics, tournament
from model_infrastructure.simulator.draft import DraftSimulator


class _RandomFactory:
    def __call__(self, seed: int):
        return RandomAgent(seed=seed)


def _patch_metric(monkeypatch, league: LeagueConfig):
    def fake_record(rosters, season, league, seed, weekly_pts=None):
        rng = np.random.default_rng(seed)
        return rng.uniform(0.0, 1.0, size=len(rosters)).tolist()
    monkeypatch.setattr(tournament, "stub_h2h_record", fake_record)


# ---------------------------------------------------------------------------
# Existing tests — updated to unpack (stats, draft_records) return value
# ---------------------------------------------------------------------------

def test_paired_bootstrap_ci_shape():
    arr = np.random.default_rng(0).uniform(0, 1, size=(50, 3))
    cis = tournament.paired_bootstrap_ci(arr, n_resamples=200)
    assert cis.shape == (3, 2)
    for low, high in cis:
        assert low <= high


def test_tournament_reproducible(monkeypatch, league: LeagueConfig, player_pool: list[Player]):
    _patch_metric(monkeypatch, league)
    factories = {"r1": _RandomFactory(), "r2": _RandomFactory()}
    a, _ = tournament.run_tournament(
        factories=factories, n_drafts=8, league=league, players=player_pool,
        eval_season=2024, n_workers=1, base_seed=42,
    )
    b, _ = tournament.run_tournament(
        factories=factories, n_drafts=8, league=league, players=player_pool,
        eval_season=2024, n_workers=1, base_seed=42,
    )
    assert a == b


def test_tournament_returns_keys_for_all_factories(monkeypatch, league, player_pool):
    _patch_metric(monkeypatch, league)
    factories = {"r1": _RandomFactory(), "r2": _RandomFactory(), "r3": _RandomFactory()}
    out, _ = tournament.run_tournament(
        factories=factories, n_drafts=4, league=league, players=player_pool,
        eval_season=2024, n_workers=1, base_seed=0,
    )
    assert set(out.keys()) == {"r1", "r2", "r3"}
    for v in out.values():
        assert "mean" in v and "ci_low" in v and "ci_high" in v
        assert v["ci_low"] <= v["mean"] <= v["ci_high"]


# ---------------------------------------------------------------------------
# picks_hash
# ---------------------------------------------------------------------------

def test_picks_hash_is_16_char_hex(league: LeagueConfig, player_pool: list[Player]):
    sim = DraftSimulator(league, player_pool)
    agents = [RandomAgent(seed=i) for i in range(league.n_teams)]
    sim.run(agents, seed=42)
    h = tournament.picks_hash(sim._last_picks)
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_picks_hash_deterministic(league: LeagueConfig, player_pool: list[Player]):
    sim = DraftSimulator(league, player_pool)
    agents = [RandomAgent(seed=i) for i in range(league.n_teams)]
    sim.run(agents, seed=42)
    assert tournament.picks_hash(sim._last_picks) == tournament.picks_hash(sim._last_picks)


def test_picks_hash_differs_for_different_seeds(league: LeagueConfig, player_pool: list[Player]):
    sim = DraftSimulator(league, player_pool)
    agents = [RandomAgent(seed=i) for i in range(league.n_teams)]
    sim.run(agents, seed=42)
    h1 = tournament.picks_hash(sim._last_picks)
    sim.run(agents, seed=99)
    h2 = tournament.picks_hash(sim._last_picks)
    assert h1 != h2


# ---------------------------------------------------------------------------
# run_tournament draft_records return value
# ---------------------------------------------------------------------------

def test_run_tournament_returns_two_tuple(monkeypatch, league, player_pool):
    _patch_metric(monkeypatch, league)
    result = tournament.run_tournament(
        factories={"r1": _RandomFactory()}, n_drafts=3,
        league=league, players=player_pool, eval_season=2024, base_seed=0,
    )
    assert isinstance(result, tuple) and len(result) == 2


def test_draft_records_count_matches_n_drafts(monkeypatch, league, player_pool):
    _patch_metric(monkeypatch, league)
    n = 5
    _, draft_records = tournament.run_tournament(
        factories={"r1": _RandomFactory(), "r2": _RandomFactory()},
        n_drafts=n, league=league, players=player_pool,
        eval_season=2024, base_seed=0,
    )
    assert len(draft_records) == n


def test_draft_records_have_correct_keys(monkeypatch, league, player_pool):
    _patch_metric(monkeypatch, league)
    _, draft_records = tournament.run_tournament(
        factories={"r1": _RandomFactory(), "r2": _RandomFactory()},
        n_drafts=3, league=league, players=player_pool,
        eval_season=2024, base_seed=0,
    )
    for i, rec in enumerate(draft_records):
        assert rec["draft_index"] == i
        sa = json.loads(rec["slot_assignment"])
        assert len(sa) == league.n_teams
        assert all(isinstance(x, int) for x in sa)
        h = rec["picks_hash"]
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


def test_draft_records_hashes_differ_across_drafts(monkeypatch, league, player_pool):
    _patch_metric(monkeypatch, league)
    _, draft_records = tournament.run_tournament(
        factories={"r1": _RandomFactory(), "r2": _RandomFactory()},
        n_drafts=4, league=league, players=player_pool,
        eval_season=2024, base_seed=0,
    )
    hashes = [r["picks_hash"] for r in draft_records]
    assert len(set(hashes)) == len(hashes), "Each draft should produce a unique picks hash"


# ---------------------------------------------------------------------------
# replay_draft
# ---------------------------------------------------------------------------

def test_replay_draft_hash_matches_original(monkeypatch, league, player_pool):
    _patch_metric(monkeypatch, league)
    factories = {"r1": _RandomFactory(), "r2": _RandomFactory()}
    _, draft_records = tournament.run_tournament(
        factories=factories, n_drafts=3, league=league, players=player_pool,
        eval_season=2024, base_seed=7,
    )

    config = {"seed": 7, "agents": "r1,r2"}
    for rec in draft_records:
        slot_assignment = json.loads(rec["slot_assignment"])
        picks = tournament.replay_draft(
            experiment_config=config,
            slot_assignment=slot_assignment,
            factories=factories,
            players=player_pool,
            draft_index=rec["draft_index"],
        )
        assert tournament.picks_hash(picks) == rec["picks_hash"]


def test_replay_draft_returns_all_picks(league, player_pool):
    factories = {"r1": _RandomFactory()}
    config = {"seed": 0, "agents": "r1"}
    slot_assignment = [0] * league.n_teams
    picks = tournament.replay_draft(
        experiment_config=config,
        slot_assignment=slot_assignment,
        factories=factories,
        players=player_pool,
        draft_index=0,
    )
    assert len(picks) == league.n_teams * league.roster.total_rounds
