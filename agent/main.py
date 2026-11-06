"""The UnderCover Agent."""

import json
import os
from uuid import uuid4

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
DEFAULT_MODEL = "openai/gpt-6-luna"

FRAMING = """Use get_claim to read the claim in full. Use list_handbook_sections \
and read_handbook_section to look up the policy wording and the claims manual as \
you need them. Then use submit_decision to record your decision with the payout, \
the reason and the policy section."""


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


@tool
def get_claim(claim_id: str) -> str:
    """Read a claim in full: its story, items, documents, policy, plan and history."""
    with backend() as client:
        response = client.get(f"/api/claims/{claim_id}")
    response.raise_for_status()
    add_step(claim_id, "Read the claim", "Read the story, items, documents and policy.")
    return json.dumps(response.json())


@tool
def list_handbook_sections() -> str:
    """List the sections of the policy wording and the claims manual to look up."""
    with backend() as client:
        response = client.get("/api/handbook")
    response.raise_for_status()
    return json.dumps(response.json())


@tool
def read_handbook_section(claim_id: str, section_id: str) -> str:
    """Read one handbook section by its id, such as wording/3 or manual/9."""
    with backend() as client:
        response = client.get(f"/api/handbook/{section_id}")
    response.raise_for_status()
    section = response.json()
    label = "Read the manual" if section["document"] == "manual" else "Read the wording"
    add_step(claim_id, label, section["title"])
    return section["text"]


@tool
def submit_decision(
    claim_id: str, decision: str, payout: float, reason: str, policy_section: str
) -> str:
    """Record the decision on a claim: approve, decline or refer, with its payout."""
    with backend() as client:
        response = client.post(
            f"/api/claims/{claim_id}/decision",
            json={
                "decision": decision,
                "payout": payout,
                "reason": reason,
                "policy_section": policy_section,
            },
        )
    response.raise_for_status()
    return f"Recorded {decision} on {claim_id}."


def instructions(kind: str = "claim") -> str:
    """Read one of the agent's instruction sets from the backend."""
    with backend() as client:
        response = client.get("/api/instructions")
    response.raise_for_status()
    return response.json()[kind]


def start(claim_id: str) -> None:
    """Tell the backend the agent has started working the claim."""
    with backend() as client:
        client.post(f"/api/claims/{claim_id}/start").raise_for_status()


def add_step(claim_id: str, label: str, detail: str) -> None:
    """Record a step in the agent's work on the claim."""
    with backend() as client:
        client.post(
            f"/api/claims/{claim_id}/steps",
            json={"label": label, "detail": detail},
        ).raise_for_status()


def system_prompt() -> str:
    """Build the worker's system prompt from the claim instructions and framing."""
    return f"{instructions('claim')}\n\n{FRAMING}"


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or GPT-6 Luna by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
    )


def fetch_detail(claim_id: str) -> dict:
    """Read a claim's current detail from the backend."""
    with backend() as client:
        response = client.get(f"/api/claims/{claim_id}")
    response.raise_for_status()
    return response.json()


def report(claim_id: str, detail: dict) -> str:
    """Summarise a claim's outcome in one line."""
    decision = detail["decision"]
    if decision is None:
        return f"{claim_id}: failed"
    if decision["decision"] == "approve":
        return f"{claim_id}: approve, ${decision['payout']:.2f}"
    return f"{claim_id}: {decision['decision']}"


def work_claim(
    claim_id: str, llm: BaseChatModel | None = None, thread_id: str | None = None
) -> str:
    """Work one claim from a clean start and return its one-line report."""
    if fetch_detail(claim_id)["decision"] is not None:
        return f"{claim_id}: already decided"
    start(claim_id)
    add_step(claim_id, "Picked up the claim", f"Opened {claim_id} from the queue.")
    add_step(
        claim_id,
        "Read the instructions",
        "Reviewed the instructions for working a claim.",
    )
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
        {"messages": [{"role": "user", "content": f"Decide claim {claim_id}."}]},
        config={"configurable": {"thread_id": thread_id or uuid4().hex}},
    )
    add_step(claim_id, "Recorded the decision", result["messages"][-1].text)
    return report(claim_id, fetch_detail(claim_id))


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Work one named claim and return its one-line report."""
    return work_claim(claim_id, llm, thread_id)
