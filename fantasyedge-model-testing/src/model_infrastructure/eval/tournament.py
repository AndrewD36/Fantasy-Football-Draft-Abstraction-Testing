import multiprocessing as mp
import random
from typing import Callable

import numpy as np

from model_infrastructure.config import LeagueConfig
from model_infrastructure.domain.player import Player
from model_infrastructure.eval.metrics import stub_h2h_record
from model_infrastructure.simulator.draft import DraftSimulator

AgentFactory = Callable[[int], object]  # (seed) -> Agent


def _run_one(args):
    league, players, factories, slot_assignment, draft_seed, eval_seed, eval_season = args
    agents = [factories[fac_idx](draft_seed + slot)
              for slot, fac_idx in enumerate(slot_assignment)]
    sim = DraftSimulator(league, players)
    rosters = sim.run(agents, seed=draft_seed)
    record = stub_h2h_record(rosters, season=eval_season, league=league, seed=eval_seed)
    # Average across slots for each factory (a factory may occupy multiple slots).
    totals = [0.0] * len(factories)
    counts = [0] * len(factories)
    for slot, fac_idx in enumerate(slot_assignment):
        totals[fac_idx] += record[slot]
        counts[fac_idx] += 1
    return [totals[i] / counts[i] if counts[i] else 0.0 for i in range(len(factories))]


def run_tournament(
    factories: dict[str, AgentFactory],
    n_drafts: int,
    league: LeagueConfig,
    players: list[Player],
    eval_season: int,
    n_workers: int = 1,
    base_seed: int = 0,
) -> dict:
    fac_names = list(factories.keys())
    fac_funcs = [factories[n] for n in fac_names]
    n = league.n_teams
    rng = random.Random(base_seed)

    args_list = []
    for d in range(n_drafts):
        slots = list(range(len(fac_funcs)))
        rng.shuffle(slots)
        slot_assignment = [slots[i % len(slots)] for i in range(n)]
        rng.shuffle(slot_assignment)
        args_list.append((league, players, fac_funcs, slot_assignment,
                          base_seed + d, base_seed + d * 17, eval_season))

    if n_workers <= 1:
        results = [_run_one(a) for a in args_list]
    else:
        with mp.Pool(n_workers) as pool:
            results = pool.map(_run_one, args_list)

    arr = np.array(results)
    means = arr.mean(axis=0)
    cis = paired_bootstrap_ci(arr, n_resamples=2000)
    return {
        fac_names[i]: {
            "mean": float(means[i]),
            "ci_low": float(cis[i, 0]),
            "ci_high": float(cis[i, 1]),
        }
        for i in range(len(fac_names))
    }


def paired_bootstrap_ci(arr: np.ndarray, n_resamples: int = 2000, alpha: float = 0.05):
    n_drafts, n_factories = arr.shape
    rng = np.random.default_rng(0)
    boots = np.empty((n_resamples, n_factories))
    for b in range(n_resamples):
        idx = rng.integers(0, n_drafts, size=n_drafts)
        boots[b] = arr[idx].mean(axis=0)
    return np.quantile(boots, [alpha / 2, 1 - alpha / 2], axis=0).T
