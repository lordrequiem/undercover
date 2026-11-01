from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_queue_lists_all_claims_waiting():
    response = client.get("/api/claims")
    assert response.status_code == 200
    queue = response.json()
    assert len(queue) == 25
    assert all(claim["state"] == "waiting" for claim in queue)


def test_queue_item_fields():
    item = next(
        c for c in client.get("/api/claims").json() if c["claim_id"] == "CLM-1001"
    )
    assert item["customer_name"] == "Maya Patel"
    assert item["plan"] == "premium"
    assert item["claim_type"] == "trip_delay"
    assert item["amount_claimed"] == 420.0
    assert item["submitted_on"] == "2026-06-24"


def test_claim_detail_has_policy_plan_and_history():
    detail = client.get("/api/claims/CLM-1001").json()
    assert detail["policy"]["policy_id"] == "POL-2001"
    assert detail["plan"]["plan"] == "premium"
    assert detail["customer"]["name"] == "Maya Patel"
    assert detail["customer"]["previous_claims"][0]["claim_id"] == "CLM-0412"
    assert detail["items"]
    assert detail["decision"] is None
    assert detail["steps"] == []


def test_missing_claim_returns_404():
    assert client.get("/api/claims/CLM-9999").status_code == 404


def test_instructions_returns_text():
    response = client.get("/api/instructions")
    assert response.status_code == 200
    assert response.json()["instructions"].strip()
