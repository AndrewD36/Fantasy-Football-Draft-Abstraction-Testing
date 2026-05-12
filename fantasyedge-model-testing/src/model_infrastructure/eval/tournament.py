import hashlib
import json
import multiprocessing as mp
import random
import time
from typing import Callable

import numpy as np

from model_infrastructure.config import LeagueConfig
from model_infrastructure.domain.player import Player
from model_infrastructure.eval.metrics import stub_h2h_record
from model_infrastructure.data.queries import load_weekly_points
from model_infrastructure.simulator.draft import DraftSimulator

AgentFactory = Callable[[int], object]  # (seed) -> Agent


def picks_hash(picks) -> str:
    """SHA256[:16] of the canonical pick sequence. Used only for replay verification."""
    canonical = ";".join(
        f"{p.player_id}:{p.team_slot}:{p.round}:{p.overall}" for p in picks
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _run_one(args):
    league, players, factories, slot_assignment, draft_seed, eval_seed, eval_season, weekly_pts = args
    agents = [factories[fac_idx](draft_seed + slot)
              for slot, fac_idx in enumerate(slot_assignment)]
    sim = DraftSimulator(league, players)
    rosters = sim.run(agents, seed=draft_seed)
    record = stub_h2h_record(rosters, season=eval_season, league=league, seed=eval_seed,
                             weekly_pts=weekly_pts)
    totals = [0.0] * len(factories)
    counts = [0] * len(factories)
    for slot, fac_idx in enumerate(slot_assignment):
        totals[fac_idx] += record[slot]
        counts[fac_idx] += 1

    # Compute a verification hash of the exact pick sequence (cheap, O(n_picks))
    draft_state_picks = sim._last_picks if hasattr(sim, "_last_picks") else []
    p_hash = picks_hash(draft_state_picks)

    win_rates = [totals[i] / counts[i] if counts[i] else 0.0 for i in range(len(factories))]
    return win_rates, p_hash


def _run_sequential(
    args_list: list,
    fac_names: list[str],
    report_interval_s: float = 10.0,
) -> tuple[list, list]:
    """Run drafts sequentially, printing a progress line every `report_interval_s` seconds.

    Returns (results, hashes) where results[i] is the win-rate row and hashes[i] is the
    picks hash for draft i.
    """
    n_drafts = len(args_list)
    n_width = len(str(n_drafts))
    results: list = []
    hashes: list = []
    running_totals = [0.0] * len(fac_names)
    t_start = time.monotonic()
    t_last_report = t_start

    for i, args in enumerate(args_list, start=1):
        row, p_hash = _run_one(args)
        results.append(row)
        hashes.append(p_hash)
        for j, v in enumerate(row):
            running_totals[j] += v

        now = time.monotonic()
        if now - t_last_report >= report_interval_s or i == n_drafts:
            elapsed = now - t_start
            rate = i / elapsed if elapsed > 0 else 0.0
            eta = (n_drafts - i) / rate if rate > 0 else 0.0
            rates_str = "  ".join(
                f"{fac_names[j]}={running_totals[j]/i:.4f}"
                for j in range(len(fac_names))
            )
            eta_str = f"{int(eta//60)}m{int(eta%60):02d}s" if eta >= 60 else f"{eta:.0f}s"
            print(
                f"  [{i:{n_width}}/{n_drafts}]  {rates_str}"
                f"  ({rate:.1f} drafts/s, ETA {eta_str})",
                flush=True,
            )
            t_last_report = now

    return results, hashes


def run_tournament(
    factories: dict[str, AgentFactory],
    n_drafts: int,
    league: LeagueConfig,
    players: list[Player],
    eval_season: int,
    n_workers: int = 1,
    base_seed: int = 0,
    report_interval_s: float = 10.0,
) -> tuple[dict, list[dict]]:
    """Run the tournament and return (results_dict, draft_records).

    draft_records is a list of dicts with keys:
      draft_index, slot_assignment (JSON string), picks_hash
    suitable for bulk-inserting into draft_hashes.
    """
    fac_names = list(factories.keys())
    fac_funcs = [factories[n] for n in fac_names]
    n = league.n_teams
    rng = random.Random(base_seed)
    weekly_pts = load_weekly_points(eval_season)

    args_list = []
    slot_assignments = []
    for d in range(n_drafts):
        slots = list(range(len(fac_funcs)))
        rng.shuffle(slots)
        slot_assignment = [slots[i % len(slots)] for i in range(n)]
        rng.shuffle(slot_assignment)
        slot_assignments.append(slot_assignment)
        args_list.append((league, players, fac_funcs, slot_assignment,
                          base_seed + d, base_seed + d * 17, eval_season, weekly_pts))

    if n_workers <= 1:
        results, hashes = _run_sequential(args_list, fac_names, report_interval_s)
    else:
        with mp.Pool(n_workers) as pool:
            raw = pool.map(_run_one, args_list)
        results = [r for r, _ in raw]
        hashes = [h for _, h in raw]

    arr = np.array(results)
    means = arr.mean(axis=0)
    cis = paired_bootstrap_ci(arr, n_resamples=2000)
    stats = {
        fac_names[i]: {
            "mean": float(means[i]),
            "ci_low": float(cis[i, 0]),
            "ci_high": float(cis[i, 1]),
        }
        for i in range(len(fac_names))
    }

    draft_records = [
        {
            "draft_index": d,
            "slot_assignment": json.dumps(slot_assignments[d]),
            "picks_hash": hashes[d],
        }
        for d in range(n_drafts)
    ]

    return stats, draft_records


def replay_draft(
    experiment_config: dict,
    slot_assignment: list[int],
    factories: dict[str, AgentFactory],
    players: list[Player],
    draft_index: int,
) -> list:
    """Replay a single draft and return the list of Pick objects.

    Used by the `show-draft` CLI command to reconstruct pick-by-pick history
    without reading from any stored transcript.
    """
    fac_names = list(factories.keys())
    fac_funcs = [factories[n] for n in fac_names]
    base_seed = experiment_config.get("seed", 0)
    league = LeagueConfig()

    draft_seed = base_seed + draft_index
    agents = [fac_funcs[fac_idx](draft_seed + slot)
              for slot, fac_idx in enumerate(slot_assignment)]
    sim = DraftSimulator(league, players)
    sim.run(agents, seed=draft_seed)
    return getattr(sim, "_last_picks", [])


def paired_bootstrap_ci(arr: np.ndarray, n_resamples: int = 2000, alpha: float = 0.05):
    n_drafts, n_factories = arr.shape
    rng = np.random.default_rng(0)
    boots = np.empty((n_resamples, n_factories))
    for b in range(n_resamples):
        idx = rng.integers(0, n_drafts, size=n_drafts)
        boots[b] = arr[idx].mean(axis=0)
    return np.quantile(boots, [alpha / 2, 1 - alpha / 2], axis=0).T
