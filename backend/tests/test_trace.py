"""Trace recording + spend limit + loop detection."""
from app import config, db
from app.agents.graphs import run_agent


def test_trace_records_every_step():
    r = run_agent(
        "scout",
        "Research vendor Acme Corp and compute the total for 50 seats at $49 each, then save a summary file.",
    )
    assert r["status"] == "completed"
    steps = db.get_trace(r["run_id"])
    types = [s["type"] for s in steps]
    assert "memory" in types
    assert "llm" in types
    assert "tool" in types
    assert "node" in types
    # Tool steps carry inputs, outputs, timing, and cost.
    tool_steps = [s for s in steps if s["type"] == "tool"]
    assert len(tool_steps) == 4
    for s in tool_steps:
        assert s["input"] is not None
        assert s["output"] is not None
        assert s["duration_ms"] >= 0
        assert s["status"] == "ok"
    # Sequence numbers are strictly increasing.
    seqs = [s["seq"] for s in steps]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_spend_limit_halts_run(monkeypatch):
    monkeypatch.setattr(config, "MAX_COST_USD_PER_RUN", 0.0001)
    r = run_agent(
        "scout",
        "Research vendor Acme Corp and compute the total for 50 seats at $49 each, then save a summary file.",
    )
    assert r["status"] == "failed"
    assert "spend" in r["result"].lower()
    run = db.get_run(r["run_id"])
    assert run["status"] == "failed"


def test_flaky_tool_is_detected_and_run_fails_gracefully():
    r = run_agent(
        "scout",
        "Research vendor Acme Corp and save a summary file.",
        behaviour={"web_search": "fail"},
    )
    # The run must fail (not claim success) and must halt, not loop forever.
    assert r["status"] == "failed"
    assert r["success"] is False
    steps = db.get_trace(r["run_id"])
    # The tool was retried (not infinitely) and the failure is recorded.
    search_steps = [s for s in steps if s["type"] == "tool" and s["name"] == "web_search"]
    assert 1 <= len(search_steps) <= 3
    assert any(s["status"] == "error" for s in search_steps)
