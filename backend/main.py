"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException

from backend import db


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.seed()
    yield


app = FastAPI(title="UnderCover", lifespan=lifespan)


def get_conn() -> Iterator[sqlite3.Connection]:
    """Open a database connection for one request."""
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


def record(conn: sqlite3.Connection, kind: str, key: str) -> dict[str, Any]:
    """Return one seeded record of a kind, or raise 404."""
    row = conn.execute(
        "SELECT data FROM records WHERE kind = ? AND key = ?", (kind, key)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{kind} {key} not found")
    return json.loads(row["data"])


def decision_of(row: sqlite3.Row) -> dict[str, Any] | None:
    """Return the recorded decision for a claim row, or None."""
    if row["decision"] is None:
        return None
    return {
        "decision": row["decision"],
        "payout": row["payout"],
        "reason": row["reason"],
        "policy_section": row["policy_section"],
        "signed_off": bool(row["signed_off"]),
        "paid": row["paid"],
    }


def steps_of(conn: sqlite3.Connection, claim_id: str) -> list[dict[str, str]]:
    """Return a claim's activity steps in order."""
    rows = conn.execute(
        "SELECT label, detail FROM steps WHERE claim_id = ? ORDER BY id", (claim_id,)
    ).fetchall()
    return [{"label": row["label"], "detail": row["detail"]} for row in rows]


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}


@app.get("/api/instructions", operation_id="get_instructions")
def get_instructions(conn: Conn) -> dict[str, str]:
    """Return the agent's instructions, read only."""
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'instructions'"
    ).fetchone()
    return {"instructions": row["value"]}


@app.get("/api/claims", operation_id="list_claims")
def list_claims(conn: Conn) -> list[dict[str, Any]]:
    """Return the claims queue."""
    rows = conn.execute("SELECT data, state FROM claims ORDER BY claim_id").fetchall()
    queue = []
    for row in rows:
        claim = json.loads(row["data"])
        policy = record(conn, "policy", claim["policy_id"])
        customer = record(conn, "customer", claim["customer_id"])
        queue.append(
            {
                "claim_id": claim["claim_id"],
                "customer_name": customer["name"],
                "plan": policy["plan"],
                "claim_type": claim["claim_type"],
                "amount_claimed": claim["amount_claimed"],
                "submitted_on": claim["submitted_on"],
                "state": row["state"],
            }
        )
    return queue


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str, conn: Conn) -> dict[str, Any]:
    """Return one claim in full with its decision and activity."""
    row = conn.execute(
        "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"claim {claim_id} not found")
    claim = json.loads(row["data"])
    policy = record(conn, "policy", claim["policy_id"])
    return {
        **claim,
        "state": row["state"],
        "policy": policy,
        "plan": record(conn, "plan", policy["plan"]),
        "customer": record(conn, "customer", claim["customer_id"]),
        "decision": decision_of(row),
        "steps": steps_of(conn, claim_id),
    }
