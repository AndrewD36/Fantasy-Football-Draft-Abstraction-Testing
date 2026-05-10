import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path("data/fantasyedge.db")


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path if path is not None else DB_PATH
    p.parent.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(p)
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
