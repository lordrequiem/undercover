"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from backend import db, handbook


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


class RunIn(BaseModel):
    """How many waiting claims a run should work, or null for all of them."""

    limit: int | None


class PlanIn(BaseModel):
    """The ordered claim ids that make up a run's to-do list."""

    claim_ids: list[str]


class ItemIn(BaseModel):
    """The status and one-line note for one item on a run's to-do list."""

    status: Literal["to_do", "in_progress", "done", "for_handler"]
    note: str


class FinishIn(BaseModel):
    """The summary written when a run finishes."""

    summary: str


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


def setting(conn: sqlite3.Connection, key: str) -> str:
    """Return a stored setting's text value."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"]


@app.get("/api/instructions", operation_id="get_instructions")
def get_instructions(conn: Conn) -> dict[str, str]:
    """Return the agent's instructions for the queue and for a claim, read only."""
    return {
        "queue": setting(conn, "queue_instructions"),
        "claim": setting(conn, "claim_instructions"),
    }


@app.get("/api/handbook", operation_id="list_handbook")
def list_handbook() -> list[dict[str, str]]:
    """List every section of the policy wording and the claims manual, in order."""
    return handbook.index()


@app.get("/api/handbook/{section_id:path}", operation_id="read_handbook")
def read_handbook(section_id: str) -> dict[str, Any]:
    """Return one handbook section's full text, or 404 if there is no such id."""
    found = handbook.section(section_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"section {section_id} not found")
    return found


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
    row = fetch_claim(conn, claim_id)
    if row["decision"] is not None:
        raise HTTPException(status_code=409, detail="claim already has a decision")
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


@app.post("/api/claims/{claim_id}/requeue", operation_id="requeue_claim")
def requeue_claim(claim_id: str, conn: Conn) -> dict[str, Any]:
    """Return a claim to waiting to be worked again, unless it is already decided."""
    row = fetch_claim(conn, claim_id)
    if row["decision"] is not None:
        raise HTTPException(status_code=409, detail="claim already has a decision")
    conn.execute("UPDATE claims SET state = 'waiting' WHERE claim_id = ?", (claim_id,))
    conn.commit()
    return claim_detail(conn, claim_id)


@app.post("/api/claims/{claim_id}/for_handler", operation_id="hand_to_handler")
def hand_to_handler(claim_id: str, conn: Conn) -> dict[str, Any]:
    """Leave a claim for a handler to work by hand."""
    fetch_claim(conn, claim_id)
    conn.execute(
        "UPDATE claims SET state = 'for_handler' WHERE claim_id = ?", (claim_id,)
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


def fetch_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row:
    """Return a run row, or raise 404."""
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return row


def run_view(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    """Assemble a run with its to-do list in order."""
    items = conn.execute(
        "SELECT claim_id, status, note FROM run_items"
        " WHERE run_id = ? ORDER BY ordinal",
        (row["run_id"],),
    ).fetchall()
    return {
        "run_id": row["run_id"],
        "limit": row["limit_count"],
        "finished": bool(row["finished"]),
        "summary": row["summary"],
        "items": [dict(item) for item in items],
    }


@app.post("/api/runs", operation_id="open_run")
def open_run(body: RunIn, conn: Conn) -> dict[str, Any]:
    """Open a run over the first `limit` waiting claims, or all when null."""
    cursor = conn.execute("INSERT INTO runs (limit_count) VALUES (?)", (body.limit,))
    conn.commit()
    return {"run_id": cursor.lastrowid}


@app.post("/api/runs/{run_id}/plan", operation_id="plan_run")
def plan_run(run_id: int, body: PlanIn, conn: Conn) -> dict[str, Any]:
    """Write the run's ordered to-do list, each item to do."""
    fetch_run(conn, run_id)
    conn.execute("DELETE FROM run_items WHERE run_id = ?", (run_id,))
    conn.executemany(
        "INSERT INTO run_items (run_id, ordinal, claim_id) VALUES (?, ?, ?)",
        [
            (run_id, ordinal, claim_id)
            for ordinal, claim_id in enumerate(body.claim_ids)
        ],
    )
    conn.commit()
    return run_view(conn, fetch_run(conn, run_id))


@app.post("/api/runs/{run_id}/items/{claim_id}", operation_id="update_run_item")
def update_run_item(
    run_id: int, claim_id: str, body: ItemIn, conn: Conn
) -> dict[str, Any]:
    """Update one item on the run's to-do list: its status and one-line note."""
    fetch_run(conn, run_id)
    cursor = conn.execute(
        "UPDATE run_items SET status = ?, note = ? WHERE run_id = ? AND claim_id = ?",
        (body.status, body.note, run_id, claim_id),
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"item {claim_id} not on the run")
    conn.commit()
    return run_view(conn, fetch_run(conn, run_id))


@app.post("/api/runs/{run_id}/finish", operation_id="finish_run")
def finish_run(run_id: int, body: FinishIn, conn: Conn) -> dict[str, Any]:
    """Store the run's summary and mark it finished."""
    fetch_run(conn, run_id)
    conn.execute(
        "UPDATE runs SET summary = ?, finished = 1 WHERE run_id = ?",
        (body.summary, run_id),
    )
    conn.commit()
    return run_view(conn, fetch_run(conn, run_id))


@app.get("/api/runs/current", operation_id="get_current_run")
def get_current_run(conn: Conn) -> dict[str, Any] | None:
    """Return the latest run with its to-do list, or null if there is none."""
    row = conn.execute("SELECT * FROM runs ORDER BY run_id DESC LIMIT 1").fetchone()
    return run_view(conn, row) if row is not None else None
