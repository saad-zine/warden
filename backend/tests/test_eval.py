"""Eval suite: the current agent passes; a degraded agent is blocked.

This is the regression-blocking test: the "degraded" candidate has the
calculator tool removed, so every cost task fails. The suite must
catch the regression and return verdict="blocked".
"""
from app.evals.suite import run_suite


def test_current_candidate_passes():
    result = run_suite("current")
    assert result["verdict"] == "pass", result
    assert result["scenarios_passed"] == result["scenarios_total"]
    assert result["success_rate"] == 1.0
    # The gate scenarios really hit the gate.
    by_id = {s["id"]: s for s in result["scenarios"]}
    assert by_id["s2_crm_update_gate"]["gate_hit"] is True
    assert by_id["s6_send_message_gate"]["gate_hit"] is True
    # The failure scenarios failed gracefully (no false success).
    assert by_id["s4_flaky_search"]["passed"] is True
    assert by_id["s5_crm_timeout"]["passed"] is True
    assert by_id["s7_rejection_blocks"]["passed"] is True


def test_degraded_candidate_is_blocked():
    # Baseline first (a passing "current" run sets it).
    run_suite("current")
    result = run_suite("degraded")
    assert result["verdict"] == "blocked", result
    assert result["success_rate"] < 1.0
    assert result["baseline_delta"] is not None
    assert result["baseline_delta"] < -0.10
    # The cost scenarios are the ones that regressed.
    by_id = {s["id"]: s for s in result["scenarios"]}
    assert by_id["s1_research_quote"]["passed"] is False
    assert by_id["s8_small_quote"]["passed"] is False
