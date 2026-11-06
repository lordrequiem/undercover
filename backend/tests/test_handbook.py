from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_handbook_lists_sections_from_both_documents_in_order():
    sections = client.get("/api/handbook").json()
    documents = [s["document"] for s in sections]
    assert "wording" in documents
    assert "manual" in documents
    assert documents == sorted(documents, key=["wording", "manual"].index)
    wording = [s for s in sections if s["document"] == "wording"]
    assert wording[0]["section_id"] == "wording/1"


def test_handbook_section_returns_its_text():
    section = client.get("/api/handbook/manual/9").json()
    assert section["section_id"] == "manual/9"
    assert section["document"] == "manual"
    assert "third claim" in section["text"]
    assert section["title"].startswith("9.")


def test_unknown_section_returns_404():
    assert client.get("/api/handbook/manual/999").status_code == 404
    assert client.get("/api/handbook/nowhere/1").status_code == 404
