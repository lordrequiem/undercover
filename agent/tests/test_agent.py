import json

from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent import main
from backend.main import app


class StubModel(GenericFakeChatModel):
    """A chat model that gives scripted replies in place of a real model."""

    def bind_tools(self, tools, **kwargs):
        return self


def decision_call(claim_id, decision, payout):
    """Script a model that submits a fixed decision, then signs off."""
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "submit_decision",
                    "args": {
                        "claim_id": claim_id,
                        "decision": decision,
                        "payout": payout,
                        "reason": "Covered under the policy wording.",
                        "policy_section": "Section 3",
                    },
                    "id": "1",
                }
            ],
        ),
        AIMessage(content=f"I have {decision}d the claim."),
    ]


def test_tools_call_the_backend(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    claim = json.loads(main.get_claim.invoke({"claim_id": "CLM-1001"}))
    assert claim["claim_id"] == "CLM-1001"
    main.submit_decision.invoke(
        {
            "claim_id": "CLM-1001",
            "decision": "approve",
            "payout": 300.0,
            "reason": "r",
            "policy_section": "Section 3",
        }
    )
    assert TestClient(app).get("/api/claims/CLM-1001").json()["decision"] is not None


def test_prompt_and_tools_do_not_reach_the_evals(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    assert "evals" not in main.system_prompt()
    assert {t.name for t in [main.get_claim, main.submit_decision]} == {
        "get_claim",
        "submit_decision",
    }


def test_run_records_the_decision(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    reply = main.run(
        "CLM-1001",
        "thread-1",
        StubModel(messages=iter(decision_call("CLM-1001", "approve", 500.0))),
    )
    assert reply == "I have approved the claim."
    detail = TestClient(app).get("/api/claims/CLM-1001").json()
    assert detail["state"] == "decided"
    assert detail["decision"]["decision"] == "approve"
    assert detail["decision"]["payout"] == 500.0
    assert detail["decision"]["policy_section"] == "Section 3"


def test_run_over_limit_waits_for_signoff(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    main.run(
        "CLM-1002",
        "thread-2",
        StubModel(messages=iter(decision_call("CLM-1002", "approve", 2500.0))),
    )
    detail = TestClient(app).get("/api/claims/CLM-1002").json()
    assert detail["state"] == "waiting_for_signoff"
    assert detail["decision"]["paid"] is None


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    assert main.model().model_name == "openai/gpt-6-luna"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert main.model().model_name == "openrouter/free"
