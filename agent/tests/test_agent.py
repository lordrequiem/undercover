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
    """Script a model that reads the claim, then submits a fixed decision."""
    return [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get_claim", "args": {"claim_id": claim_id}, "id": "c"}
            ],
        ),
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
                    "id": "d",
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


def test_prompt_drops_the_wording_and_never_reaches_the_evals(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    prompt = main.system_prompt()
    assert "evals" not in prompt
    assert "General exclusions" not in prompt


def test_read_handbook_section_records_a_named_step(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    main.start("CLM-1001")
    text = main.read_handbook_section.invoke(
        {"claim_id": "CLM-1001", "section_id": "manual/9"}
    )
    assert "third claim" in text
    steps = TestClient(app).get("/api/claims/CLM-1001").json()["steps"]
    assert steps[-1]["label"] == "Read the manual"
    assert steps[-1]["detail"].startswith("9.")


def test_list_handbook_sections_lists_both_documents(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    sections = json.loads(main.list_handbook_sections.invoke({}))
    assert {s["document"] for s in sections} == {"wording", "manual"}


def test_run_records_the_decision(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    reply = main.run(
        "CLM-1001",
        "thread-1",
        StubModel(messages=iter(decision_call("CLM-1001", "approve", 500.0))),
    )
    assert reply == "CLM-1001: approve, $500.00"
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


def test_run_records_ordered_steps_ending_in_the_decision(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    main.run(
        "CLM-1001",
        "thread-3",
        StubModel(messages=iter(decision_call("CLM-1001", "approve", 300.0))),
    )
    steps = TestClient(app).get("/api/claims/CLM-1001").json()["steps"]
    assert [step["label"] for step in steps] == [
        "Picked up the claim",
        "Read the instructions",
        "Read the claim",
        "Recorded the decision",
    ]


def test_run_moves_through_in_progress_to_final(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    seen = {}
    real = main.instructions

    def spy(kind="claim"):
        seen["state"] = TestClient(app).get("/api/claims/CLM-1001").json()["state"]
        return real(kind)

    monkeypatch.setattr(main, "instructions", spy)
    main.run(
        "CLM-1001",
        "thread-4",
        StubModel(messages=iter(decision_call("CLM-1001", "approve", 300.0))),
    )
    assert seen["state"] == "in_progress"
    assert TestClient(app).get("/api/claims/CLM-1001").json()["state"] == "decided"


def test_work_claim_records_the_decision_and_reports_it(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    report = main.work_claim(
        "CLM-1004",
        StubModel(messages=iter(decision_call("CLM-1004", "refer", 0.0))),
    )
    assert report == "CLM-1004: refer"
    detail = TestClient(app).get("/api/claims/CLM-1004").json()
    assert detail["decision"]["decision"] == "refer"


def test_work_claim_leaves_an_already_decided_claim_alone(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    main.work_claim(
        "CLM-1001",
        StubModel(messages=iter(decision_call("CLM-1001", "approve", 300.0))),
    )
    steps_before = len(TestClient(app).get("/api/claims/CLM-1001").json()["steps"])
    report = main.work_claim(
        "CLM-1001",
        StubModel(messages=iter(decision_call("CLM-1001", "decline", 0.0))),
    )
    assert "already decided" in report
    detail = TestClient(app).get("/api/claims/CLM-1001").json()
    assert detail["decision"]["decision"] == "approve"
    assert len(detail["steps"]) == steps_before


def queue_messages(ordered_claims):
    """Script a planning reply, then a decision for each claim in order."""
    messages = [AIMessage(content=" ".join(cid for cid, _, _ in ordered_claims))]
    for claim_id, decision, payout in ordered_claims:
        messages += decision_call(claim_id, decision, payout)
    return messages


def first_waiting(count):
    queue = TestClient(app).get("/api/claims").json()
    return [c["claim_id"] for c in queue if c["state"] == "waiting"][:count]


def test_run_queue_stores_and_works_the_to_do_list(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    ids = first_waiting(2)
    ordered = [(ids[0], "approve", 300.0), (ids[1], "refer", 0.0)]
    summary = main.run_queue(2, StubModel(messages=iter(queue_messages(ordered))))

    current = TestClient(app).get("/api/runs/current").json()
    assert [item["claim_id"] for item in current["items"]] == ids
    assert all(item["status"] == "done" for item in current["items"])
    assert current["items"][0]["note"] == f"{ids[0]}: approve, $300.00"
    assert current["summary"] == summary
    assert summary == "Worked 2 claims: 1 approve, 1 refer."


def test_run_queue_caps_the_run(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    ids = first_waiting(3)
    ordered = [(claim_id, "approve", 100.0) for claim_id in ids]
    main.run_queue(3, StubModel(messages=iter(queue_messages(ordered))))

    queue = TestClient(app).get("/api/claims").json()
    assert len([c for c in queue if c["state"] != "waiting"]) == 3
    assert len([c for c in queue if c["state"] == "waiting"]) == 22


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    assert main.model().model_name == "openai/gpt-6-luna"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert main.model().model_name == "openrouter/free"
