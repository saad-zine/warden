"""API: the endpoints from docs/API.md work end to end."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_and_agents():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["product"] == "Warden"
    r = client.get("/api/agents")
    assert r.status_code == 200
    assert {a["id"] for a in r.json()} == {"scout", "planner"}


def test_run_and_trace_via_api():
    r = client.post("/api/runs", json={
        "agent_id": "scout",
        "task": "Research vendor Acme Corp and compute the total for 10 seats at $19 each, then save a summary file.",
    })
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    assert r.json()["status"] == "completed"

    r = client.get(f"/api/runs/{run_id}")
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert len(r.json()["trace"]) >= 10

    r = client.get(f"/api/runs/{run_id}/trace")
    assert r.status_code == 200
    assert len(r.json()["steps"]) >= 10


def test_approval_flow_via_api():
    r = client.post("/api/runs", json={
        "agent_id": "scout",
        "task": "Research vendor Acme Corp, compute the total for 50 seats at $49 each, save a summary, and update the CRM record with the quote.",
    })
    assert r.status_code == 201
    assert r.json()["status"] == "awaiting_approval"
    run_id = r.json()["run_id"]
    approval_id = r.json()["pending_approval"]["approval_id"]

    r = client.get("/api/approvals?status=pending")
    assert r.status_code == 200
    assert any(a["id"] == approval_id for a in r.json())

    r = client.post(f"/api/runs/{run_id}/approve",
                    json={"approval_id": approval_id, "note": "ok"})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    assert r.json()["success"] is True


def test_replay_and_checkpoints_via_api():
    r = client.post("/api/runs", json={
        "agent_id": "scout",
        "task": "Research vendor Acme Corp and compute the total for 10 seats at $19 each, then save a summary file.",
    })
    run_id = r.json()["run_id"]
    r = client.post(f"/api/runs/{run_id}/replay")
    assert r.status_code == 200
    assert r.json()["divergences"] == []
    assert r.json()["replayed_steps"] >= 4
    r = client.get(f"/api/runs/{run_id}/checkpoints")
    assert r.status_code == 200
    assert len(r.json()["checkpoints"]) >= 5


def test_memory_crud_via_api():
    r = client.post("/api/memory", json={
        "agent_id": "scout", "content": "API test fact: Acme prefers annual billing.",
        "category": "preference",
    })
    assert r.status_code == 201
    mid = r.json()["id"]
    r = client.get("/api/memory?agent_id=scout")
    assert any(m["id"] == mid for m in r.json())
    r = client.put(f"/api/memory/{mid}", json={"content": "API test fact: updated."})
    assert r.status_code == 200
    r = client.delete(f"/api/memory/{mid}")
    assert r.status_code == 204


def test_stats_failure_modes_leaderboard_quests():
    # Seed at least one run so the stats are non-empty.
    client.post("/api/runs", json={
        "agent_id": "scout",
        "task": "Research vendor Acme Corp and compute the total for 10 seats at $19 each, then save a summary file.",
    })
    for path in ("/api/stats", "/api/failure-modes", "/api/leaderboard", "/api/quests"):
        r = client.get(path)
        assert r.status_code == 200, path
    stats = client.get("/api/stats").json()
    assert stats["runs_total"] >= 1
    assert 0 <= stats["reliability_score"] <= 100
    assert stats["level"] in ("Fragile", "Hardening", "Battle-tested", "Production-grade")
    quests = client.get("/api/quests").json()
    assert len(quests) >= 1
    qid = quests[0]["id"]
    r = client.post(f"/api/quests/{qid}/complete", json={"note": "fixed in test"})
    assert r.status_code == 200
    assert r.json()["xp_awarded"] == quests[0]["xp"]


def test_eval_run_via_api():
    r = client.post("/api/evals/run", json={"candidate": "current"})
    assert r.status_code == 200
    assert r.json()["verdict"] in ("pass", "blocked")
    assert r.json()["scenarios_total"] == 8
    eval_id = r.json()["id"]
    r = client.get(f"/api/evals/{eval_id}")
    assert r.status_code == 200
    assert len(r.json()["scenarios"]) == 8
