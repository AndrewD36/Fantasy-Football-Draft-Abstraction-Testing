import json
import re
from datetime import date
from pathlib import Path

import polars as pl
import requests

from model_infrastructure.data.db import connect, transaction

SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
CACHE = Path("data/raw/sleeper_players.json")


def fetch_sleeper_players(force: bool = False) -> dict:
    if CACHE.exists() and not force:
        return json.loads(CACHE.read_text())
    resp = requests.get(SLEEPER_PLAYERS_URL, timeout=30)
    resp.raise_for_status()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(resp.text)
    return resp.json()


def ingest_sleeper_players(force: bool = False) -> None:
    data = fetch_sleeper_players(force=force)
    rows = []
    for sleeper_id, p in data.items():
        if p.get("position") not in ("QB", "RB", "WR", "TE", "K", "DEF"):
            continue
        rows.append({
            "player_id": sleeper_id,                # canonical
            "sleeper_id": sleeper_id,
            "gsis_id": p.get("gsis_id"),
            "pfr_id": p.get("pfr_id"),
            "espn_id": _stringify(p.get("espn_id")),
            "yahoo_id": _stringify(p.get("yahoo_id")),
            "full_name": p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "position": "DST" if p.get("position") == "DEF" else p["position"],
            "birthdate": p.get("birth_date"),
            "draft_year": None,
            "draft_pick": None,
            "college": p.get("college"),
            "nfl_team": p.get("team"),  # team abbreviation (e.g. "SF"), key for DST->player_id mapping
        })
    conn = connect()
    with transaction(conn):
        conn.executemany(
            """INSERT OR REPLACE INTO players
               (player_id, sleeper_id, gsis_id, pfr_id, espn_id, yahoo_id, full_name, position,
                birthdate, draft_year, draft_pick, college, nfl_team)
               VALUES (:player_id, :sleeper_id, :gsis_id, :pfr_id, :espn_id, :yahoo_id,
                       :full_name, :position, :birthdate, :draft_year, :draft_pick, :college,
                       :nfl_team)""",
            rows,
        )


def ingest_adp(season: int, source: str = "fantasypros",
               csv_path: Path | None = None) -> None:
    """Load ADP from a manually-downloaded CSV into the adp table.

    Looks for the file in order:
      1. csv_path if provided
      2. data/raw/fp_adp_<season>.csv  (simple canonical name)
      3. data/raw/FantasyPros/FantasyPros_<season>_Overall_ADP_Rankings*.csv  (FantasyPros download)
    Required columns: a player name column ('Player' or 'name'), a position column,
    and an ADP column ('AVG' for FantasyPros, or 'adp_overall').
    Maps player name+position to canonical Sleeper player_id at load time.
    """
    path = csv_path or _find_adp_csv(season)
    if path is None or not path.exists():
        print(f"ADP file not found for season {season} - skipping. "
              f"Place at data/raw/fp_adp_{season}.csv or "
              f"data/raw/FantasyPros/FantasyPros_{season}_Overall_ADP_Rankings.csv")
        return

    df = pl.read_csv(path, truncate_ragged_lines=True, infer_schema_length=0)
    name_col = _pick_col(df, ["Player", "player", "name", "Name"])
    pos_col = _pick_col(df, ["POS", "Pos", "position", "Position"])
    adp_col = _pick_col(df, ["AVG", "ADP", "adp", "adp_overall"])
    if name_col is None or pos_col is None or adp_col is None:
        raise ValueError(
            f"ADP CSV missing required columns. Got: {df.columns}"
        )

    conn = connect()
    name_pos_to_id: dict[tuple[str, str], str] = {}
    for r in conn.execute("SELECT player_id, full_name, position FROM players"):
        key = (_normalize(r["full_name"]), r["position"])
        name_pos_to_id.setdefault(key, r["player_id"])

    snapshot = date.today().isoformat()
    rows = []
    unmatched: list[str] = []
    for row in df.iter_rows(named=True):
        raw_pos = str(row[pos_col]).strip()
        pos = "".join(c for c in raw_pos if c.isalpha()).upper() or raw_pos
        pos = "DST" if pos in ("DEF", "DST") else pos
        name = str(row[name_col]).strip()
        key = (_normalize(name), pos)
        pid = name_pos_to_id.get(key)
        if pid is None:
            unmatched.append(f"{name} ({pos})")
            continue
        try:
            adp_val = float(str(row[adp_col]).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
        rows.append({
            "player_id": pid,
            "season": season,
            "source": source,
            "snapshot_date": snapshot,
            "adp_overall": adp_val,
            "adp_position": None,
            "n_drafts": None,
        })

    with transaction(conn):
        conn.executemany(
            """INSERT OR REPLACE INTO adp
               (player_id, season, source, snapshot_date, adp_overall, adp_position, n_drafts)
               VALUES (:player_id, :season, :source, :snapshot_date,
                       :adp_overall, :adp_position, :n_drafts)""",
            rows,
        )

    print(f"ADP ingested: {len(rows)} matched, {len(unmatched)} unmatched.")
    if unmatched:
        print("First 10 unmatched ADP entries:")
        for u in unmatched[:10]:
            print(f"  {u}")


def _pick_col(df: pl.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


_SUFFIX_RE = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$", re.IGNORECASE)


def _normalize(name: str) -> str:
    name = _SUFFIX_RE.sub("", name).strip()
    return "".join(c for c in name.lower() if c.isalnum())


def _find_adp_csv(season: int) -> Path | None:
    """Return the first ADP CSV found for the given season, or None."""
    simple = Path(f"data/raw/fp_adp_{season}.csv")
    if simple.exists():
        return simple
    fp_dir = Path("data/raw/FantasyPros")
    if fp_dir.is_dir():
        # Match FantasyPros_2024_Overall_ADP_Rankings.csv (and variants with suffixes)
        matches = sorted(fp_dir.glob(f"FantasyPros_{season}_Overall_ADP_Rankings*.csv"))
        if matches:
            return matches[0]
    return None


def _stringify(v: object) -> str | None:
    if v is None:
        return None
    return str(v)
