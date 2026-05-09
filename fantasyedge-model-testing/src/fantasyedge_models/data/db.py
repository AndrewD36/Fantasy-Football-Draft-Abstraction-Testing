import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("data/fantasyedge.db")

def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise