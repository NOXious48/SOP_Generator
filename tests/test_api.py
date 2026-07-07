"""API smoke tests using FastAPI's TestClient."""
from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_full_flow_create_process_job_sop():
    r = client.post("/v1/processes", json={"name": "Create New Order"})
    assert r.status_code == 201
    pid = r.json()["processId"]

    for i, name in enumerate(["a.png", "b.png", "c.png"], start=1):
        u = client.post(f"/v1/processes/{pid}/uploads", params={"filename": name, "order": i})
        assert u.status_code == 200

    j = client.post("/v1/jobs", json={"process_id": pid})
    assert j.status_code == 202
    sop_id = j.json()["sopId"]
    assert sop_id

    s = client.get(f"/v1/sops/{sop_id}")
    assert s.status_code == 200
    assert s.json()["title"] == "Create New Order"


def test_metrics_endpoint():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert b"processiq_http_requests_total" in r.content
