"""Scout agent graph (ReAct loop with a human approval gate).

Graph: setup -> agent -> (gate | tools | finalize)
                 ^           |        |
                 +-----------+--------+
Gate: if the next tool needs approval, the graph PAUSES via
langgraph.types.interrupt() and waits for a human decision. On resume
the decision is injected and the graph continues. This is the canonical
LangGraph human-in-the-loop pattern, backed by a SQLite checkpointer,
so execution survives a restart and can resume from the checkpoint.
"""
import time
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from .. import config as app_config
from .model import derive_plan, estimate_cost


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    task: str
    agent_id: str
    iterations: int
    pending_tool: dict | None
    gate_decision: dict | None
    result: str
    status: str
    failure_reason: str
    cost_usd: float
    tokens: int
    force_finalize: bool
    success: bool
    plan: list


def _cfg(config):
    return config["configurable"]


def _loop_detected(messages, threshold=3):
    """True if the same tool was called `threshold` times in a row."""
    recent = [
        getattr(m, "name", "") for m in messages
        if isinstance(m, ToolMessage)
    ][-threshold:]
    return len(recent) == threshold and len(set(recent)) == 1


def setup_node(state, config):
    cfg = _cfg(config)
    tracer = cfg["tracer"]
    started = time.time()
    memory = cfg["memory_store"]
    found = memory.retrieve(state["task"], agent_id=state["agent_id"], k=3)
    tracer.log_memory(
        "memory_retrieve",
        {"query": state["task"], "agent_id": state["agent_id"]},
        {"memories": [m["content"] for m in found]},
    )
    ctx = ""
    if found:
        ctx = "Relevant memories:\n" + "\n".join(
            f"- {m['content']} ({m.get('category', 'fact')})" for m in found
        )
    tracer.log_node("setup", {"task": state["task"]},
                    {"memories_found": len(found)},
                    duration_ms=int((time.time() - started) * 1000))
    msgs = []
    if ctx:
        msgs.append(SystemMessage(content=ctx))
    return {"messages": msgs}


def agent_node(state, config):
    cfg = _cfg(config)
    tracer = cfg["tracer"]
    model = cfg["model"]
    started = time.time()
    iterations = state.get("iterations", 0) + 1
    # Spend limit.
    if state.get("cost_usd", 0) > cfg.get("max_cost", app_config.MAX_COST_USD_PER_RUN):
        tracer.log_node("agent", {"task": state["task"]},
                        {"halt": "spend_limit"},
                        duration_ms=int((time.time() - started) * 1000),
                        status="error")
        return {
            "iterations": iterations,
            "result": "Failed: spend limit reached.",
            "status": "failed",
            "failure_reason": "spend_limit",
            "force_finalize": True,
        }
    # Loop detection.
    if _loop_detected(state["messages"]):
        tracer.log_node("agent", {"task": state["task"]},
                        {"halt": "loop_detected"},
                        duration_ms=int((time.time() - started) * 1000),
                        status="error")
        return {
            "iterations": iterations,
            "result": "Failed: loop detected — the same tool was called repeatedly.",
            "status": "failed",
            "failure_reason": "loop_detected",
            "force_finalize": True,
        }
    # Iteration cap.
    if iterations > cfg.get("max_iterations", app_config.MAX_ITERATIONS):
        tracer.log_node("agent", {"task": state["task"]},
                        {"halt": "max_iterations"},
                        duration_ms=int((time.time() - started) * 1000),
                        status="error")
        return {
            "iterations": iterations,
            "result": "Failed: maximum iterations reached.",
            "status": "failed",
            "failure_reason": "max_iterations",
            "force_finalize": True,
        }
    ai = model.invoke(state["messages"])
    usage = getattr(ai, "usage_metadata", {}) or {}
    in_tok = usage.get("input_tokens", 0)
    out_tok = usage.get("output_tokens", 0)
    cost = estimate_cost(in_tok, out_tok)
    tokens = in_tok + out_tok
    tracer.log_llm(
        "model_decide",
        {"messages": len(state["messages"])},
        {"content": ai.content, "tool_calls": getattr(ai, "tool_calls", [])},
        tokens=tokens, cost_usd=cost,
    )
    update = {
        "iterations": iterations,
        "messages": [ai],
        "cost_usd": state.get("cost_usd", 0) + cost,
        "tokens": state.get("tokens", 0) + tokens,
    }
    tool_calls = getattr(ai, "tool_calls", []) or []
    if tool_calls:
        call = tool_calls[0]
        update["pending_tool"] = {
            "name": call["name"],
            "args": call["args"],
            "call_id": call["id"],
        }
    else:
        update["pending_tool"] = None
        update["result"] = ai.content
    return update


def route_after_agent(state):
    if state.get("force_finalize"):
        return "finalize"
    pending = state.get("pending_tool")
    if not pending:
        return "finalize"
    if pending["name"] in app_config.TOOLS_NEEDING_APPROVAL:
        return "gate"
    return "tools"


def gate_node(state, config):
    cfg = _cfg(config)
    tracer = cfg["tracer"]
    guardrail = cfg["guardrail"]
    pending = state["pending_tool"]
    decision_info = guardrail.decide(pending["name"], pending["args"])
    # NOTE: the "approval_gate" (awaiting) trace step is logged by
    # _handle_interrupt in graphs.py when the pause is detected, NOT
    # here — because LangGraph re-executes this node from the start on
    # resume, logging here would duplicate the step.
    # PAUSE here until a human decides. interrupt() raises internally
    # and the checkpointer saves the state; on resume it returns the
    # decision dict {"approved": bool, "note": str}.
    decision = interrupt({
        "tool": pending["name"],
        "args": pending["args"],
        "policy_refs": decision_info["policy_refs"],
    })
    approved = bool(decision.get("approved"))
    tracer.log_gate(
        "approval_decision",
        {"tool": pending["name"]},
        {"approved": approved, "note": decision.get("note", "")},
        status="ok" if approved else "rejected",
    )
    if approved:
        return {"gate_decision": {"approved": True, "note": decision.get("note", "")}}
    # Rejected: tell the model (as a message) never to call this tool again.
    note = (
        f"[APPROVAL REJECTED] {pending['name']}: "
        f"{decision.get('note') or 'a human rejected this action'}. "
        f"Do not call this tool again; continue with the remaining steps."
    )
    return {
        "gate_decision": {"approved": False, "note": decision.get("note", "")},
        "messages": [HumanMessage(content=note)],
    }


def route_after_gate(state):
    decision = state.get("gate_decision") or {}
    return "tools" if decision.get("approved") else "agent"


def tools_node(state, config):
    cfg = _cfg(config)
    tracer = cfg["tracer"]
    tools = cfg["tools"]
    pending = state["pending_tool"]
    started = time.time()
    tool = tools[pending["name"]]
    try:
        output = tool.invoke(pending["args"])
        status = "ok"
    except Exception as e:
        # Use json.dumps (not an f-string): the error text can contain
        # newlines/quotes, which would make the JSON unparseable and the
        # model would misread the failure as a success.
        import json as _json
        output = _json.dumps({"error": str(e)})
        status = "error"
    # The tool itself already logged to the trace via the tracer; here
    # we record the node-level step.
    tracer.log_node(
        "tools", {"tool": pending["name"], "args": pending["args"]},
        {"output": output[:500], "status": status},
        duration_ms=int((time.time() - started) * 1000),
        status=status,
    )
    msg = ToolMessage(
        content=output,
        tool_call_id=pending["call_id"],
        name=pending["name"],
    )
    return {"messages": [msg], "pending_tool": None}


def finalize_node(state, config):
    cfg = _cfg(config)
    tracer = cfg["tracer"]
    started = time.time()
    import json

    failure = state.get("failure_reason", "")
    result = state.get("result", "")
    if failure:
        success = False
        result = result or f"Failed: {failure}."
        status = "failed"
    else:
        plan = derive_plan(state["task"])
        completed = set()
        error_count = {}
        rejected = set()
        for m in state["messages"]:
            if isinstance(m, ToolMessage):
                name = getattr(m, "name", "")
                try:
                    parsed = json.loads(m.content)
                    has_error = isinstance(parsed, dict) and "error" in parsed
                except Exception:
                    has_error = False
                if has_error:
                    error_count[name] = error_count.get(name, 0) + 1
                else:
                    completed.add(name)
            elif isinstance(m, HumanMessage) and isinstance(m.content, str) \
                    and m.content.startswith("[APPROVAL REJECTED]"):
                rejected.add(m.content.split("]")[1].strip().split(":")[0].strip())
        failed = {t for t, c in error_count.items() if c >= 2}
        missing = [s["tool"] for s in plan if s["tool"] not in completed]
        if any(t in rejected for t in missing):
            success = False
            status = "blocked"
            failure = "approval_rejected"
            result = result or "Blocked: a human rejected a required action."
        elif any(t in failed for t in missing):
            success = False
            status = "failed"
            failure = "tool_failed"
            result = result or "Failed: a required tool kept failing."
        elif missing and "cannot complete" in result.lower():
            success = False
            status = "blocked"
            failure = "missing_tool"
        else:
            success = True
            status = "completed"
    tracer.log_node("finalize", {"task": state["task"]},
                    {"status": status, "success": success, "result": result[:500]},
                    duration_ms=int((time.time() - started) * 1000),
                    status="ok" if success else "error")
    return {
        "result": result,
        "status": status,
        "failure_reason": failure,
        "success": success,
    }


def build_scout_graph(checkpointer):
    graph = StateGraph(AgentState)
    graph.add_node("setup", setup_node)
    graph.add_node("agent", agent_node)
    graph.add_node("gate", gate_node)
    graph.add_node("tools", tools_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "setup")
    graph.add_edge("setup", "agent")
    graph.add_conditional_edges("agent", route_after_agent,
                                {"gate": "gate", "tools": "tools", "finalize": "finalize"})
    graph.add_conditional_edges("gate", route_after_gate,
                                {"tools": "tools", "agent": "agent"})
    graph.add_edge("tools", "agent")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
