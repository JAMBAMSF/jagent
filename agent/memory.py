from __future__ import annotations
import os, sqlite3, json, logging, time
from typing import Optional, Any, Tuple, List
from agent.config import DB_PATH, SEED_FILE

DEFAULT_DB = DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, risk_tolerance TEXT);
CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, key TEXT, value TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS portfolios (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, payload TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS price_cache (symbol TEXT, date TEXT, price REAL, ts REAL);
CREATE TABLE IF NOT EXISTS counterparties (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  counterparty TEXT,
  first_seen REAL,
  last_seen REAL,
  times_used INTEGER DEFAULT 0,
  UNIQUE(user_id, counterparty)
);
"""

def _init_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript(SCHEMA)

def _seed_counterparties_if_empty(conn: sqlite3.Connection) -> None:
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='counterparties';")
        if not cur.fetchone():
            return  
        cur.execute("SELECT COUNT(1) FROM counterparties;")
        (n,) = cur.fetchone()
        if n > 0:
            return
        if not SEED_FILE or not os.path.exists(SEED_FILE):
            return
        with open(SEED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        names = [ (c.get("name","").strip()) for c in data.get("counterparties", []) if c.get("name") ]
        if not names:
            return
        now = time.time()
        rows = [(None, name, now, now, 0) for name in names]  
        cur.executemany(
            "INSERT INTO counterparties(user_id, counterparty, first_seen, last_seen, times_used) VALUES (?, ?, ?, ?, ?)",
            rows
        )
        conn.commit()
        logging.info("Seeded %d global counterparties from %s", len(rows), SEED_FILE)
    except Exception:
        logging.exception("Seeding counterparties failed; continuing")

def connect(db_path: str = DEFAULT_DB) -> sqlite3.Connection:

    dirpath = os.path.dirname(db_path)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)

    _init_schema(conn)
    _seed_counterparties_if_empty(conn)
    return conn


def upsert_user(conn: sqlite3.Connection, name: str, risk_tolerance: Optional[str] = None) -> int:
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users(name, risk_tolerance) VALUES(?, ?)", (name, risk_tolerance))
    conn.commit()
    cur.execute("SELECT id FROM users WHERE name = ?", (name,))
    uid = int(cur.fetchone()[0])
    if risk_tolerance is not None:
        conn.execute("UPDATE users SET risk_tolerance=? WHERE id=?", (risk_tolerance, uid))
        conn.commit()
    return uid

def _counterparty_name_col(conn) -> str:
    """Return the actual column name used to store the counterparty name."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(counterparties)")
    cols = [row[1] for row in cur.fetchall()]  # row = (cid, name, type, notnull, dflt, pk)
    # priority order of likely column names
    priority = ["name", "counterparty", "payee", "payee_name", "counterparty_name", "label", "title"]
    for p in priority:
        for c in cols:
            if c.lower() == p:
                return c
    raise RuntimeError(f"Could not find a counterparty name column. Found columns: {cols}")

def rename_counterparty(
    conn: sqlite3.Connection, user_id: int, old_name: str, new_name: str
) -> str:
    """
    Rename a counterparty for a user (case-insensitive).

    Behavior:
      1) If a per-user row matches old_name, rename it; if new_name already exists for that user, merge (delete old).
      2) Else, if a GLOBAL row (user_id IS NULL) matches old_name, promote it to this user_id with the new name.
         If new_name already exists for the user, delete the global old (merge).
      3) After a successful rename/merge from a GLOBAL row, remove any remaining GLOBAL rows with the same old_name.
    Returns: 'renamed' | 'merged' | 'not_found'
    """
    old = (old_name or "").strip()
    new = (new_name or "").strip()
    if not old or not new:
        return "not_found"

    col = _counterparty_name_col(conn)
    cur = conn.cursor()

    cur.execute(
        f"SELECT id FROM counterparties WHERE user_id=? AND LOWER({col})=LOWER(?)",
        (user_id, old),
    )
    row_user_old = cur.fetchone()

    cur.execute(
        f"SELECT id FROM counterparties WHERE user_id=? AND LOWER({col})=LOWER(?)",
        (user_id, new),
    )
    row_user_new = cur.fetchone()

    if row_user_old:
        if row_user_new:
            cur.execute("DELETE FROM counterparties WHERE id=?", (row_user_old[0],))
            conn.commit()
            return "merged"
        cur.execute(
            f"UPDATE counterparties SET {col}=? WHERE id=?",
            (new, row_user_old[0]),
        )
        conn.commit()
        return "renamed"

    cur.execute(
        f"SELECT id FROM counterparties WHERE user_id IS NULL AND LOWER({col})=LOWER(?)",
        (old,),
    )
    row_global_old = cur.fetchone()
    if not row_global_old:
        return "not_found"

    if row_user_new:
        cur.execute(
            f"DELETE FROM counterparties WHERE user_id IS NULL AND LOWER({col})=LOWER(?)",
            (old,),
        )
        conn.commit()
        return "merged"

    cur.execute(
        f"UPDATE counterparties SET user_id=?, {col}=? WHERE id=?",
        (user_id, new, row_global_old[0]),
    )
    cur.execute(
        f"DELETE FROM counterparties WHERE user_id IS NULL AND LOWER({col})=LOWER(?)",
        (old,),
    )
    conn.commit()
    return "renamed"

def set_memory(conn: sqlite3.Connection, uid: int, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO memories(user_id, key, value, ts) VALUES(?,?,?,?)",
        (uid, key, json.dumps(value), time.time())
    )
    conn.commit()

def get_user(conn: sqlite3.Connection, name: str) -> Optional[Tuple[int, str]]:
    cur = conn.cursor()
    cur.execute("SELECT id, risk_tolerance FROM users WHERE name=?", (name,))
    row = cur.fetchone()
    if not row:
        return None
    return int(row[0]), row[1]

def set_risk_tolerance(conn: sqlite3.Connection, uid: int, tol: str) -> None:
    conn.execute("UPDATE users SET risk_tolerance=? WHERE id=?", (tol, uid))
    conn.commit()

def save_portfolio(conn: sqlite3.Connection, uid: int, payload: dict) -> None:
    conn.execute(
        "INSERT INTO portfolios(user_id, payload, ts) VALUES(?,?,?)",
        (uid, json.dumps(payload), time.time())
    )
    conn.commit()

def forget_user(conn: sqlite3.Connection, name: str) -> None:
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE name=?", (name,))
    row = cur.fetchone()
    if not row:
        return
    uid = int(row[0])
    conn.execute("DELETE FROM memories WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM portfolios WHERE user_id=?", (uid,))
    # keep the user row but reset to a neutral tolerance
    conn.execute("UPDATE users SET risk_tolerance=? WHERE id=?", ("moderate", uid))
    conn.commit()

def list_counterparties(conn: sqlite3.Connection, uid: int) -> List[str]:

    cur = conn.cursor()
    cur.execute(
        "SELECT counterparty FROM counterparties WHERE user_id=? OR user_id IS NULL",
        (uid,)
    )
    names = [r[0] for r in cur.fetchall()]

    seen = set()
    out = []
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            out.append(n)
    return sorted(out)

def upsert_counterparty(conn: sqlite3.Connection, uid: int, name: str) -> None:
    ts = time.time()
    conn.execute(
        """
        INSERT INTO counterparties(user_id, counterparty, first_seen, last_seen, times_used)
        VALUES(?, ?, ?, ?, 1)
        ON CONFLICT(user_id, counterparty)
        DO UPDATE SET last_seen=excluded.last_seen, times_used=times_used+1
        """,
        (uid, name.strip(), ts, ts),
    )
    conn.commit()