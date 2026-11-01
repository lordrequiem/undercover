from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def decide(claim_id, decision, payout=0.0):
    return client.post(
        f"/api/claims/{claim_id}/decision",
        json={
            "decision": decision,
            "payout": payout,
            "reason": "test",
            "policy_section": "Section 3",
        },
    )


def test_approve_under_limit_is_decided():
    body = decide("CLM-1001", "approve", 500.0).json()
    assert body["state"] == "decided"
    assert body["decision"]["payout"] == 500.0


def test_approve_over_limit_waits_for_signoff():
    body = decide("CLM-1002", "approve", 2500.0).json()
    assert body["state"] == "waiting_for_signoff"


def test_decline_and_refer_are_decided_with_zero_payout():
    for claim_id, decision in [("CLM-1003", "decline"), ("CLM-1004", "refer")]:
        body = decide(claim_id, decision, 999.0).json()
        assert body["state"] == "decided"
        assert body["decision"]["payout"] == 0.0


def test_guardrail_blocks_over_limit_pay_until_signoff():
    decide("CLM-1005", "approve", 2500.0)
    assert (
        client.post("/api/claims/CLM-1005/pay", json={"amount": 2500.0}).status_code
        == 409
    )
    assert client.post("/api/claims/CLM-1005/signoff").status_code == 200
    paid = client.post("/api/claims/CLM-1005/pay", json={"amount": 2500.0})
    assert paid.status_code == 200
    assert paid.json()["state"] == "decided"


def test_guardrail_holds_for_a_direct_over_limit_amount():
    decide("CLM-1006", "approve", 500.0)
    assert (
        client.post("/api/claims/CLM-1006/pay", json={"amount": 2500.0}).status_code
        == 409
    )


def test_pay_refuses_a_claim_that_is_not_approved():
    decide("CLM-1007", "decline")
    assert (
        client.post("/api/claims/CLM-1007/pay", json={"amount": 10.0}).status_code
        == 409
    )


def test_signoff_refuses_a_claim_not_waiting():
    decide("CLM-1008", "approve", 500.0)
    assert client.post("/api/claims/CLM-1008/signoff").status_code == 409
