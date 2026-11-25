"""Graph runner: builds the LangGraph graphs once (with a SQLite
checkpointer) and runs / resumes / replays them.

- run_agent: start a run. If the agent hits an approval gate, the run
  pauses (LangGraph interrupt) and an approval record is created; the
  API returns `awaiting_approval`.
- resume_run: resume a paused run with a human decision (approve/reject).
  The graph continues from the checkpoint — this is durable execution:
  the run survives a process restart because the state lives in
  checkpoints.db.
- replay_run: verify the recorded trace against the current agent plan
  and list the checkpoint history (state snapshots) for the thread.
"""
import sqlite3
import threading
import time

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .. import config, db, llm
from ..guardrail import Guardrail
from ..memory import MemoryStore
from ..trace import Tracer
from .model import derive_plan
from .planner import build_planner_graph
from .scout import build_scout_graph
from .tools import make_tools

# LangGraph compiles a checkpointer into the graph, and SqliteSaver owns a
# single sqlite3 connection. Neither is safe to share across threads, so
# each worker thread gets its own checkpointer + compiled graphs. SQLite is
# in WAL mode with a busy timeout, so concurrent runs from the worker pool
# serialise writes instead of corrupting or blocking forever.
_local = threading.local()

TERMINAL_STATUSES = {"completed", "failed", "blocked", "interrupted"}


def _new_checkpointer():
    conn = sqlite3.connect(
        config.CHECKPOINT_DB, check_same_thread=False, timeout=30
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return SqliteSaver(conn)


def get_checkpointer():
    """This thread's checkpointer (created on first use)."""
    cp = getattr(_local, "checkpointer", None)
    if cp is None:
        cp = _new_checkpointer()
        _local.checkpointer = cp
    return cp


def get_graphs():
    """This thread's compiled graphs (created on first use)."""
    graphs = getattr(_local, "graphs", None)
    if graphs is None:
        cp = get_checkpointer()
        graphs = {
            "scout": build_scout_graph(cp),
            "planner": build_planner_graph(cp),
        }
        _local.graphs = graphs
    return graphs


def reset_caches():
    """Drop cached graphs/checkpointers for the current thread.

    Used by tests to simulate a process restart, and by any code that
    changes the checkpoint database path at runtime.
    """
    _local.checkpointer = None
    _local.graphs = None


def _build_config(run_id, thread_id, agent_id, tracer, behaviour, tool_names,
                  provider=None, tool_mode=None):
    tools = make_tools(behaviour, tracer, mode=tool_mode)
    if tool_names is not None:
        tools = [t for t in tools if t.name in tool_names]
    model = llm.build_chat_model(tools, provider=provider)
    return {
        "configurable": {
            "thread_id": thread_id,
            "tracer": tracer,
            "guardrail": Guardrail(),
            "memory_store": MemoryStore(),
            "tools": {t.name: t for t in tools},
            "model": model,
            "run_id": run_id,
            "agent_id": agent_id,
            "max_cost": config.MAX_COST_USD_PER_RUN,
            "max_tokens": config.MAX_TOKENS_PER_RUN,
            "max_iterations": config.MAX_ITERATIONS,
        }
    }


def _initial_state(task, agent_id):
    return {
        "messages": [HumanMessage(content=task)],
        "task": task,
        "agent_id": agent_id,
        "iterations": 0,
        "pending_tool": None,
        "gate_decision": None,
        "result": "",
        "status": "running",
        "failure_reason": "",
        "cost_usd": 0.0,
        "tokens": 0,
        "force_finalize": False,
        "success": False,
        "plan": [],
    }


def _finish_run(run_id, result_state, started):
    duration_ms = int((time.time() - started) * 1000)
    db.update_run(
        run_id,
        status=result_state.get("status", "completed"),
        success=1 if result_state.get("success") else 0,
        result=result_state.get("result", "")[:2000],
        failure_reason=result_state.get("failure_reason", ""),
        cost_usd=result_state.get("cost_usd", 0.0),
        tokens=result_state.get("tokens", 0),
        duration_ms=duration_ms,
        ended_at=time.time(),
    )
    return {
        "run_id": run_id,
        "status": result_state.get("status", "completed"),
        "success": bool(result_state.get("success")),
        "result": result_state.get("result", ""),
        "cost_usd": round(result_state.get("cost_usd", 0.0), 6),
        "tokens": result_state.get("tokens", 0),
        "duration_ms": duration_ms,
    }


def _handle_interrupt(run_id, agent_id, result_state, tracer):
    """The graph paused at an approval gate. Record the approval and
    log the gate step (logged here, not in the gate node, because
    LangGraph re-executes the gate node on resume and would duplicate it)."""
    interrupts = result_state.get("__interrupt__") or []
    if not interrupts:
        return None
    payload = interrupts[0].value
    tracer.log_gate(
        "approval_gate",
        {"tool": payload.get("tool", ""), "args": payload.get("args", {})},
        {"needs_approval": True, "policy_refs": payload.get("policy_refs", [])},
        status="awaiting_approval",
    )
    approval_id = db.new_id("apr")
    db.create_approval(
        approval_id, run_id, agent_id,
        payload.get("tool", ""), payload.get("args", {}),
        payload.get("policy_refs", []),
    )
    db.update_run(run_id, status="awaiting_approval")
    return {
        "approval_id": approval_id,
        "tool": payload.get("tool", ""),
        "args": payload.get("args", {}),
        "policy_refs": payload.get("policy_refs", []),
    }


def run_agent(agent_id, task, behaviour=None, tool_names=None,
              auto_decision=None, version="1.0.0",
              run_id=None, thread_id=None, precreated=False,
              provider=None, tool_mode=None):
    """Start a run. Returns a summary dict (with pending_approval if paused).

    auto_decision: None = pause for a human at the first approval gate;
    "approve" = auto-approve every gate (used by evals);
    "reject" = auto-reject every gate (used by evals).

    thread_id / run_id / precreated let the background runner create the
    row first (so the API can return immediately) and then execute here.
    provider / tool_mode override configuration for evals and replay.
    """
    behaviour = behaviour or {}
    run_id = run_id or db.new_id("run")
    thread_id = thread_id or db.new_id("th")
    started = time.time()
    provider_name = provider or llm.resolve_provider()
    model_id = llm.model_name(provider_name)
    if precreated:
        db.update_run(run_id, status="running", provider=provider_name, model=model_id,
                      started_at=time.time())
    else:
        db.create_run(run_id, thread_id, agent_id, task, version,
                      provider=provider_name, model=model_id)
    tracer = Tracer(run_id)
    tracer.log_node(
        "model_config",
        {"agent_id": agent_id},
        {"provider": provider_name, "model": model_id,
         "tools": tool_mode or config.TOOL_MODE},
    )
    try:
        cfg = _build_config(run_id, thread_id, agent_id, tracer, behaviour,
                            tool_names, provider=provider_name,
                            tool_mode=tool_mode)
    except llm.ModelConfigError as e:
        tracer.log_node("model_config", {"agent_id": agent_id},
                        {"error": str(e)}, status="error")
        db.update_run(run_id, status="failed", success=0,
                      result=f"Failed: model unavailable — {e}",
                      failure_reason="model_config", ended_at=time.time(),
                      duration_ms=int((time.time() - started) * 1000))
        return {
            "run_id": run_id,
            "status": "failed",
            "success": False,
            "result": f"Failed: model unavailable — {e}",
            "cost_usd": 0.0,
            "tokens": 0,
            "duration_ms": int((time.time() - started) * 1000),
        }
    graph = get_graphs()[agent_id]
    result_state = graph.invoke(_initial_state(task, agent_id), cfg)
    # Auto-decision loop (used by the eval suite): keep resuming while
    # the agent hits approval gates, recording each auto-decision.
    while True:
        pending = _handle_interrupt(run_id, agent_id, result_state, tracer)
        if pending is None:
            break
        if auto_decision is None:
            return {
                "run_id": run_id,
                "thread_id": thread_id,
                "status": "awaiting_approval",
                "pending_approval": pending,
            }
        approved = auto_decision == "approve"
        db.decide_approval(pending["approval_id"],
                           "approved" if approved else "rejected",
                           decided_by=f"eval-auto-{auto_decision}",
                           note=f"auto-{auto_decision} by eval")
        result_state = graph.invoke(
            Command(resume={"approved": approved,
                            "note": f"auto-{auto_decision} by eval"}),
            cfg,
        )
    return _finish_run(run_id, result_state, started)


def resume_run(run_id, approval_id, approved, note=""):
    """Resume a paused run with a human decision."""
    run = db.get_run(run_id)
    if not run:
        return {"error": "run not found"}
    if run["status"] != "awaiting_approval":
        return {"error": f"run is not awaiting approval (status={run['status']})"}
    approval = db.get_approval(approval_id)
    if not approval:
        return {"error": "approval not found"}
    if approval["status"] != "pending":
        return {"error": f"approval already {approval['status']}"}
    changed = db.decide_approval(approval_id, "approved" if approved else "rejected",
                                 decided_by="human", note=note)
    if not changed:
        return {"error": "approval already decided"}
    started = time.time()
    tracer = Tracer(run_id)
    cfg = _build_config(run_id, run["thread_id"], run["agent_id"], tracer, {}, None)
    graph = get_graphs()[run["agent_id"]]
    result_state = graph.invoke(
        Command(resume={"approved": approved, "note": note}),
        cfg,
    )
    while True:
        pending = _handle_interrupt(run_id, run["agent_id"], result_state, tracer)
        if pending is None:
            break
        return {
            "run_id": run_id,
            "status": "awaiting_approval",
            "pending_approval": pending,
        }
    return _finish_run(run_id, result_state, started)


def replay_run(run_id, execute=False):
    """Verify the recorded trace against the current plan, and optionally
    re-execute the task against the current agent to prove it reproduces.

    Static mode has no side effects. `execute=True` really runs the agent
    again (version "replay-*", excluded from dashboard stats), auto-deciding
    gates the way the original run was decided, then compares the tool
    sequence and outcome.
    """
    run = db.get_run(run_id)
    if not run:
        return {"error": "run not found"}
    steps = db.get_trace(run_id)
    tool_steps = [s for s in steps if s["type"] == "tool"]
    recorded = [s["name"] for s in tool_steps]
    plan = derive_plan(run["task"])
    expected = [s["tool"] for s in plan]
    divergences = []
    for i, tool in enumerate(expected):
        if i >= len(recorded):
            divergences.append(f"missing step: {tool} was planned but never ran")
        elif recorded[i] != tool:
            divergences.append(
                f"step {i+1}: expected {tool}, recorded {recorded[i]}"
            )
    for tool in recorded[len(expected):]:
        divergences.append(f"extra step: {tool} ran but was not in the plan")
    failed = [s["name"] for s in tool_steps if s["status"] == "error"]
    if failed:
        divergences.append(f"failed tools: {', '.join(sorted(set(failed)))}")
    # Checkpoint history (LangGraph state snapshots for this thread).
    checkpoints = []
    try:
        graph = get_graphs()[run["agent_id"]]
        cfg = {"configurable": {"thread_id": run["thread_id"]}}
        for snap in graph.get_state_history(cfg):
            meta = snap.metadata or {}
            checkpoints.append({
                "checkpoint_id": str(snap.config["configurable"].get("checkpoint_id", "")),
                "step": meta.get("step"),
                "source": meta.get("source"),
                "writes": list((snap.metadata or {}).get("writes", {}).keys()) if isinstance((snap.metadata or {}).get("writes"), dict) else [],
            })
    except Exception as e:
        checkpoints = [{"error": str(e)}]
    out = {
        "run_id": run_id,
        "replayed_steps": len(tool_steps),
        "expected_plan": expected,
        "recorded_tools": recorded,
        "divergences": divergences,
        "checkpoints": checkpoints,
    }

    if execute:
        decisions = [a for a in db.list_approvals() if a["run_id"] == run_id]
        auto = "reject" if any(a["status"] == "rejected" for a in decisions) else "approve"
        again = run_agent(
            run["agent_id"], run["task"], auto_decision=auto,
            version=f"replay-{run.get('version') or '1.0.0'}",
        )
        again_tools = [s["name"] for s in db.get_trace(again["run_id"])
                       if s["type"] == "tool"]
        out["execution"] = {
            "run_id": again["run_id"],
            "status": again.get("status"),
            "success": bool(again.get("success")),
            "tools": again_tools,
            "same_tool_sequence": again_tools == recorded,
            "same_outcome": bool(again.get("success")) == bool(run.get("success")),
            "cost_usd": again.get("cost_usd"),
            "duration_ms": again.get("duration_ms"),
            "matches": again_tools == recorded
                       and bool(again.get("success")) == bool(run.get("success")),
        }
    return out


AGENT_INFO = [
    {
        "id": "scout",
        "name": "Scout",
        "description": "Research and operations agent: searches, fetches, computes, saves files, and updates the CRM — with a human approval gate on risky actions.",
        "tools": ["web_search", "web_fetch", "calculator", "file_writer", "crm_lookup", "crm_update"],
        "version": "1.0.0",
    },
    {
        "id": "planner",
        "name": "Planner",
        "description": "Multi-agent: a planner decomposes the task into a plan, hands it to the Scout executor, and verifies every planned step was executed.",
        "tools": ["web_search", "web_fetch", "calculator", "file_writer", "crm_lookup", "crm_update"],
        "version": "1.0.0",
    },
]
