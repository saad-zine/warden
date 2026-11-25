"""API contract: queued runs, streaming, approvals, replay, memory, evals."""
import json
import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SIMPLE_TASK = (
    "Research vendor Acme Corp and compute the total for 10 seats at $19 "
    "each, then save a summary file."
)
GATED_TASK = (
    "Research vendor Acme Corp, compute the total for 50 seats at $49 each, "
    "save a summary, and update the CRM record with the quote."
)


def _wait(run_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        detail = client.get(f"/api/runs/{run_id}").json()
        if detail["status"] in ("completed", "failed", "blocked", "awaiting_approval"):
            return detail
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not settle: {detail['status']}")


def test_health_and_agents():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["product"] == "Warden"
    assert body["provider"] == "deterministic"
    assert body["tools"] == "mock"
    r = client.get("/api/agents")
    assert r.status_code == 200
    assert {a["id"] for a in r.json()} == {"scout", "planner"}


def test_run_is_queued_then_completes():
    r = client.post("/api/runs", json={"agent_id": "scout", "task": SIMPLE_TASK})
    assert r.status_code == 202
    queued = r.json()
    assert queued["status"] in ("queued", "running")
    assert queued["provider"] == "deterministic"

    detail = _wait(queued["run_id"])
    assert detail["status"] == "completed"
    assert detail["success"] is True
    assert len(detail["trace"]) >= 10
    assert detail["provider"] == "deterministic"
    assert detail["model"] == "warden-local-deterministic"

    r = client.get(f"/api/runs/{queued['run_id']}/trace")
    assert r.status_code == 200
    assert len(r.json()["steps"]) >= 10


def test_wait_parameter_returns_final_state():
    r = client.post("/api/runs", params={"wait": 60},
                    json={"agent_id": "scout", "task": SIMPLE_TASK})
    assert r.status_code == 202
    assert r.json()["status"] == "completed"
    assert r.json()["success"] is True


def test_sse_stream_replays_steps_and_ends():
    r = client.post("/api/runs", json={"agent_id": "scout", "task": SIMPLE_TASK})
    run_id = r.json()["run_id"]
    _wait(run_id)

    events = []
    with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if line.startswith("event: "):
                events.append(line[len("event: "):])
            if line.startswith("event: end"):
                break
    assert events.count("step") >= 10
    assert "status" in events
    assert events[-1] == "end"


def test_sse_after_parameter_is_incremental():
    r = client.post("/api/runs", params={"wait": 60},
                    json={"agent_id": "scout", "task": SIMPLE_TASK})
    run_id = r.json()["run_id"]
    steps = client.get(f"/api/runs/{run_id}/trace").json()["steps"]
    after = steps[5]["seq"]
    seen = []
    with client.stream("GET", f"/api/runs/{run_id}/events?after={after}") as resp:
        for line in resp.iter_lines():
            if line.startswith("data: ") and line != "data: {}":
                payload = json.loads(line[len("data: "):])
                if "seq" in payload:
                    seen.append(payload["seq"])
            if line == "event: end":
                break
    assert seen and min(seen) > after


def test_approval_flow_via_api():
    r = client.post("/api/runs", params={"wait": 60},
                    json={"agent_id": "scout", "task": GATED_TASK})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "awaiting_approval"
    run_id = body["run_id"]
    approval_id = body["pending_approval"]["approval_id"]

    r = client.get("/api/approvals?status=pending")
    assert any(a["id"] == approval_id for a in r.json())

    r = client.post(f"/api/runs/{run_id}/approve", params={"wait": 60},
                    json={"approval_id": approval_id, "note": "ok"})
    assert r.status_code == 202
    assert r.json()["status"] == "completed"
    assert r.json()["success"] is True

    # A second decision on the same approval is refused, not applied twice.
    r = client.post(f"/api/runs/{run_id}/approve",
                    json={"approval_id": approval_id, "note": "again"})
    assert r.status_code == 409


def test_approval_queue_endpoint_resumes_run():
    r = client.post("/api/runs", params={"wait": 60},
                    json={"agent_id": "scout", "task": GATED_TASK})
    approval_id = r.json()["pending_approval"]["approval_id"]
    r = client.post(f"/api/approvals/{approval_id}/approve",
                    params={"wait": 60}, json={"note": "from queue"})
    assert r.status_code == 202
    assert r.json()["status"] == "completed"


def test_replay_and_checkpoints_via_api():
    r = client.post("/api/runs", params={"wait": 60},
                    json={"agent_id": "scout", "task": SIMPLE_TASK})
    run_id = r.json()["run_id"]
    r = client.post(f"/api/runs/{run_id}/replay")
    assert r.status_code == 200
    assert r.json()["divergences"] == []
    assert r.json()["replayed_steps"] >= 4
    assert "execution" not in r.json()

    r = client.get(f"/api/runs/{run_id}/checkpoints")
    assert r.status_code == 200
    assert len(r.json()["checkpoints"]) >= 5


def test_replay_execute_reruns_and_compares():
    r = client.post("/api/runs", params={"wait": 60},
                    json={"agent_id": "scout", "task": SIMPLE_TASK})
    run_id = r.json()["run_id"]
    r = client.post(f"/api/runs/{run_id}/replay", json={"execute": True})
    assert r.status_code == 200
    execution = r.json()["execution"]
    assert execution["status"] == "completed"
    assert execution["matches"] is True
    assert execution["same_tool_sequence"] is True
    # The replay run is tagged so dashboard stats ignore it.
    replayed = client.get(f"/api/runs/{execution['run_id']}").json()
    assert replayed["version"].startswith("replay-")


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
    client.post("/api/runs", params={"wait": 60},
                json={"agent_id": "scout", "task": SIMPLE_TASK})
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


def test_validation_errors():
    assert client.post("/api/runs", json={"agent_id": "nope", "task": "x"}).status_code == 400
    assert client.post("/api/runs", json={"agent_id": "scout", "task": "   "}).status_code == 422
    assert client.get("/api/runs/run_missing").status_code == 404
    assert client.get("/api/runs/run_missing/events").status_code == 404
