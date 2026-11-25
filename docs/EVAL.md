# Warden — Eval Results

Measured **2026-11-24** on this machine. The eval suite replays a fixed set of 8 recorded scenarios against an agent candidate and scores regressions. Raw results: [`backend/eval/results.json`](../backend/eval/results.json). Scenario definitions: [`backend/app/evals/scenarios.json`](../backend/app/evals/scenarios.json).

## How the suite works

- **8 fixed scenarios** (see table below). Each scenario runs the agent on a task with a defined behaviour (normal, flaky search, CRM timeout) and an expected outcome (`success`, `failure`, `blocked`, or `gate`).
- **Scoring per scenario:** `passed` (outcome matched expectation), `tool_correctness` (fraction of the expected tool sequence that ran correctly), `gate_hit` (whether the approval gate was reached when expected), cost, duration.
- **Verdict:** `pass` if the success rate is within 10 points of the baseline and no critical scenario failed; `blocked` otherwise. A blocked verdict stops the deploy.
- **Candidates:** `current` (the agent as shipped) and `degraded` (a deliberately weakened variant with the calculator tool removed) — the degraded run proves the blocking works.
- **Baseline:** the first `current` run sets the baseline success rate (stored in the `kv` table); later runs report `baseline_delta` against it.

## Measured results

| Candidate | Verdict | Success rate | Scenarios passed | Baseline delta | Duration |
|---|---|---|---|---|---|
| current | **pass** | 1.000 | 8 / 8 | 0.000 | 18.4 s |
| degraded (calculator removed) | **blocked** | 0.375 | 3 / 8 | −0.625 | 11.0 s |

The degraded candidate loses 62.5 points against the baseline (threshold: 10 points) and fails 5 of 8 scenarios, including the critical research + quote and CRM-gate scenarios — so the deploy is correctly blocked.

## Per-scenario detail — current candidate

| Scenario | Passed | Tool correctness | Gate hit | Cost | Duration |
|---|---|---|---|---|---|
| s1 Research + quote + save | yes | 1.00 | no | $0.0034 | 1.7 s |
| s2 CRM update hits the approval gate | yes | 1.00 | yes | $0.0051 | 2.7 s |
| s3 Planner hands off to the executor | yes | 1.00 | no | $0.0029 | 1.8 s |
| s4 Flaky search fails gracefully (loop detected) | yes | 0.00 | no | $0.0023 | 1.5 s |
| s5 CRM timeout fails gracefully (no false success) | yes | 0.75 | yes | $0.0047 | 3.1 s |
| s6 Outbound message hits the approval gate | yes | 1.00 | yes | $0.0030 | 2.1 s |
| s7 Rejection blocks the run | yes | 1.00 | yes | $0.0052 | 3.1 s |
| s8 Small quote | yes | 1.00 | no | $0.0025 | 1.7 s |

Notes on the two sub-1.0 tool-correctness scores (both intentional):

- **s4 (0.00):** the search tool is *supposed* to fail (flaky behaviour). The scenario passes because the agent detects the loop, fails gracefully, and does not claim a false success. Tool correctness is 0.0 because no tool in the expected sequence completed — that is the correct behaviour for this scenario.
- **s5 (0.75):** the CRM update times out. The agent retries once, the tool still fails, and the run finishes without claiming the CRM was updated. Tool correctness 0.75 reflects the one tool that did not complete; the scenario passes because there is no false success.

## Per-scenario detail — degraded candidate

| Scenario | Passed | Tool correctness |
|---|---|---|
| s1 Research + quote + save | no | 0.50 |
| s2 CRM update hits the approval gate | no | 0.40 |
| s3 Planner hands off to the executor | no | 0.50 |
| s4 Flaky search fails gracefully | yes | 0.00 |
| s5 CRM timeout fails gracefully | yes | 0.50 |
| s6 Outbound message hits the approval gate | no | 0.50 |
| s7 Rejection blocks the run | yes | 0.50 |
| s8 Small quote | no | 0.50 |

Without the calculator, the agent cannot complete the quote step in 5 of 8 scenarios, so those runs fail or block — exactly the regression the suite is meant to catch.

## What the numbers mean — and what they don't

- These numbers are for the **local deterministic demo model**, not a production LLM. They prove the *platform* (gates, replay, regression detection, blocking) works; they say nothing about how a real LLM would score.
- Cost is an **estimate** (reference token rates + word-count token proxy), not measured billing.
- Durations are wall-clock on this machine (single run, not averaged).
- To re-run: `POST /api/evals/run {"candidate": "current"}` (or `"degraded"`), or `cd backend && .venv/bin/python -m pytest tests/test_eval.py -q`.

## Tests

`cd backend && .venv/bin/python -m pytest tests/ -q` — **19 passed, 0 failed** (2026-11-24):

- `test_checkpoint_resume.py` — crash mid-run, resume from checkpoint, replay reproduces the trace.
- `test_approval_gate.py` — gate pauses, approve resumes and completes, reject blocks, a rejected tool never runs.
- `test_eval.py` — current candidate passes, degraded candidate is blocked.
- `test_trace.py` — trace steps, timings, tokens, and cost are recorded.
- `test_memory.py` — add / BM25 retrieve / update / delete.
- `test_api.py` — runs, trace, approvals, memory, and stats endpoints.
