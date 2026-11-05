from fastapi.testclient import TestClient

import app.main
from app.gemini import DailyQuotaExceeded
from app.main import ExplanationLimit

BODY = {"target_id": 1, "source_id": 2}


def test_limit_blocks_explanations_after_the_daily_cap(monkeypatch):
    monkeypatch.setattr(app.main, "explanation_limit", ExplanationLimit(1))
    monkeypatch.setattr(app.main, "connect", lambda: (_ for _ in ()).throw(LookupError("reached the database")))
    client = TestClient(app.main.app, raise_server_exceptions=False)
    assert client.post("/explain-edge", json=BODY).status_code == 500  # first call got past the limit
    assert client.post("/explain-edge", json=BODY).status_code == 429


def test_limit_resets_on_a_new_day():
    limit = ExplanationLimit(1)
    limit.take()
    limit.day = "2000-01-01"
    limit.take()
    assert limit.used == 1


def test_zero_means_no_limit():
    limit = ExplanationLimit(0)
    for _ in range(3):
        limit.take()


def test_gemini_daily_quota_becomes_a_clear_503(monkeypatch):
    def out_of_quota():
        raise DailyQuotaExceeded("PerDay")
    monkeypatch.setattr(app.main, "explanation_limit", ExplanationLimit(0))
    monkeypatch.setattr(app.main, "connect", out_of_quota)
    res = TestClient(app.main.app).post("/explain-edge", json=BODY)
    assert res.status_code == 503
    assert "free limit" in res.json()["detail"]
