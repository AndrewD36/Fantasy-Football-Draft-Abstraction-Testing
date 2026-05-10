import json
import time
from pathlib import Path

import click

from model_infrastructure.agents.adp_agent import ADPAgent
from model_infrastructure.agents.greedy_projection_agent import GreedyProjectionAgent
from model_infrastructure.agents.random_agent import RandomAgent
from model_infrastructure.config import LeagueConfig
from model_infrastructure.data.id_map import reconcile_ids
from model_infrastructure.data.ingest_nflverse import (
    ingest_schedules,
    ingest_seasonal_rosters,
    ingest_snap_counts,
    ingest_weekly,
)
from model_infrastructure.data.ingest_sleeper import ingest_adp, ingest_sleeper_players
from model_infrastructure.data.migrate import migrate as _migrate
from model_infrastructure.data.queries import load_adp_table, load_players_from_db, load_prior_year_points
from model_infrastructure.eval.tournament import run_tournament
from model_infrastructure.eval.validate import (
    check_data_sanity,
    check_draft_invariants,
    check_lineup_optimizer,
    check_schedule_balance,
    check_snake_order,
)
from model_infrastructure.simulator.draft import DraftSimulator
from model_infrastructure.tracking.experiments import record_experiment


@click.group()
def main():
    pass


@main.command()
def migrate():
    """Apply pending schema migrations."""
    click.echo("Running database migrations...")
    _migrate()
    click.echo("Migrations complete.")


@main.command()
@click.option("--years", default="2017-2024")
@click.option("--force", is_flag=True, help="Refetch Sleeper player dump.")
def ingest(years: str, force: bool):
    """Ingest NFL data, Sleeper players, schedules, snap counts, ADP, then reconcile IDs."""
    start, end = (int(x) for x in years.split("-"))
    yr_list = list(range(start, end + 1))
    click.echo(f"Ingesting data for seasons {start}–{end} ({len(yr_list)} years).")

    click.echo("\n[1/7] Fetching Sleeper player roster (canonical IDs, names, positions)...")
    ingest_sleeper_players()
    click.echo("      Done.")

    click.echo(f"\n[2/7] Importing weekly stats from nflverse for {yr_list[0]}–{yr_list[-1]}...")
    ingest_weekly(yr_list)
    click.echo("      Done.")

    click.echo(f"\n[3/7] Importing seasonal rosters (team, age, depth chart, games played)...")
    ingest_seasonal_rosters(yr_list)
    click.echo("      Done.")

    click.echo(f"\n[4/7] Importing snap counts (offense/defense/special teams snaps per week)...")
    ingest_snap_counts(yr_list)
    click.echo("      Done.")

    click.echo(f"\n[5/7] Importing schedules (used to derive bye weeks)...")
    ingest_schedules(yr_list)
    click.echo("      Done.")

    click.echo(f"\n[6/7] Importing ADP for each season from FantasyPros CSVs...")
    click.echo("      Maps player name+position to canonical Sleeper player_id.")
    for yr in yr_list:
        click.echo(f"      Season {yr}...")
        ingest_adp(season=yr)

    click.echo(f"\n[7/7] Reconciling IDs (gsis_id → Sleeper player_id in weekly_stats, snap_counts, player_seasons)...")
    click.echo("      Resolution order: players.gsis_id → manual_id_overrides.csv → name+position heuristic.")
    reconcile_ids()

    click.echo("\nIngest complete.")


@main.command("demo-draft")
@click.option("--season", default=2024, type=int)
def demo_draft(season: int):
    """Run a single draft with mixed agents and pretty-print rosters."""
    click.echo(f"Loading player pool for season {season}...")
    league = LeagueConfig()
    players = load_players_from_db(season=season)
    adp = load_adp_table(season=season)
    prior = load_prior_year_points(season=season - 1)
    click.echo(f"  {len(players)} players loaded, {len(adp)} with ADP, {len(prior)} with prior-year points.")
    click.echo(f"Running snake draft: {league.n_teams} teams, {league.roster.total_rounds} rounds "
               f"({league.roster.total_rounds * league.n_teams} total picks)...")
    click.echo(f"  Agents: 4x GreedyProjection, 8x ADP (seed-varied)\n")
    agents = [
        ADPAgent(adp, seed=0),
        ADPAgent(adp, seed=1),
        GreedyProjectionAgent(prior),
        ADPAgent(adp, seed=3),
        GreedyProjectionAgent(prior),
        ADPAgent(adp, seed=5),
        ADPAgent(adp, seed=6),
        GreedyProjectionAgent(prior),
        ADPAgent(adp, seed=8),
        ADPAgent(adp, seed=9),
        GreedyProjectionAgent(prior),
        ADPAgent(adp, seed=11),
    ]
    sim = DraftSimulator(league, players)
    rosters = sim.run(agents, seed=42)
    for slot, r in enumerate(rosters):
        print(f"Team Roster {slot+1} ({agents[slot].name}):")
        for p in r.all_players():
            print(f"  {p}")


@main.command()
@click.option("--agents", "agent_spec", default="random,adp,greedy",
              help="Comma-separated agent names: random, adp, greedy.")
@click.option("--n", "n_drafts", default=1000, type=int)
@click.option("--seed", "base_seed", default=42, type=int)
@click.option("--draft-season", default=2024, type=int,
              help="Player pool / ADP / prior-points season.")
@click.option("--eval-season", default=2024, type=int,
              help="Season whose actual weekly points drive the H2H stub metric.")
@click.option("--workers", "n_workers", default=1, type=int)
@click.option("--notes", default="", help="Free-form notes attached to the experiment row.")
def tournament(agent_spec: str, n_drafts: int, base_seed: int, draft_season: int,
               eval_season: int, n_workers: int, notes: str):
    """Run a tournament with bootstrap CIs and log to the experiments table."""
    agents = [a.strip() for a in agent_spec.split(",")]
    click.echo(f"Tournament setup:")
    click.echo(f"  Agents      : {', '.join(agents)}")
    click.echo(f"  Drafts      : {n_drafts}")
    click.echo(f"  Seed        : {base_seed}")
    click.echo(f"  Draft season: {draft_season}  (player pool + ADP + prior-year points)")
    click.echo(f"  Eval season : {eval_season}   (actual weekly points for H2H scoring)")
    click.echo(f"  Workers     : {n_workers}")

    click.echo(f"\nLoading player data for season {draft_season}...")
    league = LeagueConfig()
    players = load_players_from_db(season=draft_season)
    adp = load_adp_table(season=draft_season)
    prior = load_prior_year_points(season=draft_season - 1)
    relevant = set(adp.keys()) | set(prior.keys())
    players = [p for p in players if p.player_id in relevant]
    click.echo(f"  {len(players)} players (filtered to those with ADP or prior-year points), "
               f"{len(adp)} ADP entries, {len(prior)} prior-year totals.")

    factories = _build_factories(agents, adp=adp, prior=prior)
    click.echo(f"\nRunning {n_drafts} drafts (each draft = {league.n_teams}-team snake, "
               f"{league.roster.total_rounds} rounds)...")
    click.echo("  Each draft slots agents randomly across teams, scores rosters using actual "
               f"{eval_season} weekly points,")
    click.echo("  then runs a round-robin H2H schedule to produce win rates.")
    click.echo("  Progress reported every 10 seconds — columns are running win-rate means.\n")

    t_start = time.monotonic()
    results = run_tournament(
        factories=factories,
        n_drafts=n_drafts,
        league=league,
        players=players,
        eval_season=eval_season,
        n_workers=n_workers,
        base_seed=base_seed,
        report_interval_s=10.0,
    )
    elapsed = time.monotonic() - t_start
    elapsed_str = f"{int(elapsed//60)}m{int(elapsed%60):02d}s" if elapsed >= 60 else f"{elapsed:.1f}s"

    ordered = sorted(results.items(), key=lambda kv: kv[1]["mean"], reverse=True)
    click.echo(f"\nTournament complete in {elapsed_str}  ({n_drafts} drafts, seed={base_seed}, "
               f"draft_season={draft_season}, eval_season={eval_season})")
    click.echo(f"{'agent':<10} {'mean':>8} {'ci_low':>8} {'ci_high':>8}")
    for name, r in ordered:
        click.echo(f"{name:<10} {r['mean']:>8.4f} {r['ci_low']:>8.4f} {r['ci_high']:>8.4f}")

    click.echo("  (Non-overlapping 95% CIs between agents = statistically significant ordering)\n")
    best_name, best = ordered[0]
    click.echo(f"Best agent: {best_name}  (mean win rate {best['mean']:.4f}, "
               f"95% CI [{best['ci_low']:.4f}, {best['ci_high']:.4f}])")
    click.echo("Logging experiment to database...")
    eid = record_experiment(
        config={
            "agents": agent_spec, "n_drafts": n_drafts, "seed": base_seed,
            "draft_season": draft_season, "eval_season": eval_season,
            "league_hash": league.config_hash(),
        },
        headline={
            "mean": best["mean"],
            "ci_low": best["ci_low"],
            "ci_high": best["ci_high"],
        },
        results=results,
        notes=notes or f"top={best_name}",
    )
    print(f"\nLogged experiment {eid}")


@main.command("validate-sim")
@click.option("--season", default=2024, type=int,
              help="Season used for data-sanity check against the database.")
def validate_sim(season: int):
    """Assert that the draft engine, lineup optimizer, and season sim are correct.

    Runs five independent checks using synthetic data (no DB needed for the first
    four) plus a DB sanity check on real weekly_stats. Any failure is a bug —
    tournament results are meaningless until all checks pass.
    """
    league = LeagueConfig()
    checks = [
        ("Snake pick order",       lambda: check_snake_order(league)),
        ("Draft completeness",     lambda: check_draft_invariants(league)),
        ("Lineup optimizer",       lambda: check_lineup_optimizer(league.roster)),
        ("H2H schedule balance",   lambda: check_schedule_balance(league)),
        (f"Data sanity ({season})", lambda: check_data_sanity(season)),
    ]

    total_failures: list[str] = []
    for label, fn in checks:
        failures = fn()
        status = "OK  " if not failures else "FAIL"
        click.echo(f"  [{status}] {label}")
        for msg in failures:
            click.echo(f"         {msg}")
        total_failures.extend(failures)

    click.echo("")
    if total_failures:
        raise click.ClickException(f"{len(total_failures)} validation failure(s) — see above")
    click.echo("All checks passed. Draft engine and season simulation are correct.")


@main.command("frozen-test")
@click.option("--scenarios", default="frozen_tests/scenarios.json", type=click.Path())
@click.option("--expected", default="frozen_tests/expected_results.json", type=click.Path())
@click.option("--tolerance", default=1e-6, type=float)
def frozen_test(scenarios: str, expected: str, tolerance: float):
    """Run pinned scenarios and assert headline numbers match expected_results.json.

    Frozen tests guard against regressions in agent win rates. Each scenario is a
    fixed tournament run (seed, agents, n_drafts). Expected results are locked after
    a verified run and committed to expected_results.json. Entries with empty dicts
    are treated as 'not yet locked' and skipped without failing.
    """
    click.echo(f"Loading scenarios from {scenarios}...")
    scen_path = Path(scenarios)
    exp_path = Path(expected)
    if not scen_path.exists():
        raise click.ClickException(f"Missing {scen_path}")
    if not exp_path.exists():
        raise click.ClickException(f"Missing {exp_path}")

    cases = json.loads(scen_path.read_text())
    expected_results = json.loads(exp_path.read_text())
    click.echo(f"  {len(cases)} scenarios found, tolerance={tolerance}\n")

    league = LeagueConfig()
    failures: list[str] = []

    for i, case in enumerate(cases, 1):
        name = case["name"]
        exp = expected_results.get(name)
        if exp is None:
            failures.append(f"{name}: no expected entry in {exp_path.name}")
            continue
        if not exp:
            click.echo(f"[{i}/{len(cases)}] {name} — SKIPPED (not yet locked)")
            continue
        click.echo(f"[{i}/{len(cases)}] {name} — running {case['n_drafts']} drafts "
                   f"(agents: {', '.join(case['agents'])}, seed={case['seed']})...")
        adp = load_adp_table(season=case["draft_season"])
        prior = load_prior_year_points(season=case["draft_season"] - 1)
        players = load_players_from_db(season=case["draft_season"])
        relevant = set(adp.keys()) | set(prior.keys())
        players = [p for p in players if p.player_id in relevant]
        factories = _build_factories(case["agents"], adp=adp, prior=prior)
        result = run_tournament(
            factories=factories,
            n_drafts=case["n_drafts"],
            league=league,
            players=players,
            eval_season=case["eval_season"],
            n_workers=1,
            base_seed=case["seed"],
        )
        for agent_name, exp_mean in exp.items():
            got = result[agent_name]["mean"]
            if abs(got - exp_mean) > tolerance:
                failures.append(f"{name}/{agent_name}: got {got:.6f}, expected {exp_mean:.6f}")
                click.echo(f"  FAIL {agent_name}: got {got:.6f}, expected {exp_mean:.6f}")
            else:
                click.echo(f"  OK   {agent_name}: {got:.6f}")

    click.echo("")
    if failures:
        for f in failures:
            click.echo(f"FAIL: {f}")
        raise click.ClickException(f"{len(failures)} frozen-test failure(s)")
    click.echo(f"OK: all {len(cases)} frozen scenarios passed.")


def _build_factories(names: list[str], *, adp: dict[str, float],
                     prior: dict[str, float]) -> dict:
    """Map agent name strings to factory callables."""
    factories: dict = {}
    for raw in names:
        name = raw.strip()
        if name == "random":
            factories[name] = _RandomFactory()
        elif name == "adp":
            factories[name] = _ADPFactory(adp)
        elif name == "greedy":
            factories[name] = _GreedyFactory(prior)
        else:
            raise click.ClickException(f"Unknown agent: {name}")
    return factories


class _RandomFactory:
    def __call__(self, seed: int):
        return RandomAgent(seed=seed)


class _ADPFactory:
    def __init__(self, adp: dict[str, float]):
        self.adp = adp

    def __call__(self, seed: int):
        return ADPAgent(self.adp, seed=seed)


class _GreedyFactory:
    def __init__(self, prior: dict[str, float]):
        self.prior = prior

    def __call__(self, seed: int):
        return GreedyProjectionAgent(self.prior)


if __name__ == "__main__":
    main()
