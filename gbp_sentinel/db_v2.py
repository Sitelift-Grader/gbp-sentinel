"""gbp_sentinel.db_v2 - Relational database layer for GBP SMOKER / Sentinel.

Provides schema initialization, connection management, transactions, and CRUD helpers.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config

_DEFAULT_DB_PATH = str(config.DATA_DIR / "sentinel_v2.db")

_ALLOWED_TABLES = frozenset({
    "businesses",
    "business_snapshots",
    "networks",
    "network_members",
    "relationships",
    "policies",
    "evidence",
    "policy_findings",
    "cases",
    "case_businesses",
    "submissions",
    "outcomes",
    "monitoring_events",
    "review_actions",
    "false_positive_logs",
})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT UNIQUE NOT NULL,
    google_maps_url TEXT,
    name TEXT NOT NULL,
    raw_name TEXT,
    normalized_name TEXT,
    phone TEXT,
    normalized_phone TEXT,
    phone_prefix TEXT,
    domain TEXT,
    canonical_url TEXT,
    address TEXT,
    street TEXT,
    house_number TEXT,
    postal_code TEXT,
    city TEXT,
    country TEXT DEFAULT 'NL',
    category TEXT,
    rating REAL,
    review_count INTEGER DEFAULT 0,
    latitude REAL,
    longitude REAL,
    service_area TEXT,
    description TEXT,
    opening_hours TEXT,
    source_status TEXT DEFAULT 'unverified_historical',
    suspicion_score INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS business_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    snapshot_timestamp TEXT NOT NULL,
    name TEXT,
    address TEXT,
    phone TEXT,
    website TEXT,
    category TEXT,
    status_visible TEXT,
    raw_payload_json TEXT,
    sha256_hash TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(business_id, snapshot_timestamp)
);

CREATE TABLE IF NOT EXISTS networks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    network_code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    network_type TEXT DEFAULT 'MULTI_NICHE_PBX',
    suspicion_score INTEGER DEFAULT 0,
    score_breakdown_json TEXT,
    member_count INTEGER DEFAULT 0,
    address_count INTEGER DEFAULT 0,
    domain_count INTEGER DEFAULT 0,
    phone_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'DISCOVERED',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS network_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id INTEGER NOT NULL REFERENCES networks(id) ON DELETE CASCADE,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    membership_strength REAL DEFAULT 1.0,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(network_id, business_id)
);

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    target_business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    details_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_business_id, target_business_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS policies (
    policy_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    official_source_url TEXT,
    source_date TEXT,
    last_verified TEXT,
    severity TEXT DEFAULT 'HIGH',
    applicable_to_json TEXT,
    examples_json TEXT,
    counter_examples_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_code TEXT UNIQUE NOT NULL,
    case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    network_id INTEGER REFERENCES networks(id) ON DELETE SET NULL,
    evidence_type TEXT NOT NULL,
    source_url TEXT,
    source_type TEXT,
    captured_at TEXT,
    observation TEXT NOT NULL,
    policy_relevance TEXT,
    confidence TEXT DEFAULT 'HIGH',
    screenshot_path TEXT,
    sha256_hash TEXT,
    is_immutable INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS policy_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    policy_id TEXT NOT NULL REFERENCES policies(policy_id) ON DELETE CASCADE,
    status TEXT DEFAULT 'POTENTIAL',
    confidence TEXT DEFAULT 'HIGH',
    observation_text TEXT NOT NULL,
    reasoning_summary TEXT,
    supporting_evidence_ids_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_code TEXT UNIQUE NOT NULL,
    network_id INTEGER REFERENCES networks(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    priority TEXT DEFAULT 'MEDIUM',
    status TEXT DEFAULT 'DISCOVERED',
    reviewer_name TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS case_businesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'SUBJECT',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(case_id, business_id)
);

CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
    submission_type TEXT NOT NULL,
    google_case_id TEXT,
    submission_payload_csv TEXT,
    filled_screenshot_path TEXT,
    result_screenshot_path TEXT,
    status TEXT DEFAULT 'PREPARED',
    submitted_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
    outcome_type TEXT NOT NULL,
    description TEXT,
    verified_at TEXT,
    screenshot_proof_path TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitoring_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    previous_val TEXT,
    new_val TEXT,
    description TEXT,
    occurred_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
    business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
    finding_id INTEGER REFERENCES policy_findings(id) ON DELETE SET NULL,
    reviewer TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS false_positive_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
    finding_id INTEGER REFERENCES policy_findings(id) ON DELETE SET NULL,
    reviewer TEXT NOT NULL,
    dismissal_reason TEXT NOT NULL,
    context_notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_businesses_place_id ON businesses(place_id);
CREATE INDEX IF NOT EXISTS idx_businesses_phone ON businesses(normalized_phone);
CREATE INDEX IF NOT EXISTS idx_businesses_domain ON businesses(domain);
CREATE INDEX IF NOT EXISTS idx_businesses_postal ON businesses(postal_code);
CREATE INDEX IF NOT EXISTS idx_businesses_suspicion ON businesses(suspicion_score);
CREATE INDEX IF NOT EXISTS idx_networks_code ON networks(network_code);
CREATE INDEX IF NOT EXISTS idx_network_members_network ON network_members(network_id);
CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_business_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_business_id);
CREATE INDEX IF NOT EXISTS idx_evidence_business ON evidence(business_id);
CREATE INDEX IF NOT EXISTS idx_evidence_sha ON evidence(sha256_hash);
CREATE INDEX IF NOT EXISTS idx_findings_business ON policy_findings(business_id);
CREATE INDEX IF NOT EXISTS idx_cases_code ON cases(case_code);
"""


def _resolve_db_path(db_path: Optional[str] = None) -> str:
    if db_path is None:
        return os.environ.get("GBP_SENTINEL_DB", _DEFAULT_DB_PATH)
    return str(db_path)


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = _resolve_db_path(db_path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(db_path: Optional[str] = None):
    """Context manager committing on success and rolling back on exception."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize relational schema and indexes."""
    with transaction(db_path) as conn:
        conn.executescript(_SCHEMA)


def insert(table: str, data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """Insert row and return newly created row id."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Disallowed table: {table}")
    if not data:
        raise ValueError("Cannot insert empty dict")

    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"

    with transaction(db_path) as conn:
        cur = conn.execute(sql, list(data.values()))
        return cur.lastrowid


def insert_or_replace(table: str, data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """Insert or replace row and return row id."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Disallowed table: {table}")

    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    sql = f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})"

    with transaction(db_path) as conn:
        cur = conn.execute(sql, list(data.values()))
        return cur.lastrowid


def get(table: str, item_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve single record by primary key."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Disallowed table: {table}")
    sql = f"SELECT * FROM {table} WHERE id = ?"
    with transaction(db_path) as conn:
        cur = conn.execute(sql, (item_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def update(table: str, item_id: int, data: Dict[str, Any], db_path: Optional[str] = None) -> bool:
    """Update fields for row matching id."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Disallowed table: {table}")
    if not data:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in data.keys())
    sql = f"UPDATE {table} SET {set_clause} WHERE id = ?"
    with transaction(db_path) as conn:
        cur = conn.execute(sql, list(data.values()) + [item_id])
        return cur.rowcount > 0


def delete(table: str, item_id: int, db_path: Optional[str] = None) -> bool:
    """Delete record by id."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Disallowed table: {table}")
    sql = f"DELETE FROM {table} WHERE id = ?"
    with transaction(db_path) as conn:
        cur = conn.execute(sql, (item_id,))
        return cur.rowcount > 0


def list_rows(
    table: str,
    where: Optional[str] = None,
    params: tuple = (),
    order_by: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Query rows with parameterized WHERE, ORDER BY, LIMIT, and OFFSET."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Disallowed table: {table}")
    sql = f"SELECT * FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    if offset is not None:
        sql += f" OFFSET {int(offset)}"

    with transaction(db_path) as conn:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def count_rows(table: str, where: Optional[str] = None, params: tuple = (), db_path: Optional[str] = None) -> int:
    """Return count of matching rows."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Disallowed table: {table}")
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    with transaction(db_path) as conn:
        cur = conn.execute(sql, params)
        return cur.fetchone()[0]
