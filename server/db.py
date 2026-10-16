import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "retrace.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS assignments (
    id           INTEGER PRIMARY KEY,
    canvas_uid   TEXT NOT NULL UNIQUE,
    course       TEXT,
    course_code  TEXT,
    title        TEXT NOT NULL,
    due_at       TEXT,
    all_day      INTEGER NOT NULL DEFAULT 0,
    url          TEXT,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assignment_changes (
    id            INTEGER PRIMARY KEY,
    assignment_id INTEGER NOT NULL REFERENCES assignments(id),
    field         TEXT NOT NULL,
    old_value     TEXT,
    new_value     TEXT,
    detected_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id         INTEGER PRIMARY KEY,
    type       TEXT NOT NULL,
    title      TEXT NOT NULL,
    source     TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'open',
    due_at     TEXT,
    all_day    INTEGER NOT NULL DEFAULT 0,
    course     TEXT,
    place      TEXT,
    raw_text   TEXT NOT NULL,
    ai_output  TEXT,
    created_at TEXT NOT NULL,
    done_at    TEXT
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = connect()
    conn.executescript(SCHEMA)
    conn.close()