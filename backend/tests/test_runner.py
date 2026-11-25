"""Worker pool: real concurrency, crash recovery, and double-submit guards.

Three runs are executed at once to prove that per-thread checkpointers and
WAL-mode SQLite actually allow concurrent execution (a single shared
SqliteSaver would fail or interleave here).
"""
import time

import pytest

from app import db, runner


def _wait(run_id, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = db.get_run(run_id)
        if run and run["status"] in ("completed", "failed", "blocked", "awaiting_approval"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} stuck in {db.get_run(run_id)['status']}")


TASK = (
    "Research vendor Acme Corp and compute the total for 10 seats at $19 "
    "each, then save a summary file."
)


def test_three_concurrent_runs_all_complete_with_separate_traces():
    queued = [runner.start_run("scout", TASK) for _ in range(3)]
    assert len({q["run_id"] for q in queued}) == 3
    assert len({q["thread_id"] for q in queued}) == 3

    done = [_wait(q["run_id"]) for q in queued]
    assert all(r["status"] == "completed" for r in done)
    assert all(r["success"] for r in done)

    traces = [db.get_trace(q["run_id"]) for q in queued]
    assert all(len(t) >= 10 for t in traces)
    # Each thread's checkpointer wrote only its own thread.
    assert len({t[0]["run_id"] for t in traces}) == 3
    assert all(run_id == t[0]["run_id"] for run_id, t in
               zip([q["run_id"] for q in queued], traces))


def test_inflight_drains_after_completion():
    q = runner.start_run("scout", TASK)
    _wait(q["run_id"])
    deadline = time.time() + 5
    while runner.inflight() and time.time() < deadline:
        time.sleep(0.05)
    assert runner.inflight() == 0


def test_double_submit_is_refused():
    run_id = db.new_id("run")
    db.create_run(run_id, db.new_id("th"), "scout", TASK, "test", status="awaiting_approval")
    runner._claim(run_id)
    try:
        with pytest.raises(runner.RunBusy):
            runner.submit_resume(run_id, "apr_x", True, "")
    finally:
        runner._release(run_id)


def test_restart_marks_midflight_runs_failed_not_silently_resumed():
    run_id = db.new_id("run")
    db.create_run(run_id, db.new_id("th"), "scout", TASK, "test", status="running")
    recovered = db.recover_interrupted_runs()
    assert run_id in recovered
    run = db.get_run(run_id)
    assert run["status"] == "failed"
    assert run["failure_reason"] == "process_restart"
    assert run["success"] is False
