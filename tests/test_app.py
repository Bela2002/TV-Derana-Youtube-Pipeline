import main
from pipeline.youtube_client import QuotaExceededError


def test_health():
    assert main.app.test_client().get("/").status_code == 200


def test_run_success(monkeypatch):
    monkeypatch.setattr(main, "run_pipeline", lambda: {"status": "success"})
    resp = main.app.test_client().post("/run")
    assert resp.status_code == 200 and resp.get_json()["status"] == "success"


def test_run_quota(monkeypatch):
    def boom():
        raise QuotaExceededError("quota")

    monkeypatch.setattr(main, "run_pipeline", boom)
    resp = main.app.test_client().post("/run")
    assert resp.status_code == 200  # no scheduler retry
    assert resp.get_json()["status"] == "quota_exceeded"


def test_run_failure(monkeypatch):
    def boom():
        raise RuntimeError("bad")

    monkeypatch.setattr(main, "run_pipeline", boom)
    resp = main.app.test_client().post("/run")
    assert resp.status_code == 500 and resp.get_json()["error"] == "bad"


def test_get_run_not_allowed():
    assert main.app.test_client().get("/run").status_code == 405
