"""SQLite database for tracking processed emails to prevent duplicates."""
import sqlite3
from config.settings import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id TEXT UNIQUE NOT NULL,
                subject TEXT,
                sender TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                forwarded INTEGER DEFAULT 0
            )
        """)


def is_processed(entry_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM processed_emails WHERE entry_id = ?", (entry_id,)).fetchone()
    return row is not None


def mark_processed(entry_id: str, subject: str, sender: str, forwarded: bool = True):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_emails (entry_id, subject, sender, forwarded) VALUES (?, ?, ?, ?)",
            (entry_id, subject, sender, int(forwarded)),
        )
