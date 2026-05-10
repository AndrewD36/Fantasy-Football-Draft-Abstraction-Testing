import csv
from pathlib import Path

from model_infrastructure.data.db import connect, transaction

OVERRIDES_PATH = Path("data/raw/manual_id_overrides.csv")


def load_overrides() -> dict[str, str]:
    """gsis_id -> sleeper_player_id from the committed overrides CSV."""
    if not OVERRIDES_PATH.exists():
        return {}
    out: dict[str, str] = {}
    with open(OVERRIDES_PATH, newline="") as fh:
        for row in csv.DictReader(fh):
            gsis = (row.get("gsis_id") or "").strip()
            sleeper = (row.get("sleeper_player_id") or "").strip()
            if gsis and sleeper:
                out[gsis] = sleeper
    return out


def reconcile_ids() -> dict[str, list[str]]:
    """Rewrite weekly_stats / snap_counts player_id from gsis_id to canonical Sleeper player_id.

    Resolution order:
      1. players.gsis_id (Sleeper-provided cross-reference) - the easy case.
      2. data/raw/manual_id_overrides.csv - hand-reconciled difficult cases.
      3. name + position match against nfl_data_py.import_players() metadata - heuristic.
    Anything still unmatched is reported back so a human can add overrides.

    Returns: {"matched_via_gsis": [...], "matched_via_overrides": [...],
              "matched_via_name": [...], "unmatched": [gsis_id, ...]}.
    """
    conn = connect()

    sleeper_by_gsis: dict[str, str] = {
        r["gsis_id"]: r["player_id"]
        for r in conn.execute("SELECT player_id, gsis_id FROM players WHERE gsis_id IS NOT NULL")
    }

    sleeper_by_name_pos: dict[tuple[str, str], str] = {}
    name_pos_dupes: set[tuple[str, str]] = set()
    for r in conn.execute("SELECT player_id, full_name, position FROM players"):
        key = (_normalize_name(r["full_name"]), r["position"])
        if key in sleeper_by_name_pos:
            name_pos_dupes.add(key)
        sleeper_by_name_pos[key] = r["player_id"]
    for k in name_pos_dupes:
        sleeper_by_name_pos.pop(k, None)

    overrides = load_overrides()

    unmatched_gsis = [
        r["gsis_id"]
        for r in conn.execute(
            """SELECT DISTINCT player_id AS gsis_id
               FROM weekly_stats
               WHERE player_id NOT IN (SELECT player_id FROM players)"""
        )
    ]

    name_pos_lookup = _fetch_nflverse_player_metadata() if unmatched_gsis else {}

    via_gsis: list[tuple[str, str]] = []
    via_overrides: list[tuple[str, str]] = []
    via_name: list[tuple[str, str]] = []
    unmatched: list[str] = []

    for gsis in unmatched_gsis:
        if gsis in sleeper_by_gsis:
            via_gsis.append((gsis, sleeper_by_gsis[gsis]))
        elif gsis in overrides:
            via_overrides.append((gsis, overrides[gsis]))
        else:
            meta = name_pos_lookup.get(gsis)
            if meta is None:
                unmatched.append(gsis)
                continue
            key = (_normalize_name(meta[0]), meta[1])
            if key in sleeper_by_name_pos:
                via_name.append((gsis, sleeper_by_name_pos[key]))
            else:
                unmatched.append(gsis)

    rewrites = via_gsis + via_overrides + via_name
    with transaction(conn):
        for gsis, sleeper in rewrites:
            conn.execute(
                "UPDATE weekly_stats SET player_id = ? WHERE player_id = ?", (sleeper, gsis)
            )
            conn.execute(
                "UPDATE snap_counts SET player_id = ? WHERE player_id = ?", (sleeper, gsis)
            )
            conn.execute(
                "UPDATE player_seasons SET player_id = ? WHERE player_id = ?", (sleeper, gsis)
            )

    print(
        f"Reconciled: {len(via_gsis)} via gsis, {len(via_overrides)} via overrides, "
        f"{len(via_name)} via name+pos. {len(unmatched)} unmatched."
    )
    if unmatched:
        print("First 20 unmatched gsis_ids (add to manual_id_overrides.csv if relevant):")
        for g in unmatched[:20]:
            print(f"  {g}")

    return {
        "matched_via_gsis": [g for g, _ in via_gsis],
        "matched_via_overrides": [g for g, _ in via_overrides],
        "matched_via_name": [g for g, _ in via_name],
        "unmatched": unmatched,
    }


def _normalize_name(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


def _fetch_nflverse_player_metadata() -> dict[str, tuple[str, str]]:
    """gsis_id -> (display_name, position) from nfl_data_py.import_players().
    Imported lazily because nfl-data-py is an optional extra."""
    try:
        import nfl_data_py as nfl
    except ImportError:
        return {}
    df = nfl.import_players()
    out: dict[str, tuple[str, str]] = {}
    name_col = "display_name" if "display_name" in df.columns else "football_name"
    for row in df.itertuples():
        gsis = getattr(row, "gsis_id", None)
        if not gsis:
            continue
        pos = getattr(row, "position", None)
        if pos == "DEF":
            pos = "DST"
        if pos not in ("QB", "RB", "WR", "TE", "K", "DST"):
            continue
        nm = getattr(row, name_col, None)
        if not nm:
            continue
        out[gsis] = (nm, pos)
    return out
