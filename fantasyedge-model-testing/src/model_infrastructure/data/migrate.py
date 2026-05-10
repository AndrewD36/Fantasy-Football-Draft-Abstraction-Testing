# src/fantasyedge/data/migrate.py
import sqlite3
from pathlib import Path
from model_infrastructure.data.db import connect

def migrate(migrations_dir: Path = Path("migrations")) -> None:
    conn = connect()
    conn.execute("CREATE TABLE IF NOT EXISTS schema_versions (version TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_versions")}
    for f in sorted(migrations_dir.glob("*.sql")):
        if f.stem in applied:
            continue
        with open(f) as fh:
            conn.executescript(fh.read())
        conn.execute("INSERT INTO schema_versions (version) VALUES (?)", (f.stem,))
        conn.commit()
        print(f"Applied {f.stem}")