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
import json
import sqlite3
import time

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .. import config, db
from ..guardrail import Guardrail
from ..memory import MemoryStore
from ..trace import Tracer
from .model import DeterministicModel, derive_plan
from .planner import build_planner_graph
from .scout import build_scout_graph
from .tools import TOOL_NAMES, make_tools

_checkpointer = None
_graphs = None


def get_checkpointer():
    global _checkpointer
    if _checkpointer is None:
        # SqliteSaver takes a live connection (from_conn_string returns a
        # context manager, which is wrong for a long-lived app).
        conn = sqlite3.connect(config.CHECKPOINT_DB, check_same_thread=False)
        _checkpointer = SqliteSaver(conn)
    return _checkpointer


def get_graphs():
    global _graphs
    if _graphs is None:
        cp = get_checkpointer()
        _graphs = {
            "scout": build_scout_graph(cp),
            "planner": build_planner_graph(cp),
        }
    return _graphs


def _build_config(run_id, thread_id, agent_id, tracer, behaviour, tool_names):
    tools = make_tools(behaviour, tracer)
    if tool_names is not None:
        tools = [t for t in tools if t.name in tool_names]
    model = DeterministicModel(available_tools=[t.name for t in tools])
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
              auto_decision=None, version="1.0.0"):
    """Start a run. Returns a summary dict (with pending_approval if paused).

    auto_decision: None = pause for a human at the first approval gate;
    "approve" = auto-approve every gate (used by evals);
    "reject" = auto-reject every gate (used by evals).
    """
    behaviour = behaviour or {}
    run_id = db.new_id("run")
    thread_id = db.new_id("th")
    started = time.time()
    db.create_run(run_id, thread_id, agent_id, task, version)
    tracer = Tracer(run_id)
    cfg = _build_config(run_id, thread_id, agent_id, tracer, behaviour, tool_names)
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
    db.decide_approval(approval_id, "approved" if approved else "rejected",
                       decided_by="human", note=note)
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


def replay_run(run_id):
    """Verify the recorded trace against the current agent plan and list
    the checkpoint history for the thread. No side effects: nothing is
    re-executed."""
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
    return {
        "run_id": run_id,
        "replayed_steps": len(tool_steps),
        "expected_plan": expected,
        "recorded_tools": recorded,
        "divergences": divergences,
        "checkpoints": checkpoints,
    }


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
