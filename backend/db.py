"""The UnderCover SQLite database: connection and seeding from data/."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
HERE = Path(__file__).resolve().parent
CLAIM_INSTRUCTIONS = HERE / "claim_instructions.md"
QUEUE_INSTRUCTIONS = HERE / "queue_instructions.md"
DEFAULT_DB = str(ROOT / "backend" / "undercover.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    state TEXT NOT NULL,
    decision TEXT,
    payout REAL,
    reason TEXT,
    policy_section TEXT,
    signed_off INTEGER NOT NULL DEFAULT 0,
    paid REAL
);
CREATE TABLE IF NOT EXISTS records (
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (kind, key)
);
CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    label TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def db_path() -> str:
    """Return the database path, from UNDERCOVER_DB or the default."""
    return os.getenv("UNDERCOVER_DB", DEFAULT_DB)


def connect() -> sqlite3.Connection:
    """Open a connection to the UnderCover database."""
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _load(name: str) -> Any:
    """Read a JSON file from the data directory."""
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _seed_records(
    conn: sqlite3.Connection, kind: str, rows: list[dict[str, Any]], key: str
) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO records (kind, key, data) VALUES (?, ?, ?)",
        [(kind, row[key], json.dumps(row)) for row in rows],
    )


def seed() -> None:
    """Create the schema and load the seed data. Safe to run again."""
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR IGNORE INTO claims (claim_id, data, state)"
            " VALUES (?, ?, 'waiting')",
            [(claim["claim_id"], json.dumps(claim)) for claim in _load("claims.json")],
        )
        _seed_records(conn, "policy", _load("policies.json"), "policy_id")
        _seed_records(conn, "customer", _load("customers.json"), "customer_id")
        _seed_records(conn, "plan", _load("plans.json")["plans"], "plan")
        _seed_records(conn, "handler", _load("handlers.json"), "handler_id")
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('company', ?)",
            (json.dumps(_load("company.json")),),
        )
        for key, path in (
            ("claim_instructions", CLAIM_INSTRUCTIONS),
            ("queue_instructions", QUEUE_INSTRUCTIONS),
        ):
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, path.read_text(encoding="utf-8")),
            )
        conn.commit()
    finally:
        conn.close()
