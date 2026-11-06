import json
from collections import defaultdict

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


class FakeWorker:
    """A stand-in for work_claim with a scripted outcome per attempt."""

    def __init__(self, script):
        self.script = script
        self.calls = defaultdict(int)

    def __call__(self, claim_id, llm, thread_id=None):
        outcome = self.script[claim_id][self.calls[claim_id]]
        self.calls[claim_id] += 1
        main.start(claim_id)
        if outcome == "raise":
            raise RuntimeError("provider error")
        if outcome == "fail":
            return f"{claim_id}: failed"
        main.submit_decision.invoke(
            {
                "claim_id": claim_id,
                "decision": outcome,
                "payout": 100.0 if outcome == "approve" else 0.0,
                "reason": "r",
                "policy_section": "3",
            }
        )
        return main.report(claim_id, main.fetch_detail(claim_id))


def setup_queue(monkeypatch, script):
    """Point the agent at the test backend with a scripted fake worker."""
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    monkeypatch.setattr(main, "plan_order", lambda ids, llm: ids)
    worker = FakeWorker(script)
    monkeypatch.setattr(main, "work_claim", worker)
    return worker


def items_by_claim(run):
    return {item["claim_id"]: item for item in run["items"]}


def test_a_raising_worker_does_not_stop_the_run(monkeypatch):
    bad, good = first_waiting(3)[0], first_waiting(3)[1]
    other = first_waiting(3)[2]
    worker = setup_queue(
        monkeypatch,
        {bad: ["raise", "raise"], good: ["approve"], other: ["decline"]},
    )
    main.run_queue(3, StubModel(messages=iter([])))

    run = TestClient(app).get("/api/runs/current").json()
    assert run["finished"] is True
    items = items_by_claim(run)
    assert items[good]["status"] == "done"
    assert items[other]["status"] == "done"
    assert items[bad]["status"] == "for_handler"
    assert worker.calls[bad] == 2


def test_a_claim_that_fails_once_is_retried_and_succeeds(monkeypatch):
    claim_id = first_waiting(1)[0]
    worker = setup_queue(monkeypatch, {claim_id: ["fail", "approve"]})
    main.run_queue(1, StubModel(messages=iter([])))

    assert worker.calls[claim_id] == 2
    run = TestClient(app).get("/api/runs/current").json()
    assert items_by_claim(run)[claim_id]["status"] == "done"
    detail = TestClient(app).get(f"/api/claims/{claim_id}").json()
    assert detail["decision"]["decision"] == "approve"


def test_a_claim_that_fails_twice_is_left_for_a_handler(monkeypatch):
    claim_id = first_waiting(1)[0]
    setup_queue(monkeypatch, {claim_id: ["fail", "fail"]})
    main.run_queue(1, StubModel(messages=iter([])))

    detail = TestClient(app).get(f"/api/claims/{claim_id}").json()
    assert detail["state"] == "for_handler"
    assert detail["decision"] is None
    run = TestClient(app).get("/api/runs/current").json()
    assert items_by_claim(run)[claim_id]["status"] == "for_handler"


def test_no_claim_is_left_in_progress(monkeypatch):
    first, second = first_waiting(2)
    setup_queue(monkeypatch, {first: ["fail", "fail"], second: ["approve"]})
    main.run_queue(2, StubModel(messages=iter([])))

    queue = TestClient(app).get("/api/claims").json()
    assert all(c["state"] != "in_progress" for c in queue)


def test_the_missed_claims_check_leaves_no_capped_claim_waiting(monkeypatch):
    capped = first_waiting(2)
    setup_queue(monkeypatch, {capped[0]: ["fail", "approve"], capped[1]: ["approve"]})
    main.run_queue(2, StubModel(messages=iter([])))

    queue = {
        c["claim_id"]: c["state"] for c in TestClient(app).get("/api/claims").json()
    }
    assert all(queue[claim_id] != "waiting" for claim_id in capped)


def test_a_retry_never_records_a_second_decision(monkeypatch):
    claim_id = first_waiting(1)[0]

    class DecideThenCrash(FakeWorker):
        def __call__(self, cid, llm, thread_id=None):
            self.calls[cid] += 1
            main.submit_decision.invoke(
                {
                    "claim_id": cid,
                    "decision": "approve",
                    "payout": 100.0,
                    "reason": "r",
                    "policy_section": "3",
                }
            )
            return f"{cid}: failed"

    worker = DecideThenCrash({})
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    monkeypatch.setattr(main, "plan_order", lambda ids, llm: ids)
    monkeypatch.setattr(main, "work_claim", worker)
    main.run_queue(1, StubModel(messages=iter([])))

    assert worker.calls[claim_id] == 1
    detail = TestClient(app).get(f"/api/claims/{claim_id}").json()
    assert detail["state"] == "decided"
    again = TestClient(app).post(
        f"/api/claims/{claim_id}/decision",
        json={"decision": "decline", "payout": 0, "reason": "r", "policy_section": "3"},
    )
    assert again.status_code == 409


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    assert main.model().model_name == "deepseek/deepseek-v4.1-flash"
    assert main.model().reasoning_effort == "low"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert main.model().model_name == "openrouter/free"
    assert main.model().reasoning_effort is None
