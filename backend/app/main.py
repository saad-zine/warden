"""Warden — agent reliability platform API.

Any-model execution (LangGraph + SQLite checkpoints) in a bounded worker
pool, SSE trace streaming, human approval gates, persistent memory, replay
you can re-execute, and an eval suite that blocks deploy on regressions.
"""
import datetime
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import analysis, config, db, llm, runner
from .agents.graphs import (
    AGENT_INFO,
    TERMINAL_STATUSES,
    get_graphs,
    replay_run,
)
from .evals.suite import run_suite
from .memory import MemoryStore

log = logging.getLogger("warden.api")


def _iso(ts):
    """Epoch seconds (float) -> ISO-8601 string; None stays None."""
    if ts is None:
        return None
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()


def _serialise_step(step):
    """Trace step: `ts` -> ISO string; `input`/`output` -> JSON strings."""
    s = dict(step)
    s["ts"] = _iso(step.get("ts"))
    for k in ("input", "output"):
        v = step.get(k)
        if isinstance(v, (dict, list)):
            s[k] = json.dumps(v)
        elif v is None:
            s[k] = ""
        else:
            s[k] = str(v)
    return s


def _serialise_run(run):
    r = dict(run)
    r["started_at"] = _iso(run.get("started_at"))
    r["ended_at"] = _iso(run.get("ended_at"))
    if r.get("trace"):
        r["trace"] = [_serialise_step(s) for s in r["trace"]]
    if r.get("pending_approval"):
        r["pending_approval"] = _serialise_approval(r["pending_approval"])
    return r


def _serialise_approval(a):
    out = dict(a)
    # `id` is the storage key; `approval_id` is the API name used by the
    # run detail and the decision endpoints. Expose both so clients never
    # have to guess which endpoint returns which.
    out["approval_id"] = a.get("id")
    out["created_at"] = _iso(a.get("created_at"))
    out["decided_at"] = _iso(a.get("decided_at"))
    return out


def _serialise_memory(m):
    out = dict(m)
    out["created_at"] = _iso(m.get("created_at"))
    out["updated_at"] = _iso(m.get("updated_at"))
    return out


def _serialise_eval(e):
    out = dict(e)
    out["started_at"] = _iso(e.get("started_at"))
    # Normalise scenarios to the API contract: each scenario carries a
    # numeric success_rate and notes as a single string.
    scenarios = []
    for s in e.get("scenarios") or []:
        s = dict(s)
        if "success_rate" not in s:
            s["success_rate"] = 1.0 if s.get("passed") else 0.0
        notes = s.get("notes")
        if isinstance(notes, list):
            s["notes"] = "; ".join(str(n) for n in notes)
        elif notes is None:
            s["notes"] = ""
        scenarios.append(s)
    out["scenarios"] = scenarios
    if "scenarios_passed" not in out:
        out["scenarios_passed"] = sum(1 for s in scenarios if s.get("passed"))
    if "scenarios_total" not in out:
        out["scenarios_total"] = len(scenarios)
    return out


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    db.seed_quests()
    recovered = db.recover_interrupted_runs()
    if recovered:
        log.warning("marked %d interrupted run(s) as failed after restart", len(recovered))
    get_graphs()  # build graphs + checkpointer eagerly
    info = llm.provider_info()
    log.info(
        "warden up: model=%s (%s) tools=%s workers=%d",
        info.get("provider"), info.get("model"), config.TOOL_MODE, config.WORKER_THREADS,
    )
    yield
    runner.shutdown()


app = FastAPI(title=config.PRODUCT_NAME, version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Give every request an id and a latency line in the log."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = int((time.perf_counter() - started) * 1000)
    response.headers["x-request-id"] = request_id
    log.info("%s %s %s -> %d (%dms)", request_id, request.method,
             request.url.path, response.status_code, elapsed)
    return response

_memory = MemoryStore()


# ---------- models ----------
class RunRequest(BaseModel):
    agent_id: str = "scout"
    task: str


class DecisionRequest(BaseModel):
    approval_id: str | None = None
    note: str = ""


class MemoryRequest(BaseModel):
    agent_id: str
    content: str
    category: str = "fact"


class MemoryUpdate(BaseModel):
    content: str | None = None
    category: str | None = None


class EvalRunRequest(BaseModel):
    candidate: str = "current"


class ReplayRequest(BaseModel):
    execute: bool = False


class QuestCompleteRequest(BaseModel):
    note: str = ""


# ---------- health & agents ----------
@app.get("/health")
def health():
    info = llm.provider_info()
    return {
        "status": "ok",
        "product": config.PRODUCT_NAME,
        "version": app.version,
        "agents": [a["id"] for a in AGENT_INFO],
        "runs": db.count_runs(),
        "db": "sqlite",
        "model": info.get("model"),
        "provider": info.get("provider"),
        "live_model": info.get("live", False),
        "tools": config.TOOL_MODE,
        "workers": config.WORKER_THREADS,
        "inflight": runner.inflight(),
    }


@app.get("/api/agents")
def list_agents():
    return AGENT_INFO


# ---------- runs ----------
def _run_detail(run_id):
    run = db.get_run(run_id)
    if not run:
        return None
    run["trace"] = db.get_trace(run_id)
    pending = [a for a in db.list_approvals("pending") if a["run_id"] == run_id]
    run["pending_approval"] = pending[0] if pending else None
    # Checkpoint count (from the LangGraph checkpoint DB).
    try:
        graph = get_graphs()[run["agent_id"]]
        cfg = {"configurable": {"thread_id": run["thread_id"]}}
        run["checkpoints"] = len(list(graph.get_state_history(cfg)))
    except Exception:
        run["checkpoints"] = 0
    return _serialise_run(run)


def _await_run(run_id, timeout):
    """Wait until the run has no worker left and is paused or terminal.

    Status alone is not enough: right after a decision the run is still
    `awaiting_approval` while the worker resumes it, and right after a
    start it is `queued`. The worker's in-flight flag is the signal that
    the transition has actually happened.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = db.get_run(run_id)
        if run and not runner.is_inflight(run_id):
            if run["status"] in TERMINAL_STATUSES or run["status"] == "awaiting_approval":
                break
        time.sleep(0.05)
    return _run_detail(run_id)


@app.post("/api/runs", status_code=202)
def start_run(req: RunRequest, wait: float = Query(0, ge=0, le=300)):
    """Queue a run. Returns 202 immediately; ?wait=N blocks up to N seconds.

    The synchronous form exists for curl demos and tests; the UI streams
    progress from /api/runs/{id}/events instead.
    """
    if req.agent_id not in ("scout", "planner"):
        raise HTTPException(400, f"unknown agent: {req.agent_id}")
    if not req.task.strip():
        raise HTTPException(422, "task must not be empty")
    queued = runner.start_run(req.agent_id, req.task)
    if wait:
        return _await_run(queued["run_id"], wait)
    return queued


@app.get("/api/runs")
def list_runs(agent_id: str | None = None, status: str | None = None, limit: int = 50):
    return [_serialise_run(r) for r in db.list_runs(agent_id, status, limit)]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    detail = _run_detail(run_id)
    if detail is None:
        raise HTTPException(404, "run not found")
    return detail


@app.get("/api/runs/{run_id}/trace")
def get_trace(run_id: str):
    if not db.get_run(run_id):
        raise HTTPException(404, "run not found")
    return {"run_id": run_id, "steps": [_serialise_step(s) for s in db.get_trace(run_id)]}


@app.get("/api/runs/{run_id}/events")
def run_events(run_id: str, after: int = 0):
    """Server-sent events: trace steps as they are written, then status.

    Reads from the database rather than an in-memory bus, so a client can
    reconnect (Last-Event-ID / ?after=) or attach late and still get the
    full history. Ends when the run is terminal or paused at a gate.
    """
    if not db.get_run(run_id):
        raise HTTPException(404, "run not found")

    def gen():
        last = after
        last_status = None
        yield "retry: 1000\n\n"
        while True:
            for step in db.get_trace_after(run_id, last):
                last = step["seq"]
                payload = json.dumps(_serialise_step(step))
                yield f"id: {last}\nevent: step\ndata: {payload}\n\n"
            run = db.get_run(run_id)
            status = run["status"] if run else "missing"
            if status != last_status:
                last_status = status
                payload = json.dumps({
                    "run_id": run_id,
                    "status": status,
                    "success": bool(run.get("success")) if run else False,
                })
                yield f"event: status\ndata: {payload}\n\n"
            if status in TERMINAL_STATUSES or status == "awaiting_approval":
                yield "event: end\ndata: {}\n\n"
                break
            time.sleep(config.STREAM_POLL_S)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _pending_approval_id(run_id):
    for a in db.list_approvals("pending"):
        if a["run_id"] == run_id:
            return a["id"]
    return None


def _decide_run(run_id, approval_id, approved, note, wait):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if run["status"] != "awaiting_approval":
        raise HTTPException(409, f"run is not awaiting approval (status={run['status']})")
    approval_id = approval_id or _pending_approval_id(run_id)
    if not approval_id:
        raise HTTPException(409, "no pending approval for this run")
    try:
        runner.submit_resume(run_id, approval_id, approved, note)
    except runner.RunBusy:
        raise HTTPException(409, "a decision is already being applied")
    if wait:
        return _await_run(run_id, wait)
    return {"run_id": run_id, "status": "resuming", "approval_id": approval_id}


@app.post("/api/runs/{run_id}/approve", status_code=202)
def approve_run(run_id: str, req: DecisionRequest | None = None,
                wait: float = Query(0, ge=0, le=300)):
    req = req or DecisionRequest()
    return _decide_run(run_id, req.approval_id, True, req.note, wait)


@app.post("/api/runs/{run_id}/reject", status_code=202)
def reject_run(run_id: str, req: DecisionRequest | None = None,
               wait: float = Query(0, ge=0, le=300)):
    req = req or DecisionRequest()
    return _decide_run(run_id, req.approval_id, False, req.note, wait)


@app.post("/api/runs/{run_id}/replay")
def replay(run_id: str, req: ReplayRequest | None = None):
    result = replay_run(run_id, execute=bool(req and req.execute))
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.get("/api/runs/{run_id}/checkpoints")
def checkpoints(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    out = []
    try:
        graph = get_graphs()[run["agent_id"]]
        cfg = {"configurable": {"thread_id": run["thread_id"]}}
        for snap in graph.get_state_history(cfg):
            meta = snap.metadata or {}
            out.append({
                "checkpoint_id": str(snap.config["configurable"].get("checkpoint_id", "")),
                "step": meta.get("step"),
                "source": meta.get("source"),
                "ts": meta.get("created_at"),
            })
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"run_id": run_id, "checkpoints": out}


# ---------- approvals ----------
@app.get("/api/approvals")
def list_approvals(status: str | None = None):
    return [_serialise_approval(a) for a in db.list_approvals(status)]


@app.post("/api/approvals/{approval_id}/approve", status_code=202)
def approve_approval(approval_id: str, req: DecisionRequest | None = None,
                     wait: float = Query(0, ge=0, le=300)):
    approval = db.get_approval(approval_id)
    if not approval:
        raise HTTPException(404, "approval not found")
    note = req.note if req else ""
    return _decide_run(approval["run_id"], approval_id, True, note, wait)


@app.post("/api/approvals/{approval_id}/reject", status_code=202)
def reject_approval(approval_id: str, req: DecisionRequest | None = None,
                    wait: float = Query(0, ge=0, le=300)):
    approval = db.get_approval(approval_id)
    if not approval:
        raise HTTPException(404, "approval not found")
    note = req.note if req else ""
    return _decide_run(approval["run_id"], approval_id, False, note, wait)


# ---------- memory ----------
@app.get("/api/memory")
def list_memory(agent_id: str | None = None):
    return [_serialise_memory(m) for m in _memory.list(agent_id)]


@app.post("/api/memory", status_code=201)
def add_memory(req: MemoryRequest):
    mid = _memory.add(req.agent_id, req.content, req.category)
    return {"id": mid, "agent_id": req.agent_id,
            "content": req.content, "category": req.category}


@app.put("/api/memory/{mid}")
def update_memory(mid: str, req: MemoryUpdate):
    _memory.update(mid, req.content, req.category)
    return {"id": mid, "content": req.content, "category": req.category}


@app.delete("/api/memory/{mid}", status_code=204)
def delete_memory(mid: str):
    _memory.delete(mid)
    return None


# ---------- evals ----------
@app.get("/api/evals")
def list_evals():
    return [_serialise_eval(e) for e in db.list_evals()]


@app.post("/api/evals/run")
def run_eval(req: EvalRunRequest):
    if req.candidate not in ("current", "degraded"):
        raise HTTPException(400, "candidate must be 'current' or 'degraded'")
    return run_suite(req.candidate)


@app.get("/api/evals/{eval_id}")
def get_eval(eval_id: str):
    ev = db.get_eval(eval_id)
    if not ev:
        raise HTTPException(404, "eval not found")
    return _serialise_eval(ev)


# ---------- stats / analysis / gamification ----------
@app.get("/api/stats")
def stats():
    return analysis.dashboard_stats()


@app.get("/api/failure-modes")
def failure_modes():
    modes = analysis.failure_modes()
    quests = {q["failure_mode"]: q for q in db.list_quests()}
    for m in modes:
        q = quests.get(m["mode"])
        if q is None:
            # Every failure mode gets a quest, even one nobody seeded:
            # a generic quest derived from the mode, so the UI contract
            # ("each mode has a quest with XP") always holds.
            q = {
                "id": "q_auto_" + "".join(c if c.isalnum() else "_" for c in m["mode"])[:40],
                "title": f"Fix: {m['mode']}",
                "description": "A run failed with this mode. Investigate the trace and harden the agent against it.",
                "failure_mode": m["mode"],
                "xp": 100,
                "status": "open",
            }
        m["quest"] = q
        m["last_seen"] = _iso(m.get("last_seen"))
    return modes


@app.get("/api/leaderboard")
def leaderboard():
    return analysis.leaderboard()


@app.get("/api/quests")
def quests():
    return db.list_quests()


@app.post("/api/quests/{quest_id}/complete")
def complete_quest(quest_id: str, req: QuestCompleteRequest | None = None):
    q = db.complete_quest(quest_id)
    if not q:
        raise HTTPException(404, "quest not found")
    total_xp = int(db.kv_get("total_xp", "0") or "0") + q["xp"]
    db.kv_set("total_xp", str(total_xp))
    if total_xp >= 500:
        level = "Production-grade"
    elif total_xp >= 250:
        level = "Battle-tested"
    elif total_xp >= 100:
        level = "Hardening"
    else:
        level = "Fragile"
    return {
        "quest_id": quest_id,
        "xp_awarded": q["xp"],
        "total_xp": total_xp,
        "level": level,
    }


# ---------- eval dataset (built from real traces) ----------
@app.get("/api/eval-dataset")
def eval_dataset():
    return analysis.build_eval_dataset_from_traces()


# ---------- single-origin deploy: serve the dashboard frontend ----------
# The React build (frontend/dist) is served from this same origin, so the
# dashboard's API calls are relative (/api/...) and work behind any host
# or tunnel without a separate frontend server. Only mounted when the
# build exists; the API above always takes precedence.
from fastapi.staticfiles import StaticFiles  # noqa: E402

_FRONTEND_DIST = config.BACKEND_DIR.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
