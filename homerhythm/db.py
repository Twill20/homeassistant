"""SQLite storage. One file, created on first run."""
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("HOMERHYTHM_DB", ROOT / "data" / "homerhythm.db"))
HOUSE_YAML = Path(os.environ.get("HOMERHYTHM_HOUSE", ROOT / "data" / "house.yaml"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS room (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, floor INT, kind TEXT, zone TEXT,
  robot INT DEFAULT 1, shower INT DEFAULT 1, never_during TEXT DEFAULT '[]',
  prefer_when TEXT, sort INT
);
CREATE TABLE IF NOT EXISTS slot (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, ord INT, noise TEXT, busy INT DEFAULT 0,
  category TEXT, anchor TEXT, offset_from TEXT, offset_minutes INT,
  wd_on INT DEFAULT 1, wd_start TEXT, wd_minutes INT,
  we_on INT DEFAULT 1, we_start TEXT, we_minutes INT
);
CREATE TABLE IF NOT EXISTS task (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, group_label TEXT,
  room_id TEXT, scope TEXT DEFAULT 'room', steps TEXT DEFAULT '[]', minutes INT DEFAULT 10,
  days TEXT DEFAULT '[]', preferred_slots TEXT DEFAULT '[]', robot INT DEFAULT 0,
  category TEXT, note TEXT, active INT DEFAULT 1, sort INT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS day_theme (dow TEXT PRIMARY KEY, theme TEXT);
CREATE TABLE IF NOT EXISTS week (start TEXT PRIMARY KEY, generated_at TEXT);
CREATE TABLE IF NOT EXISTS item (
  id INTEGER PRIMARY KEY AUTOINCREMENT, week_start TEXT NOT NULL, task_id INT NOT NULL,
  date TEXT, slot_id TEXT, status TEXT DEFAULT 'planned', steps_done TEXT DEFAULT '[]',
  moved_count INT DEFAULT 0, orig_date TEXT, orig_slot TEXT, done_at TEXT
);
CREATE INDEX IF NOT EXISTS item_week ON item(week_start, date);
CREATE TABLE IF NOT EXISTS completion (
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INT, task_id INT, room_id TEXT, done_at TEXT
);
CREATE INDEX IF NOT EXISTS completion_task ON completion(task_id, room_id);
CREATE TABLE IF NOT EXISTS move (
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INT, at TEXT,
  from_date TEXT, from_slot TEXT, to_date TEXT, to_slot TEXT, reason TEXT
);
CREATE TABLE IF NOT EXISTS day_state (
  date TEXT PRIMARY KEY, anchors TEXT DEFAULT '{}', closed TEXT DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value TEXT);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path or DB_PATH)
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def is_seeded(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM slot").fetchone()[0] > 0
