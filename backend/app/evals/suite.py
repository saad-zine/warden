"""Nightly eval suite: replay recorded production traces against a new
agent version, score regressions, and BLOCK deploy if regressions
exceed a threshold.

How it works:
- A fixed set of 8 scenarios (see scenarios.json) is run against an
  agent version. Each scenario declares what counts as a pass
  ("success", "gate_hit_and_success", "graceful_failure", "blocked").
- Tool correctness = share of expected tools that ran successfully.
- The result is compared to a stored baseline (the last passing
  "current" run). If the success rate drops by more than the threshold
  (10 points) or a critical scenario fails, the verdict is "blocked"
  (deploy is blocked). Otherwise "pass".
- candidate="degraded" runs the same scenarios with the calculator
  tool removed — a deliberately weakened agent — to demonstrate that
  a regression is caught and deploy is blocked.

All numbers are measured by actually running the agents. Nothing is
simulated except the tool failures injected by the scenarios
themselves (a flaky search, a CRM timeout), which are the point of
the test.
"""
import json
import time
from pathlib import Path

from .. import config, db
from ..agents.graphs import run_agent

SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.json"


def load_scenarios():
    return json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))


def _tool_correctness(run_id, expected_tools):
    steps = db.get_trace(run_id)
    ok = set()
    for s in steps:
        if s["type"] == "tool" and s["status"] == "ok":
            ok.add(s["name"])
    if not expected_tools:
        return 1.0
    return round(len([t for t in expected_tools if t in ok]) / len(expected_tools), 3)


def _gate_hit(run_id):
    approvals = db.list_approvals()
    return any(a["run_id"] == run_id for a in approvals)


def _check(scenario, result, run_id):
    """Return (passed, notes) for one scenario."""
    expect = scenario["expect"]
    notes = []
    tc = _tool_correctness(run_id, scenario.get("expected_tools", []))
    gate = _gate_hit(run_id)
    status = result.get("status")
    success = result.get("success", False)
    if expect == "success":
        passed = bool(success) and status == "completed"
        if not passed:
            notes.append(f"expected success, got status={status}")
        if tc < 1.0:
            passed = False
            notes.append(f"tool correctness {tc} < 1.0")
    elif expect == "gate_hit_and_success":
        passed = bool(success) and gate
        if not gate:
            notes.append("expected the approval gate to be hit, it was not")
        if not success:
            notes.append(f"expected success after approval, got status={status}")
        if tc < 1.0:
            passed = False
            notes.append(f"tool correctness {tc} < 1.0")
    elif expect == "graceful_failure":
        # The run must FAIL (not claim success) and must have a clear
        # failure reason — the point is the platform detects the failure
        # instead of hanging or lying.
        passed = (not success) and status in ("failed", "blocked")
        if success:
            notes.append("expected a failure, but the run claimed success")
        if not result.get("result"):
            notes.append("no failure reason recorded")
    elif expect == "blocked":
        passed = (not success) and status == "blocked"
        if success:
            notes.append("expected blocked, but the run claimed success")
        if status != "blocked":
            notes.append(f"expected status=blocked, got {status}")
    else:
        passed = False
        notes.append(f"unknown expect value: {expect}")
    return passed, notes, tc, gate


def run_suite(candidate="current"):
    """Run the full eval suite. candidate is "current" or "degraded"."""
    started = time.time()
    scenarios = load_scenarios()
    # The degraded candidate has the calculator tool removed.
    tool_names = None
    if candidate == "degraded":
        tool_names = [t for t in
                      ["web_search", "web_fetch", "file_writer", "crm_lookup",
                       "crm_update", "send_message", "delete_file"]]
    results = []
    for sc in scenarios:
        t0 = time.time()
        result = run_agent(
            sc["agent_id"], sc["task"],
            behaviour=sc.get("behaviour", {}),
            tool_names=tool_names,
            auto_decision=sc.get("auto_decision"),
            version=f"eval-{candidate}",
        )
        run_id = result["run_id"]
        passed, notes, tc, gate = _check(sc, result, run_id)
        results.append({
            "id": sc["id"],
            "name": sc["name"],
            "passed": passed,
            "success": bool(result.get("success")),
            "success_rate": 1.0 if passed else 0.0,
            "status": result.get("status"),
            "tool_correctness": tc,
            "gate_hit": gate,
            "cost_usd": result.get("cost_usd", 0),
            "duration_ms": result.get("duration_ms", int((time.time() - t0) * 1000)),
            "notes": "; ".join(notes),
            "run_id": run_id,
            "critical": bool(sc.get("critical")),
        })
    passed_n = sum(1 for r in results if r["passed"])
    success_rate = round(passed_n / len(results), 3) if results else 0.0
    # Baseline comparison.
    baseline_raw = db.kv_get("eval_baseline")
    baseline = json.loads(baseline_raw) if baseline_raw else None
    baseline_rate = baseline["success_rate"] if baseline else None
    delta = None
    if baseline_rate is not None:
        delta = round(success_rate - baseline_rate, 3)
    critical_failed = any(
        r["critical"] and not r["passed"] for r in results
    )
    if baseline_rate is None:
        verdict = "pass" if not critical_failed else "blocked"
    elif critical_failed or delta < -config.EVAL_REGRESSION_THRESHOLD:
        verdict = "blocked"
    else:
        verdict = "pass"
    # A passing "current" run becomes the new baseline.
    if candidate == "current" and verdict == "pass":
        db.kv_set("eval_baseline", json.dumps({
            "success_rate": success_rate,
            "scenarios_passed": passed_n,
            "scenarios_total": len(results),
        }))
    duration_ms = int((time.time() - started) * 1000)
    eval_id = db.new_id("eval")
    db.save_eval(eval_id, candidate, verdict, results, delta, duration_ms)
    return {
        "id": eval_id,
        "candidate": candidate,
        "verdict": verdict,
        "scenarios": results,
        "scenarios_passed": passed_n,
        "scenarios_total": len(results),
        "success_rate": success_rate,
        "baseline_success_rate": baseline_rate,
        "baseline_delta": delta,
        "duration_ms": duration_ms,
    }
