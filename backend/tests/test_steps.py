from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_start_sets_in_progress():
    body = client.post("/api/claims/CLM-1001/start").json()
    assert body["state"] == "in_progress"


def test_steps_append_in_order_and_show_on_detail():
    client.post("/api/claims/CLM-1001/steps", json={"label": "First", "detail": "one"})
    client.post("/api/claims/CLM-1001/steps", json={"label": "Second", "detail": "two"})
    steps = client.get("/api/claims/CLM-1001").json()["steps"]
    assert [step["label"] for step in steps] == ["First", "Second"]
    assert steps[0]["detail"] == "one"
