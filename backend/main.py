"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from backend import db


class DecisionIn(BaseModel):
    """The agent's decision on a claim."""

    decision: Literal["approve", "decline", "refer"]
    payout: float
    reason: str
    policy_section: str


class PayIn(BaseModel):
    """An amount to pay on an approved claim."""

    amount: float


class StepIn(BaseModel):
    """A step in the agent's work on a claim."""

    label: str
    detail: str


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


def company(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return the company settings."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'company'").fetchone()
    return json.loads(row["value"])


def fetch_claim(conn: sqlite3.Connection, claim_id: str) -> sqlite3.Row:
    """Return a claim row, or raise 404."""
    row = conn.execute(
        "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"claim {claim_id} not found")
    return row


def claim_detail(conn: sqlite3.Connection, claim_id: str) -> dict[str, Any]:
    """Assemble one claim in full with its decision and activity."""
    row = fetch_claim(conn, claim_id)
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
    return claim_detail(conn, claim_id)


@app.post("/api/claims/{claim_id}/start", operation_id="start_claim")
def start_claim(claim_id: str, conn: Conn) -> dict[str, Any]:
    """Mark that the agent has started working the claim."""
    fetch_claim(conn, claim_id)
    conn.execute(
        "UPDATE claims SET state = 'in_progress' WHERE claim_id = ?", (claim_id,)
    )
    conn.commit()
    return claim_detail(conn, claim_id)


@app.post("/api/claims/{claim_id}/steps", operation_id="add_step")
def add_step(claim_id: str, body: StepIn, conn: Conn) -> dict[str, Any]:
    """Append a step to the agent's activity on the claim."""
    fetch_claim(conn, claim_id)
    conn.execute(
        "INSERT INTO steps (claim_id, label, detail) VALUES (?, ?, ?)",
        (claim_id, body.label, body.detail),
    )
    conn.commit()
    return claim_detail(conn, claim_id)


@app.post("/api/claims/{claim_id}/decision", operation_id="decide_claim")
def decide_claim(claim_id: str, body: DecisionIn, conn: Conn) -> dict[str, Any]:
    """Record a decision and move the claim to its resulting state."""
    fetch_claim(conn, claim_id)
    payout = body.payout if body.decision == "approve" else 0.0
    limit = company(conn)["payout_approval_limit"]
    over_limit = body.decision == "approve" and payout > limit
    state = "waiting_for_signoff" if over_limit else "decided"
    conn.execute(
        "UPDATE claims SET decision = ?, payout = ?, reason = ?,"
        " policy_section = ?, state = ? WHERE claim_id = ?",
        (body.decision, payout, body.reason, body.policy_section, state, claim_id),
    )
    conn.commit()
    return claim_detail(conn, claim_id)


@app.post("/api/claims/{claim_id}/signoff", operation_id="sign_off_claim")
def sign_off_claim(claim_id: str, conn: Conn) -> dict[str, Any]:
    """Sign off an over-limit approval, clearing it for payment."""
    row = fetch_claim(conn, claim_id)
    if row["state"] != "waiting_for_signoff":
        raise HTTPException(status_code=409, detail="claim is not waiting for sign-off")
    conn.execute(
        "UPDATE claims SET signed_off = 1, state = 'decided' WHERE claim_id = ?",
        (claim_id,),
    )
    conn.commit()
    return claim_detail(conn, claim_id)


@app.post("/api/claims/{claim_id}/pay", operation_id="pay_claim")
def pay_claim(claim_id: str, body: PayIn, conn: Conn) -> dict[str, Any]:
    """Pay an amount on an approved claim, blocked over the limit until sign-off."""
    row = fetch_claim(conn, claim_id)
    if row["decision"] != "approve":
        raise HTTPException(status_code=409, detail="claim is not approved")
    limit = company(conn)["payout_approval_limit"]
    if body.amount > limit and not row["signed_off"]:
        raise HTTPException(
            status_code=409, detail="payment over the limit needs sign-off"
        )
    conn.execute(
        "UPDATE claims SET paid = ? WHERE claim_id = ?", (body.amount, claim_id)
    )
    conn.commit()
    return claim_detail(conn, claim_id)
