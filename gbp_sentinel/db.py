import sqlite3
import json
from datetime import datetime
from . import config

DB_PATH = config.DB_PATH

def _get_connection():
    """Create and return a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database by creating tables if they don't exist."""
    conn = _get_connection()
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS targets (
                    name TEXT PRIMARY KEY,
                    kvk TEXT,
                    website TEXT,
                    hq_address TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_name TEXT,
                    data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (target_name) REFERENCES targets(name) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_name TEXT,
                    case_id TEXT,
                    email TEXT,
                    dossier_path TEXT,
                    filled_screenshot TEXT,
                    result_screenshot TEXT,
                    status TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (target_name) REFERENCES targets(name) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS case_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
    finally:
        conn.close()

def save_target(name, kvk='', website='', hq_address=''):
    """Insert or replace a target record."""
    conn = _get_connection()
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO targets (name, kvk, website, hq_address) VALUES (?, ?, ?, ?)",
                (name, kvk, website, hq_address)
            )
    finally:
        conn.close()

def get_target(name):
    """Retrieve a target by name, return dict or None."""
    conn = _get_connection()
    try:
        row = conn.execute("SELECT * FROM targets WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def save_location(target_name, loc_dict):
    """Insert a single location for a target (stored as JSON)."""
    conn = _get_connection()
    try:
        with conn:
            conn.execute(
                "INSERT INTO locations (target_name, data) VALUES (?, ?)",
                (target_name, json.dumps(loc_dict))
            )
    finally:
        conn.close()

def save_locations(target_name, loc_list):
    """Insert multiple locations for a target."""
    conn = _get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM locations WHERE target_name = ?", (target_name,))
            for loc in loc_list:
                conn.execute(
                    "INSERT INTO locations (target_name, data) VALUES (?, ?)",
                    (target_name, json.dumps(loc))
                )
    finally:
        conn.close()

def get_locations(target_name):
    """Retrieve all locations for a target as list of dicts."""
    conn = _get_connection()
    try:
        rows = conn.execute("SELECT data FROM locations WHERE target_name = ?", (target_name,)).fetchall()
        return [json.loads(row['data']) for row in rows]
    finally:
        conn.close()

def save_submission(target_name, case_id, email, dossier_path, filled_screenshot, result_screenshot, status='submitted'):
    """Insert a new submission record."""
    conn = _get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO submissions
                    (target_name, case_id, email, dossier_path, filled_screenshot, result_screenshot, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (target_name, case_id, email, dossier_path, filled_screenshot, result_screenshot, status, datetime.now().isoformat())
            )
    finally:
        conn.close()

def list_targets():
    """Return list of all targets as dicts."""
    conn = _get_connection()
    try:
        rows = conn.execute("SELECT * FROM targets ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def list_submissions():
    """Return list of all submissions as dicts."""
    conn = _get_connection()
    try:
        rows = conn.execute("SELECT * FROM submissions ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def update_submission_status(case_id, status):
    """Record a manually verified outcome for an existing Google case."""
    conn = _get_connection()
    try:
        with conn:
            cursor = conn.execute(
                "UPDATE submissions SET status = ? WHERE case_id = ?",
                (status, case_id),
            )
        return cursor.rowcount
    finally:
        conn.close()

def submission_status_summary():
    """Return case counts grouped by their current lifecycle status."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT COALESCE(status, 'unknown') AS status, COUNT(*) AS total "
            "FROM submissions GROUP BY status ORDER BY status"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def save_case_event(case_id, event_type, details=""):
    """Record a verified email, response, or manual review event for a case."""
    conn = _get_connection()
    try:
        with conn:
            conn.execute(
                "INSERT INTO case_events (case_id, event_type, details, created_at) VALUES (?, ?, ?, ?)",
                (case_id, event_type, details, datetime.now().isoformat()),
            )
    finally:
        conn.close()
