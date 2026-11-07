"""The UnderCover Agent."""

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv(override=True)

BACKEND_URL = "http://localhost:8000"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"

FRAMING = """Use get_claim to read the claim in full. Use list_handbook_sections \
and read_handbook_section to look up the policy wording and the claims manual as \
you need them. Then use submit_decision to record your decision with the payout, \
the reason and the policy section."""


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


def call(method: str, path: str, **kwargs: Any) -> Any:
    """Call the backend, raise on an error status, and return the JSON body."""
    with backend() as client:
        response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()


@tool
def get_claim(claim_id: str) -> str:
    """Read a claim in full: its story, items, documents, policy, plan and history."""
    detail = fetch_detail(claim_id)
    add_step(claim_id, "Read the claim", "Read the story, items, documents and policy.")
    return json.dumps(detail)


@tool
def list_handbook_sections() -> str:
    """List the sections of the policy wording and the claims manual to look up."""
    return json.dumps(call("GET", "/api/handbook"))


@tool
def read_handbook_section(claim_id: str, section_id: str) -> str:
    """Read one handbook section by its id, such as wording/3 or manual/9."""
    section = call("GET", f"/api/handbook/{section_id}")
    label = "Read the manual" if section["document"] == "manual" else "Read the wording"
    add_step(claim_id, label, section["title"])
    return section["text"]


@tool
def submit_decision(
    claim_id: str, decision: str, payout: float, reason: str, policy_section: str
) -> str:
    """Record the decision on a claim: approve, decline or refer, with its payout."""
    call(
        "POST",
        f"/api/claims/{claim_id}/decision",
        json={
            "decision": decision,
            "payout": payout,
            "reason": reason,
            "policy_section": policy_section,
        },
    )
    return f"Recorded {decision} on {claim_id}."


def instructions(kind: str) -> str:
    """Read one of the agent's instruction sets ('queue' or 'claim')."""
    return call("GET", "/api/instructions")[kind]


def add_step(claim_id: str, label: str, detail: str) -> None:
    """Record a step in the agent's work on the claim."""
    call(
        "POST", f"/api/claims/{claim_id}/steps", json={"label": label, "detail": detail}
    )


def post_claim(claim_id: str, action: str) -> None:
    """Move a claim through an action: start, requeue or for_handler."""
    call("POST", f"/api/claims/{claim_id}/{action}")


def system_prompt() -> str:
    """Build the worker's system prompt from the claim instructions and framing."""
    return f"{instructions('claim')}\n\n{FRAMING}"


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or DeepSeek V4.1 Flash by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
    )


def fetch_detail(claim_id: str) -> dict[str, Any]:
    """Read a claim's current detail from the backend."""
    return call("GET", f"/api/claims/{claim_id}")


@dataclass(frozen=True)
class Report:
    """A claim's outcome: the kind for counting and a one-line note for people."""

    claim_id: str
    kind: str
    line: str


def report(claim_id: str, detail: dict[str, Any]) -> Report:
    """Turn a claim's current detail into its outcome report."""
    decision = detail["decision"]
    if decision is None:
        return Report(claim_id, "failed", f"{claim_id}: failed")
    kind = decision["decision"]
    if kind == "approve":
        return Report(
            claim_id, "approve", f"{claim_id}: approve, ${decision['payout']:.2f}"
        )
    return Report(claim_id, kind, f"{claim_id}: {kind}")


def work_claim(claim_id: str, llm: BaseChatModel | None = None) -> Report:
    """Work one claim from a clean start and return its outcome report."""
    if fetch_detail(claim_id)["decision"] is not None:
        return Report(claim_id, "already decided", f"{claim_id}: already decided")
    post_claim(claim_id, "start")
    add_step(claim_id, "Picked up the claim", f"Opened {claim_id} from the queue.")
    agent = create_agent(
        llm or model(),
        tools=[
            get_claim,
            list_handbook_sections,
            read_handbook_section,
            submit_decision,
        ],
        system_prompt=system_prompt(),
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"Decide claim {claim_id}."}]}
    )
    add_step(claim_id, "Recorded the decision", result["messages"][-1].text)
    return report(claim_id, fetch_detail(claim_id))


def waiting_claims(limit: int | None) -> list[str]:
    """Read the waiting claims from the queue, capped at `limit`."""
    ids = [c["claim_id"] for c in call("GET", "/api/claims") if c["state"] == "waiting"]
    return ids if limit is None else ids[:limit]


def plan_order(claim_ids: list[str], llm: BaseChatModel) -> list[str]:
    """Ask the model for the order to work the claims, reconciled to the set."""
    if not claim_ids:
        return []
    prompt = (
        f"{instructions('queue')}\n\nOrder these claims to work them, best first, "
        "and reply with their ids in that order:\n" + "\n".join(claim_ids)
    )
    text = llm.invoke(prompt).text
    wanted = set(claim_ids)
    ordered: list[str] = []
    for claim_id in re.findall(r"CLM-\d+", text):
        if claim_id in wanted and claim_id not in ordered:
            ordered.append(claim_id)
    ordered += [c for c in claim_ids if c not in ordered]
    return ordered


def open_run(limit: int | None) -> int:
    """Open a run on the backend and return its id."""
    return call("POST", "/api/runs", json={"limit": limit})["run_id"]


def write_plan(run_id: int, claim_ids: list[str]) -> None:
    """Write the run's to-do list in order."""
    call("POST", f"/api/runs/{run_id}/plan", json={"claim_ids": claim_ids})


def set_item(run_id: int, claim_id: str, status: str, note: str) -> None:
    """Update one item on the run's to-do list."""
    call(
        "POST",
        f"/api/runs/{run_id}/items/{claim_id}",
        json={"status": status, "note": note},
    )


def finish_run(run_id: int, summary: str) -> None:
    """Store the run's summary and mark it finished."""
    call("POST", f"/api/runs/{run_id}/finish", json={"summary": summary})


def work_with_retry(run_id: int, claim_id: str, llm: BaseChatModel) -> Report:
    """Work a claim, retrying once before a decision; hand off after a second fail."""
    for attempt in (1, 2):
        note = "Working the claim." if attempt == 1 else "Trying the claim again."
        set_item(run_id, claim_id, "in_progress", note)
        try:
            work_claim(claim_id, llm)
        except Exception as error:
            add_step(claim_id, "Hit a problem", f"The worker failed: {error}")
        detail = fetch_detail(claim_id)
        if detail["decision"] is not None:
            outcome = report(claim_id, detail)
            set_item(run_id, claim_id, "done", outcome.line)
            return outcome
        if attempt == 1:
            post_claim(claim_id, "requeue")
            set_item(run_id, claim_id, "to_do", "Failed; back in the queue.")
    post_claim(claim_id, "for_handler")
    set_item(run_id, claim_id, "for_handler", "Failed twice; left for a handler.")
    return Report(claim_id, "for_handler", f"{claim_id}: for_handler")


def summarise(reports: list[Report]) -> str:
    """Count the outcomes of a run's reports into one line for the handlers."""
    if not reports:
        return "No claims to work."
    counts = Counter(outcome.kind for outcome in reports)
    parts = ", ".join(f"{count} {name}" for name, count in sorted(counts.items()))
    return f"Worked {len(reports)} claims: {parts}."


def run_queue(limit: int | None = None, llm: BaseChatModel | None = None) -> str:
    """Work every waiting claim, up to `limit`, recovering from failures."""
    chat = llm or model()
    run_id = open_run(limit)
    ordered = plan_order(waiting_claims(limit), chat)
    write_plan(run_id, ordered)
    reports: dict[str, Report] = {}

    def handle(claim_id: str) -> None:
        # One guard around the whole of a claim's work: a backend outage or any
        # other failure is turned into a report in memory, never an escape that
        # stops the run. The guard itself makes no network call to report.
        try:
            reports[claim_id] = work_with_retry(run_id, claim_id, chat)
        except Exception:
            reports.setdefault(
                claim_id, Report(claim_id, "failed", f"{claim_id}: failed")
            )

    for claim_id in ordered:
        handle(claim_id)
    # Missed-claims check: re-read the queue and work any claim this run planned
    # that is somehow still waiting, staying within the run's cap.
    planned = set(ordered)
    for claim_id in waiting_claims(limit):
        if claim_id in planned:
            handle(claim_id)
    summary = summarise(list(reports.values()))
    finish_run(run_id, summary)
    return summary
