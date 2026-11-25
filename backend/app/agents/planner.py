"""Planner agent graph (multi-agent handoff).

Graph: planner -> executor (Scout subgraph) -> summarizer

The Planner decomposes the task into an explicit plan, hands the plan
and the task to the Executor (the Scout graph, embedded as a subgraph —
a separate compiled agent sharing the same state and checkpointer), and
the Summarizer verifies that every planned step has a corresponding
tool result in the trace and produces the final summary. The handoff is
real: two agents, shared state, one checkpointed thread. An approval
gate inside the Executor pauses the whole Planner run too (the
interrupt propagates through the subgraph).
"""
import time

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from .model import _build_tool_args, derive_plan
from .scout import AgentState, build_scout_graph


def planner_node(state, config):
    cfg = config["configurable"]
    tracer = cfg["tracer"]
    started = time.time()
    steps = derive_plan(state["task"])
    plan = []
    for step in steps:
        args = _build_tool_args(step["tool"], state["task"], state["messages"])
        plan.append({"tool": step["tool"], "args": args, "why": step["why"], "status": "planned"})
    tracer.log_node(
        "planner",
        {"task": state["task"]},
        {"plan": [{"tool": p["tool"], "why": p["why"]} for p in plan]},
        duration_ms=int((time.time() - started) * 1000),
    )
    plan_text = "Plan:\n" + "\n".join(
        f"{i+1}. {p['tool']} — {p['why']}" for i, p in enumerate(plan)
    )
    return {
        "plan": plan,
        "messages": [HumanMessage(content=f"[PLAN] {plan_text}")],
    }


def summarizer_node(state, config):
    cfg = config["configurable"]
    tracer = cfg["tracer"]
    started = time.time()
    from langchain_core.messages import ToolMessage
    import json

    completed = set()
    for m in state["messages"]:
        if isinstance(m, ToolMessage):
            try:
                parsed = json.loads(m.content)
                if not (isinstance(parsed, dict) and "error" in parsed):
                    completed.add(getattr(m, "name", ""))
            except Exception:
                completed.add(getattr(m, "name", ""))
    plan = state.get("plan") or []
    covered = [p["tool"] for p in plan if p["tool"] in completed]
    missing = [p["tool"] for p in plan if p["tool"] not in completed]
    summary = (
        f"Planner summary: {len(covered)}/{len(plan)} planned steps executed "
        f"({', '.join(covered) or 'none'})."
    )
    if missing:
        summary += f" Not executed: {', '.join(missing)}."
    summary += f" Executor result: {state.get('result', '')[:300]}"
    tracer.log_node(
        "summarizer",
        {"plan_steps": len(plan)},
        {"covered": covered, "missing": missing},
        duration_ms=int((time.time() - started) * 1000),
    )
    # The executor already set status/success; the summarizer only
    # enriches the result text.
    return {"result": summary}


def build_planner_graph(checkpointer):
    scout = build_scout_graph(checkpointer)
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("executor", scout)
    graph.add_node("summarizer", summarizer_node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "summarizer")
    graph.add_edge("summarizer", END)
    return graph.compile(checkpointer=checkpointer)
