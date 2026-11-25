"""Durable execution: a run survives a process restart.

The test starts a run that pauses at an approval gate, then throws
away every in-memory object (the cached checkpointer and graphs) and
rebuilds them from the same checkpoint file — simulating a process
restart. Resuming must work, because the state lives in
checkpoints.db, not in memory.
"""
from app import db
from app.agents import graphs
from app.agents.graphs import resume_run, run_agent


def _restart():
    """Simulate a process restart: drop all cached LangGraph objects."""
    graphs._checkpointer = None
    graphs._graphs = None


def test_run_survives_restart():
    r = run_agent(
        "scout",
        "Research vendor Acme Corp, compute the total for 50 seats at $49 each, save a summary, and update the CRM record with the quote.",
    )
    assert r["status"] == "awaiting_approval"
    approval = r["pending_approval"]
    assert approval["tool"] == "crm_update"

    # The process "restarts": all in-memory graph state is gone.
    _restart()

    # The checkpoint file still has the run. Resume it.
    resumed = resume_run(r["run_id"], approval["approval_id"], True, "approved after restart")
    assert resumed["status"] == "completed"
    assert resumed["success"] is True
    assert "crm_update" in resumed["result"]

    # The trace is intact across the restart.
    steps = db.get_trace(r["run_id"])
    assert len(steps) >= 10
    assert any(s["type"] == "gate" for s in steps)


def test_checkpoint_history_exists():
    r = run_agent(
        "scout",
        "Research vendor Acme Corp and compute the total for 10 seats at $19 each, then save a summary file.",
    )
    assert r["status"] == "completed"
    run = db.get_run(r["run_id"])
    graph = graphs.get_graphs()["scout"]
    cfg = {"configurable": {"thread_id": run["thread_id"]}}
    history = list(graph.get_state_history(cfg))
    # At least one checkpoint per node that ran.
    assert len(history) >= 5
