import hashlib
import json
import subprocess
import uuid
from datetime import datetime, timezone

from model_infrastructure.data.db import connect, transaction


def record_experiment(config: dict, headline: dict, results: dict | None = None,
                      notes: str = "", draft_records: list[dict] | None = None) -> str:
    """Insert a row in the experiments table. Returns the experiment_id.

    results: full per-agent dict from run_tournament, e.g.
      {"adp": {"mean": 0.81, "ci_low": 0.80, "ci_high": 0.82}, ...}
    headline: the top agent's stats (for quick queries without parsing results_json).
    draft_records: list of {draft_index, slot_assignment, picks_hash} from run_tournament.
      Stored in draft_hashes table for deterministic replay via `show-draft`.
    """
    eid = str(uuid.uuid4())
    git_sha = _git_sha()
    config_json = json.dumps(config, sort_keys=True, default=str)
    config_hash = hashlib.sha256(config_json.encode()).hexdigest()[:12]
    results_json = json.dumps(results, default=float) if results is not None else None
    now = datetime.now(timezone.utc).isoformat()
    conn = connect()
    with transaction(conn):
        conn.execute(
            """INSERT INTO experiments
               (experiment_id, config_hash, config_json, git_sha,
                started_at, completed_at, headline_metric,
                metric_ci_low, metric_ci_high, notes, results_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                eid, config_hash, config_json, git_sha,
                now, now,
                headline.get("mean"),
                headline.get("ci_low"),
                headline.get("ci_high"),
                notes,
                results_json,
            ),
        )
        if draft_records:
            conn.executemany(
                """INSERT INTO draft_hashes (experiment_id, draft_index, slot_assignment, picks_hash)
                   VALUES (?, ?, ?, ?)""",
                [
                    (eid, r["draft_index"], r["slot_assignment"], r["picks_hash"])
                    for r in draft_records
                ],
            )
    return eid


def list_experiments(limit: int = 50) -> list[dict]:
    conn = connect()
    rows = conn.execute(
        """SELECT experiment_id, config_hash, config_json, git_sha, started_at,
                  headline_metric, metric_ci_low, metric_ci_high, notes
           FROM experiments
           ORDER BY started_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
