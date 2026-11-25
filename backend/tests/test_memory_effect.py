"""Memory must change behaviour, not just decorate the trace.

The offline model honours a documented subset of explicit preferences
(see agents/model.py). This test proves the full path: memory row ->
BM25 retrieval -> system prompt -> plan -> tool arguments -> result.
"""
import json

from app import db
from app.agents.graphs import run_agent

TASK = (
    "Research vendor Acme Corp and compute the total for 50 seats at $49 "
    "each plus a $200 setup fee, then save a summary file."
)


def _clear_memories():
    for m in db.list_memories():
        db.delete_memory(m["id"])


def _calculator_input(run_id):
    for step in db.get_trace(run_id):
        if step["type"] == "tool" and step["name"] == "calculator" and step["status"] == "ok":
            return step["input"]
    raise AssertionError("calculator did not run")


def test_setup_fee_is_charged_without_memory():
    _clear_memories()
    result = run_agent("scout", TASK)
    assert result["status"] == "completed"
    expression = _calculator_input(result["run_id"])["expression"]
    assert expression == "50.0*49.0+200.0"


def test_memory_waiving_the_setup_fee_changes_the_total():
    _clear_memories()
    db.add_memory("scout", "Acme Corp asked us to waive the setup fee on this renewal.",
                  category="preference")

    result = run_agent("scout", TASK)
    assert result["status"] == "completed"
    expression = _calculator_input(result["run_id"])["expression"]
    assert expression == "50.0*49.0"   # the +200 term is gone

    # The retrieval is visible in the trace, with the memory that caused it.
    memory_steps = [s for s in db.get_trace(result["run_id"])
                    if s["type"] == "memory"]
    assert memory_steps, "no memory_retrieve step recorded"
    assert any("waive the setup fee" in str(s["output"]) for s in memory_steps)

    # And the model says why it changed the calculation.
    decisions = [json.dumps(s["output"]) for s in db.get_trace(result["run_id"])
                 if s["type"] == "llm"]
    assert any("waived" in d for d in decisions)

    _clear_memories()


def test_memory_is_scoped_per_agent():
    _clear_memories()
    db.add_memory("planner", "Acme Corp asked us to waive the setup fee.",
                  category="preference")
    result = run_agent("scout", TASK)
    expression = _calculator_input(result["run_id"])["expression"]
    # A planner memory must not leak into a scout run.
    assert expression == "50.0*49.0+200.0"
    _clear_memories()
