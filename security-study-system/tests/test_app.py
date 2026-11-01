import pytest
from fastapi.testclient import TestClient
import app as study


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(study, "DB", tmp_path / "history.sqlite3")
    with TestClient(study.app) as c:
        yield c


def test_meta_and_quiz_no_answers(client):
    meta = client.get("/api/meta").json()
    assert len(meta["subjects"]) == 5
    assert meta["questions"] == 100
    assert meta["written"] == 20
    q = client.get("/api/quiz?count=1").json()["questions"][0]
    assert "correct_index" not in q and "explanation" not in q
    assert len(q["options"]) >= 2


def test_score_wrongbook_and_progress(client):
    q = client.get("/api/quiz?count=1").json()["questions"][0]
    true_answer = study.question_bank()[q["key"]]["correct_index"]
    incorrect = (true_answer + 1) % len(q["options"])
    r = client.post("/api/answers", json={"question_key": q["key"], "selected": incorrect})
    assert r.json()["correct"] is False
    assert client.get("/api/wrongbook").json()[0]["question_key"] == q["key"]
    assert client.put("/api/wrongbook/" + q["key"], json={"memo": "복습", "review_date": "2027-04-01"}).status_code == 200
    r = client.post("/api/answers", json={"question_key": q["key"], "selected": true_answer})
    assert r.json()["correct"] is True
    assert client.get("/api/wrongbook").json() == []
    k = client.get("/api/concepts").json()[0]["key"]
    assert client.post("/api/progress", params={"key": k}, json={"done": True}).status_code == 200
    assert client.get("/api/analytics").json()["total_done"] == 1


def test_source_safety_and_headers(client):
    first = client.get("/api/sources").json()[0]
    assert client.delete("/api/sources/" + str(first["id"])).status_code == 409
    bad = {"url": "javascript:alert(1)", "title": "Bad"}
    assert client.post("/api/sources", json=bad).status_code == 422
    created = client.post("/api/sources", json={"url": "https://example.org/notes", "title": "추가 참고"}).json()
    assert client.delete("/api/sources/" + str(created["id"])).status_code == 200
    assert client.get("/").headers["x-frame-options"] == "DENY"
