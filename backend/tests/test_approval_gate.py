"""Approval gate: pause, approve, reject."""
from app import db
from app.agents.graphs import resume_run, run_agent

TASK = (
    "Research vendor Acme Corp, compute the total for 50 seats at $49 each, "
    "save a summary, and update the CRM record with the quote."
)


def test_approve_completes_run():
    r = run_agent("scout", TASK)
    assert r["status"] == "awaiting_approval"
    apr = r["pending_approval"]
    assert apr["tool"] == "crm_update"
    # The guardrail retrieved real policy/incident evidence.
    assert len(apr["policy_refs"]) >= 1
    assert any("crm" in ref["doc"].lower() for ref in apr["policy_refs"])

    resumed = resume_run(r["run_id"], apr["approval_id"], True, "looks good")
    assert resumed["status"] == "completed"
    assert resumed["success"] is True

    approval = db.get_approval(apr["approval_id"])
    assert approval["status"] == "approved"


def test_reject_blocks_run():
    r = run_agent("scout", TASK)
    assert r["status"] == "awaiting_approval"
    apr = r["pending_approval"]

    resumed = resume_run(r["run_id"], apr["approval_id"], False, "wrong customer")
    assert resumed["status"] == "blocked"
    assert resumed["success"] is False

    approval = db.get_approval(apr["approval_id"])
    assert approval["status"] == "rejected"

    # The run did NOT claim success and did NOT run crm_update.
    steps = db.get_trace(r["run_id"])
    assert not any(
        s["type"] == "tool" and s["name"] == "crm_update" and s["status"] == "ok"
        for s in steps
    )


def test_approval_queue_lists_pending():
    r = run_agent("scout", TASK)
    assert r["status"] == "awaiting_approval"
    pending = [a for a in db.list_approvals("pending") if a["run_id"] == r["run_id"]]
    assert len(pending) == 1
    # Clean up: approve it so later tests see a clean queue.
    resume_run(r["run_id"], pending[0]["id"], True, "cleanup")
