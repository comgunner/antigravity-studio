import sqlite3
import time
import os
import tempfile
from pathlib import Path

# Multi-platform temporary directory for the database
DEFAULT_DB_PATH = Path(tempfile.gettempdir()) / "antigravity_auth_cooldown.db"
AUTH_DB_PATH = os.getenv("AUTH_DB_PATH", str(DEFAULT_DB_PATH))

def get_db_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS cooldowns (account TEXT PRIMARY KEY, last_gen_ts INTEGER)")
    return conn

def set_cooldown(account: str):
    """Sets the current timestamp as the last generation for the account."""
    ts = int(time.time())
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO cooldowns (account, last_gen_ts) VALUES (?, ?)", (account, ts))

def get_remaining_cooldown(account: str, cooldown_duration: int = 300) -> int:
    """Returns the remaining seconds of cooldown for the account."""
    with get_db_connection() as conn:
        row = conn.execute("SELECT last_gen_ts FROM cooldowns WHERE account = ?", (account,)).fetchone()
        if not row:
            return 0
        elapsed = int(time.time()) - row[0]
        remaining = cooldown_duration - elapsed
        return max(0, remaining)
