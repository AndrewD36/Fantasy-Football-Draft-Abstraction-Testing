# FantasyEdge — model testing

## Setup

```bash
uv sync --all-extras
uv run pre-commit install
```

## Phase 0 acceptance flow

```bash
# 1. Database
uv run fantasyedge migrate

# 2. Data ingestion (downloads ~1-2 minutes the first time)
uv run fantasyedge ingest --years 2012-2024

# 3. Sanity check
uv run fantasyedge demo-draft

# 4. Tournament with bootstrap CIs (logged to experiments table)
uv run fantasyedge tournament --agents random,adp,greedy --n 1000 --seed 42

# 5. Frozen regression check
uv run fantasyedge frozen-test
```

Phase 0 is "done" when the tournament prints `greedy > adp > random` with non-overlapping 95% CIs and completes in <10 minutes on a laptop.

## Development

```bash
uv run pytest                              # all tests
uv run pytest tests/test_domain/ -v        # subset
uv run ruff check src tests                # lint
uv run ruff format src tests               # format
uv run pyright src                         # type check
```

## ADP for Phase 0

Manually download FantasyPros' aggregated ADP CSV to `data/raw/fp_adp_<season>.csv`:
- https://www.fantasypros.com/nfl/adp/half-point-ppr-overall.php

Commit it (it's small). Phase 4+ replaces this with scraped Sleeper public drafts.

## Layout

- `src/model_infrastructure/` — all source
- `tests/` — mirrors src layout (`test_domain/`, `test_agents/`, ...)
- `migrations/` — numbered SQL migrations
- `frozen_tests/` — pinned scenarios + locked headline numbers
- `data/` — SQLite + raw cached pulls (mostly gitignored)
