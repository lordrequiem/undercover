from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def open_run(limit=None):
    return client.post("/api/runs", json={"limit": limit}).json()["run_id"]


def test_a_run_keeps_an_ordered_to_do_list_and_a_summary():
    run_id = open_run(limit=2)
    client.post(
        f"/api/runs/{run_id}/plan",
        json={"claim_ids": ["CLM-1002", "CLM-1001"]},
    )
    client.post(
        f"/api/runs/{run_id}/items/CLM-1002",
        json={"status": "done", "note": "CLM-1002: approve, $500.00"},
    )
    client.post(f"/api/runs/{run_id}/finish", json={"summary": "Worked 2 claims."})

    current = client.get("/api/runs/current").json()
    assert current["run_id"] == run_id
    assert current["limit"] == 2
    assert current["finished"] is True
    assert current["summary"] == "Worked 2 claims."
    assert [item["claim_id"] for item in current["items"]] == ["CLM-1002", "CLM-1001"]
    assert current["items"][0]["status"] == "done"
    assert current["items"][0]["note"] == "CLM-1002: approve, $500.00"
    assert current["items"][1]["status"] == "to_do"


def test_current_run_is_the_latest():
    first = open_run()
    second = open_run()
    assert first != second
    assert client.get("/api/runs/current").json()["run_id"] == second


def test_no_run_yet_returns_null():
    assert client.get("/api/runs/current").json() is None


def test_updating_an_unknown_item_is_404():
    run_id = open_run()
    client.post(f"/api/runs/{run_id}/plan", json={"claim_ids": ["CLM-1001"]})
    response = client.post(
        f"/api/runs/{run_id}/items/CLM-9999", json={"status": "done", "note": "x"}
    )
    assert response.status_code == 404
