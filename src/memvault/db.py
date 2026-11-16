"""SQLite schema and connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'manual',   -- manual | claude | chatgpt | mcp | chat
    tags        TEXT NOT NULL DEFAULT '',         -- comma separated
    created_at  TEXT NOT NULL,
    saved_at    TEXT NOT NULL,
    archived_at TEXT                              -- NULL = active
);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    position         INTEGER NOT NULL,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    created_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, position);

CREATE TABLE IF NOT EXISTS chunks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    text             TEXT NOT NULL,
    embedding        BLOB,          -- float32 vector, NULL if no embedder
    model            TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_conv ON chunks(conversation_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id', tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
"""


def default_db_path() -> Path:
    return Path.home() / ".memvault" / "vault.db"


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path).expanduser() if path else default_db_path()
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    # async servers create the vault in one thread and use it from the event loop thread
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(conversations)")}
    if "archived_at" not in cols:  # vaults created before v0.2
        conn.execute("ALTER TABLE conversations ADD COLUMN archived_at TEXT")
        conn.commit()
