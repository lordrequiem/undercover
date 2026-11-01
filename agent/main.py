"""The UnderCover Agent."""

import json
import os
from pathlib import Path

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
POLICY_WORDING = Path(__file__).resolve().parents[1] / "data" / "policy_wording.md"

FRAMING = """Use get_claim to read the claim in full, then submit_decision to \
record your decision with the payout, the reason and the policy section.

The policy wording follows."""


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


@tool
def get_claim(claim_id: str) -> str:
    """Read a claim in full: its story, items, documents, policy, plan and history."""
    with backend() as client:
        response = client.get(f"/api/claims/{claim_id}")
    response.raise_for_status()
    return json.dumps(response.json())


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


def instructions() -> str:
    """Read the agent's instructions from the backend."""
    with backend() as client:
        response = client.get("/api/instructions")
    response.raise_for_status()
    return response.json()["instructions"]


def system_prompt() -> str:
    """Build the system prompt from the instructions and the policy wording."""
    wording = POLICY_WORDING.read_text(encoding="utf-8")
    return f"{instructions()}\n\n{FRAMING}\n\n{wording}"


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or GPT-6 Luna by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
    )


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Run the agent on one claim and return its final reply."""
    agent = create_agent(
        llm or model(),
        tools=[get_claim, submit_decision],
        system_prompt=system_prompt(),
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"Decide claim {claim_id}."}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].text
