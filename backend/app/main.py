"""Warden — agent reliability platform API.

Durable agent execution (LangGraph + SQLite checkpoints), full trace
recording, human approval gates, persistent memory, and a nightly eval
suite that blocks deploy on regressions.
"""
import json

import datetime
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import analysis, config, db
from .agents.graphs import (
    AGENT_INFO,
    get_graphs,
    replay_run,
    resume_run,
    run_agent,
)
from .evals.suite import run_suite
from .memory import MemoryStore


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
    get_graphs()  # build graphs + checkpointer eagerly
    yield


app = FastAPI(title=config.PRODUCT_NAME, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_memory = MemoryStore()


# ---------- models ----------
class RunRequest(BaseModel):
    agent_id: str = "scout"
    task: str


class DecisionRequest(BaseModel):
    approval_id: str
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


class QuestCompleteRequest(BaseModel):
    note: str = ""


# ---------- health & agents ----------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "product": config.PRODUCT_NAME,
        "agents": [a["id"] for a in AGENT_INFO],
        "runs": db.count_runs(),
        "db": "sqlite",
        "model": "local-deterministic",
    }


@app.get("/api/agents")
def list_agents():
    return AGENT_INFO


# ---------- runs ----------
@app.post("/api/runs", status_code=201)
def start_run(req: RunRequest):
    if req.agent_id not in ("scout", "planner"):
        raise HTTPException(400, f"unknown agent: {req.agent_id}")
    return run_agent(req.agent_id, req.task)


@app.get("/api/runs")
def list_runs(agent_id: str | None = None, status: str | None = None, limit: int = 50):
    return [_serialise_run(r) for r in db.list_runs(agent_id, status, limit)]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
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


@app.get("/api/runs/{run_id}/trace")
def get_trace(run_id: str):
    if not db.get_run(run_id):
        raise HTTPException(404, "run not found")
    return {"run_id": run_id, "steps": [_serialise_step(s) for s in db.get_trace(run_id)]}


@app.post("/api/runs/{run_id}/approve")
def approve_run(run_id: str, req: DecisionRequest):
    result = resume_run(run_id, req.approval_id, True, req.note)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/api/runs/{run_id}/reject")
def reject_run(run_id: str, req: DecisionRequest):
    result = resume_run(run_id, req.approval_id, False, req.note)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/api/runs/{run_id}/replay")
def replay(run_id: str):
    result = replay_run(run_id)
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


@app.post("/api/approvals/{approval_id}/approve")
def approve_approval(approval_id: str, req: DecisionRequest | None = None):
    approval = db.get_approval(approval_id)
    if not approval:
        raise HTTPException(404, "approval not found")
    note = req.note if req else ""
    result = resume_run(approval["run_id"], approval_id, True, note)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/api/approvals/{approval_id}/reject")
def reject_approval(approval_id: str, req: DecisionRequest | None = None):
    approval = db.get_approval(approval_id)
    if not approval:
        raise HTTPException(404, "approval not found")
    note = req.note if req else ""
    result = resume_run(approval["run_id"], approval_id, False, note)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


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
