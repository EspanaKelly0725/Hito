"""SQLite persistence. Deliberately dependency-free and schema-on-boot."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from .config import settings

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    client_name TEXT NOT NULL,
    client_email TEXT NOT NULL,
    client_country TEXT,
    currency TEXT DEFAULT 'USD',
    total_amount REAL DEFAULT 0,
    contract_filename TEXT,
    contract_text TEXT,
    contract_summary TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS milestones (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    idx INTEGER,
    title TEXT,
    description TEXT,
    amount REAL,
    currency TEXT DEFAULT 'USD',
    due_date TEXT,
    status TEXT DEFAULT 'pending',          -- pending|delivered|invoiced|overdue|paid|blocked
    evidence TEXT,
    contract_quote TEXT,
    delivered_at TEXT,
    invoice_id TEXT,
    invoice_number TEXT,
    invoice_url TEXT,
    invoiced_at TEXT,
    paid_at TEXT,
    paid_amount REAL,
    FOREIGN KEY (project_id) REFERENCES projects (id)
);

CREATE TABLE IF NOT EXISTS collaborators (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT,
    email TEXT,
    role TEXT,
    pct REAL,
    FOREIGN KEY (project_id) REFERENCES projects (id)
);

CREATE TABLE IF NOT EXISTS dunning (
    id TEXT PRIMARY KEY,
    milestone_id TEXT NOT NULL,
    created_at TEXT,
    days_overdue INTEGER,
    pd REAL,
    band TEXT,
    tone TEXT,
    expected_loss REAL,
    subject TEXT,
    body TEXT,
    offer TEXT,
    factors TEXT,
    status TEXT DEFAULT 'draft',           -- draft|sent|dismissed
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS payouts (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    created_at TEXT,
    status TEXT DEFAULT 'proposed',        -- proposed|approved|sent|failed
    total REAL,
    currency TEXT DEFAULT 'USD',
    batch_id TEXT,
    rationale TEXT,
    approved_at TEXT,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS payout_items (
    id TEXT PRIMARY KEY,
    payout_id TEXT NOT NULL,
    collaborator_id TEXT,
    name TEXT,
    email TEXT,
    role TEXT,
    pct REAL,
    amount REAL,
    needs_approval INTEGER DEFAULT 0,
    approved INTEGER DEFAULT 0,
    status TEXT DEFAULT 'proposed',
    note TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    ts TEXT,
    project_id TEXT,
    actor TEXT,                            -- agent|human|paypal|system
    kind TEXT,
    summary TEXT,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    ts TEXT,
    agent TEXT,
    model TEXT,
    engine TEXT,                           -- claude|rules
    latency_ms INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    verdict TEXT,
    project_id TEXT
);

CREATE TABLE IF NOT EXISTS webhook_log (
    id TEXT PRIMARY KEY,
    ts TEXT,
    event_type TEXT,
    verified TEXT,
    resource_id TEXT,
    raw TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with _lock:
        cur = connect().execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]


def one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = ()) -> None:
    with _lock:
        conn = connect()
        conn.execute(sql, tuple(params))
        conn.commit()


def insert(table: str, row: dict) -> dict:
    cols = ", ".join(row.keys())
    marks = ", ".join("?" for _ in row)
    execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(row.values()))
    return row


def update(table: str, row_id: str, changes: dict) -> None:
    if not changes:
        return
    sets = ", ".join(f"{k} = ?" for k in changes)
    execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*changes.values(), row_id])


def log_event(kind: str, summary: str, *, actor: str = "agent",
              project_id: str | None = None, payload: dict | None = None) -> dict:
    row = {
        "id": new_id("ev"),
        "ts": now(),
        "project_id": project_id,
        "actor": actor,
        "kind": kind,
        "summary": summary,
        "payload": json.dumps(payload or {}, ensure_ascii=False, default=str),
    }
    insert("events", row)
    return row


def log_agent_run(agent: str, result: dict, *, project_id: str | None = None,
                  verdict: str = "") -> None:
    meta = result.get("_meta", {}) if isinstance(result, dict) else {}
    insert("agent_runs", {
        "id": new_id("run"),
        "ts": now(),
        "agent": agent,
        "model": meta.get("model", ""),
        "engine": meta.get("engine", "rules"),
        "latency_ms": int(meta.get("latency_ms", 0)),
        "input_tokens": int(meta.get("input_tokens", 0)),
        "output_tokens": int(meta.get("output_tokens", 0)),
        "cost_usd": float(meta.get("cost_usd", 0.0)),
        "verdict": verdict,
        "project_id": project_id,
    })


def reset() -> None:
    """Wipe every table (used by /api/demo/reset and the test suite)."""
    with _lock:
        conn = connect()
        for table in ("payout_items", "payouts", "dunning", "collaborators",
                      "milestones", "projects", "events", "agent_runs", "webhook_log"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
