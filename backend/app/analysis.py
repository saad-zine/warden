"""Trace cleaning + failure-pattern analysis (the data work).

Raw traces are noisy: duplicate steps, inconsistent tool names, and
one-off errors. This module cleans them (normalise names, dedupe
identical consecutive failures, drop noise) and surfaces the top
failure modes, the failure rate, and cost over time — the data that
feeds the dashboard and the incident quests.
"""
import re
from collections import Counter, defaultdict

from . import db


def clean_steps(steps):
    """Clean raw trace steps into a normalised list.

    - normalise tool names (lowercase, strip)
    - drop exact duplicate consecutive steps (same type+name+status)
    - drop `setup` node noise (keep it, but mark it as low-value)
    """
    out = []
    prev_key = None
    for s in steps:
        name = (s.get("name") or "").strip().lower()
        key = (s.get("type"), name, s.get("status"))
        if key == prev_key:
            continue
        prev_key = key
        d = dict(s)
        d["name"] = name
        out.append(d)
    return out


def _prod_runs(limit=1000):
    """Runs that are not eval-suite runs (eval runs have version
    'eval-*' and are test traffic, not production runs)."""
    return [r for r in db.list_runs(limit=limit)
            if not (r.get("version") or "").startswith("eval-")]


def failure_modes(limit=10):
    """Top failure modes across production runs.

    Sources, in order of usefulness: (1) the run's recorded
    failure_reason (loop_detected, approval_rejected, tool_failed,
    spend_limit, missing_tool); (2) tool error steps, enriched with the
    error text. Raw trace steps are cleaned first (dedupe, normalise).
    """
    prod_runs = _prod_runs()
    prod_ids = {r["run_id"] for r in prod_runs}
    counts = Counter()
    last_seen = {}
    for r in prod_runs:
        reason = (r.get("failure_reason") or "").strip()
        if reason:
            mode = f"failure: {reason}"
            counts[mode] += 1
            last_seen[mode] = max(last_seen.get(mode, 0), r.get("started_at", 0))
    steps = [s for s in db.get_all_steps() if s["run_id"] in prod_ids]
    cleaned = clean_steps(steps)
    for s in cleaned:
        if s.get("status") == "error" and s.get("type") == "tool":
            mode = f"tool_error: {s.get('name')}"
            try:
                import json
                out = json.loads(s.get("output_json") or "{}")
                err = out.get("error", "")
                if "timed out" in err.lower():
                    mode = f"tool_error: {s.get('name')} timeout"
                elif "failed" in err.lower():
                    mode = f"tool_error: {s.get('name')} failed"
            except Exception:
                pass
            counts[mode] += 1
            last_seen[mode] = max(last_seen.get(mode, 0), s.get("ts", 0))
    total_errors = sum(counts.values())
    out = []
    for mode, count in counts.most_common(limit):
        out.append({
            "mode": mode,
            "count": count,
            "share": round(count / total_errors, 3) if total_errors else 0,
            "last_seen": last_seen.get(mode),
        })
    return out


def dashboard_stats():
    """Aggregate stats for the dashboard (production runs only)."""
    runs = _prod_runs()
    total = len(runs)
    completed = [r for r in runs if r["status"] == "completed"]
    success = len([r for r in runs if r.get("success") == 1])
    success_rate = round(success / total, 3) if total else 0.0
    cost_total = round(sum(r.get("cost_usd", 0) for r in runs), 4)
    # Cost over time (per day, by started_at).
    by_day = defaultdict(float)
    for r in runs:
        import datetime
        day = datetime.datetime.fromtimestamp(r["started_at"]).strftime("%Y-%m-%d")
        by_day[day] += r.get("cost_usd", 0)
    cost_over_time = [
        {"day": d, "cost_usd": round(c, 4)}
        for d, c in sorted(by_day.items())
    ]
    # Reliability score: a 0-100 number from success rate + recency.
    # Recent runs weigh more (last 10 runs count double).
    recent = runs[:10]
    recent_success = (
        sum(1 for r in recent if r.get("success") == 1) / len(recent)
        if recent else 0.0
    )
    reliability = round(100 * (0.6 * success_rate + 0.4 * recent_success)) if total else 0
    # Trend: reliability per day (last 7 days with runs).
    trend = []
    for d in sorted(by_day.keys())[-7:]:
        day_runs = [r for r in runs if
                    __import__("datetime").datetime.fromtimestamp(r["started_at"]).strftime("%Y-%m-%d") == d]
        if day_runs:
            trend.append(round(100 * sum(1 for r in day_runs if r.get("success") == 1) / len(day_runs)))
    # Streak: consecutive days (most recent first) with at least one run
    # and no failed run.
    import datetime
    streak = 0
    today = datetime.date.today()
    by_date = defaultdict(list)
    for r in runs:
        d = datetime.datetime.fromtimestamp(r["started_at"]).date()
        by_date[d].append(r)
    day = today
    while True:
        day_runs = by_date.get(day, [])
        if not day_runs:
            break
        if any(r.get("success") != 1 for r in day_runs):
            break
        streak += 1
        day = day - datetime.timedelta(days=1)
    # Level from the reliability score.
    if reliability >= 90:
        level = "Production-grade"
    elif reliability >= 70:
        level = "Battle-tested"
    elif reliability >= 40:
        level = "Hardening"
    else:
        level = "Fragile"
    return {
        "reliability_score": reliability,
        "reliability_trend": trend,
        "runs_total": total,
        "success_rate": success_rate,
        "cost_usd_total": cost_total,
        "streak_days": streak,
        "level": level,
        "cost_over_time": cost_over_time,
    }


def leaderboard():
    """Agents ranked by reliability score (production runs only)."""
    runs = _prod_runs()
    by_agent = defaultdict(list)
    for r in runs:
        by_agent[r["agent_id"]].append(r)
    out = []
    for agent_id, rs in by_agent.items():
        success = sum(1 for r in rs if r.get("success") == 1)
        rate = success / len(rs) if rs else 0
        score = round(100 * rate)
        if score >= 90:
            level = "Production-grade"
        elif score >= 70:
            level = "Battle-tested"
        elif score >= 40:
            level = "Hardening"
        else:
            level = "Fragile"
        out.append({
            "agent_id": agent_id,
            "name": agent_id.capitalize(),
            "reliability_score": score,
            "runs": len(rs),
            "success_rate": round(rate, 3),
            "level": level,
        })
    return sorted(out, key=lambda x: x["reliability_score"], reverse=True)


def build_eval_dataset_from_traces():
    """Build an eval dataset from real (recorded) traces: each distinct
    (task, tool sequence) becomes a scenario. Returns the dataset."""
    runs = _prod_runs()
    dataset = []
    seen = set()
    for r in runs:
        steps = db.get_trace(r["run_id"])
        tools = [s["name"] for s in steps if s["type"] == "tool"]
        key = (r["task"], tuple(tools))
        if key in seen:
            continue
        seen.add(key)
        dataset.append({
            "task": r["task"],
            "agent_id": r["agent_id"],
            "expected_tools": tools,
            "success": bool(r.get("success")),
        })
    return dataset
