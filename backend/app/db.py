"""SQLite storage for app data (runs, traces, memories, approvals,
evals, quests). LangGraph checkpoints live in a separate file
(checkpoints.db) managed by SqliteSaver.
"""
import json
import sqlite3
import time
import uuid
from pathlib import Path

from . import config


def _connect():
    conn = sqlite3.connect(config.DATA_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    Path(config.DATA_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            thread_id TEXT,
            agent_id TEXT,
            task TEXT,
            status TEXT,
            success INTEGER,
            result TEXT,
            cost_usd REAL DEFAULT 0,
            tokens INTEGER DEFAULT 0,
            duration_ms INTEGER DEFAULT 0,
            version TEXT,
            started_at REAL,
            ended_at REAL
        );
        CREATE TABLE IF NOT EXISTS trace_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            seq INTEGER,
            type TEXT,
            name TEXT,
            input_json TEXT,
            output_json TEXT,
            duration_ms INTEGER DEFAULT 0,
            tokens INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0,
            status TEXT,
            ts REAL
        );
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            agent_id TEXT,
            content TEXT,
            category TEXT,
            created_at REAL,
            updated_at REAL
        );
        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            agent_id TEXT,
            tool TEXT,
            args_json TEXT,
            policy_refs_json TEXT,
            status TEXT,
            decided_by TEXT,
            note TEXT,
            created_at REAL,
            decided_at REAL
        );
        CREATE TABLE IF NOT EXISTS evals (
            id TEXT PRIMARY KEY,
            candidate TEXT,
            verdict TEXT,
            scenarios_json TEXT,
            baseline_delta REAL,
            started_at REAL,
            duration_ms INTEGER
        );
        CREATE TABLE IF NOT EXISTS quests (
            id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            failure_mode TEXT,
            xp INTEGER,
            status TEXT,
            done_by TEXT,
            done_at REAL
        );
        CREATE TABLE IF NOT EXISTS kv (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    conn.commit()
    # Migrations (added after the first release).
    cols = [r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()]
    for column, ddl in (
        ("failure_reason", "ALTER TABLE runs ADD COLUMN failure_reason TEXT DEFAULT ''"),
        ("provider", "ALTER TABLE runs ADD COLUMN provider TEXT DEFAULT ''"),
        ("model", "ALTER TABLE runs ADD COLUMN model TEXT DEFAULT ''"),
        ("request_id", "ALTER TABLE runs ADD COLUMN request_id TEXT DEFAULT ''"),
    ):
        if column not in cols:
            conn.execute(ddl)
            conn.commit()
    conn.close()


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now():
    return time.time()


# ---- runs ----
def create_run(run_id, thread_id, agent_id, task, version,
               provider="", model="", status="running"):
    conn = _connect()
    conn.execute(
        "INSERT INTO runs (run_id, thread_id, agent_id, task, status, version,"
        " provider, model, started_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (run_id, thread_id, agent_id, task, status, version,
         provider, model, now()),
    )
    conn.commit()
    conn.close()


def update_run(run_id, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    conn = _connect()
    conn.execute(
        f"UPDATE runs SET {sets} WHERE run_id=?", (*fields.values(), run_id)
    )
    conn.commit()
    conn.close()


def _normalise_run(row):
    d = dict(row)
    # SQLite stores success as 0/1/NULL; expose it as a real boolean.
    if d.get("success") is not None:
        d["success"] = bool(d["success"])
    return d


def get_run(run_id):
    conn = _connect()
    row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    conn.close()
    return _normalise_run(row) if row else None


def list_runs(agent_id=None, status=None, limit=50):
    conn = _connect()
    q = "SELECT * FROM runs"
    params = []
    clauses = []
    if agent_id:
        clauses.append("agent_id=?")
        params.append(agent_id)
    if status:
        clauses.append("status=?")
        params.append(status)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_normalise_run(r) for r in rows]


def count_runs():
    conn = _connect()
    n = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    conn.close()
    return n


# ---- trace steps ----
def add_step(run_id, seq, type_, name, input_json, output_json,
             duration_ms=0, tokens=0, cost_usd=0.0, status="ok"):
    conn = _connect()
    conn.execute(
        "INSERT INTO trace_steps (run_id, seq, type, name, input_json,"
        " output_json, duration_ms, tokens, cost_usd, status, ts)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id, seq, type_, name,
            json.dumps(input_json) if input_json is not None else None,
            json.dumps(output_json) if output_json is not None else None,
            duration_ms, tokens, cost_usd, status, now(),
        ),
    )
    conn.commit()
    conn.close()


def get_trace(run_id):
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM trace_steps WHERE run_id=? ORDER BY seq ASC", (run_id,)
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["input"] = json.loads(d.pop("input_json")) if d["input_json"] else None
        d["output"] = json.loads(d.pop("output_json")) if d["output_json"] else None
        out.append(d)
    return out


def get_all_steps():
    """All trace steps (for failure analysis)."""
    conn = _connect()
    rows = conn.execute("SELECT * FROM trace_steps ORDER BY ts ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trace_after(run_id, seq=0):
    """Trace steps with seq greater than `seq` (incremental reads for SSE)."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM trace_steps WHERE run_id=? AND seq>? ORDER BY seq ASC",
        (run_id, seq),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["input"] = json.loads(d.pop("input_json")) if d["input_json"] else None
        d["output"] = json.loads(d.pop("output_json")) if d["output_json"] else None
        out.append(d)
    return out


def recover_interrupted_runs():
    """Close runs that were mid-flight when the process died.

    Only the *paused* state is durable on purpose: a run interrupted at an
    approval gate resumes from its checkpoint (that is the product claim,
    and it is tested). A run killed mid-tool-call is marked failed rather
    than silently replayed, because replaying a node can duplicate a side
    effect (a second CRM write, a second email).
    """
    conn = _connect()
    rows = conn.execute(
        "SELECT run_id FROM runs WHERE status IN ('queued', 'running')"
    ).fetchall()
    ids = [r["run_id"] for r in rows]
    for run_id in ids:
        conn.execute(
            "UPDATE runs SET status='failed', success=0, ended_at=?,"
            " failure_reason='process_restart',"
            " result='Failed: the worker process stopped mid-run.'"
            " WHERE run_id=?",
            (now(), run_id),
        )
    conn.commit()
    conn.close()
    return ids


# ---- memories ----
def add_memory(agent_id, content, category="fact"):
    mid = new_id("mem")
    conn = _connect()
    conn.execute(
        "INSERT INTO memories (id, agent_id, content, category, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (mid, agent_id, content, category, now(), now()),
    )
    conn.commit()
    conn.close()
    return mid


def list_memories(agent_id=None):
    conn = _connect()
    if agent_id:
        rows = conn.execute(
            "SELECT * FROM memories WHERE agent_id=? ORDER BY created_at DESC",
            (agent_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM memories ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_memory(mid, content=None, category=None):
    conn = _connect()
    if content is not None:
        conn.execute(
            "UPDATE memories SET content=?, updated_at=? WHERE id=?",
            (content, now(), mid),
        )
    if category is not None:
        conn.execute(
            "UPDATE memories SET category=?, updated_at=? WHERE id=?",
            (category, now(), mid),
        )
    conn.commit()
    conn.close()


def delete_memory(mid):
    conn = _connect()
    conn.execute("DELETE FROM memories WHERE id=?", (mid,))
    conn.commit()
    conn.close()


# ---- approvals ----
def create_approval(approval_id, run_id, agent_id, tool, args, policy_refs):
    conn = _connect()
    conn.execute(
        "INSERT INTO approvals (id, run_id, agent_id, tool, args_json,"
        " policy_refs_json, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (
            approval_id, run_id, agent_id, tool,
            json.dumps(args), json.dumps(policy_refs), "pending", now(),
        ),
    )
    conn.commit()
    conn.close()


def get_approval(approval_id):
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["args"] = json.loads(d.pop("args_json")) if d["args_json"] else {}
    d["policy_refs"] = (
        json.loads(d.pop("policy_refs_json")) if d["policy_refs_json"] else []
    )
    return d


def list_approvals(status=None):
    conn = _connect()
    if status:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE status=? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM approvals ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["args"] = json.loads(d.pop("args_json")) if d["args_json"] else {}
        d["policy_refs"] = (
            json.loads(d.pop("policy_refs_json")) if d["policy_refs_json"] else []
        )
        out.append(d)
    return out


def decide_approval(approval_id, status, decided_by="human", note=""):
    """Record a decision once. Returns 0 if it was already decided.

    The WHERE clause makes double-clicks, retries and two humans racing on
    the same approval idempotent: only the first decision takes effect.
    """
    conn = _connect()
    cur = conn.execute(
        "UPDATE approvals SET status=?, decided_by=?, note=?, decided_at=?"
        " WHERE id=? AND status='pending'",
        (status, decided_by, note, now(), approval_id),
    )
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed


# ---- evals ----
def save_eval(eval_id, candidate, verdict, scenarios, baseline_delta, duration_ms):
    conn = _connect()
    conn.execute(
        "INSERT INTO evals (id, candidate, verdict, scenarios_json,"
        " baseline_delta, started_at, duration_ms) VALUES (?,?,?,?,?,?,?)",
        (
            eval_id, candidate, verdict, json.dumps(scenarios),
            baseline_delta, now(), duration_ms,
        ),
    )
    conn.commit()
    conn.close()


def list_evals(limit=20):
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM evals ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["scenarios"] = json.loads(d.pop("scenarios_json"))
        out.append(d)
    return out


def get_eval(eval_id):
    conn = _connect()
    row = conn.execute("SELECT * FROM evals WHERE id=?", (eval_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["scenarios"] = json.loads(d.pop("scenarios_json"))
    return d


# ---- quests ----
def seed_quests():
    conn = _connect()
    n = conn.execute("SELECT COUNT(*) FROM quests").fetchone()[0]
    if n:
        conn.close()
        return
    quests = [
        ("q_crm_timeout", "Fix the CRM timeout",
         "crm_update timed out 5 times. Add a retry with backoff and a 5s timeout.",
         "tool_error: crm_update timeout", 150),
        ("q_loop_guard", "Stop the loop",
         "An agent looped 12 times on a broken search. Tighten the iteration cap and add loop detection.",
         "loop_detected: repeated web_search", 200),
        ("q_cost_spike", "Tame the cost spike",
         "One run spent 3x the median. Add a per-run cost budget and a cheaper fallback path.",
         "cost_spike: run over budget", 100),
        ("q_stale_memory", "Clean the stale memory",
         "3 memories contradict the current vendor pricing. Review and update the memory store.",
         "memory_conflict: stale vendor pricing", 120),
        ("q_gate_rejected", "Review the rejected action",
         "A human rejected a risky action. Check the policy refs and the run trace, then fix the agent's plan.",
         "failure: approval_rejected", 100),
        ("q_tool_failed", "Fix the failing tool",
         "A tool call failed and the run could not complete. Add a retry and a graceful fallback.",
         "failure: tool_failed", 120),
        ("q_loop_detected", "Break the loop",
         "An agent repeated the same tool call and was halted. Tighten the loop detector and the iteration cap.",
         "failure: loop_detected", 150),
        ("q_spend_limit", "Cap the spend",
         "A run hit the spend limit and was halted. Lower the per-run budget or make the agent cheaper.",
         "failure: spend_limit", 100),
        ("q_missing_tool", "Wire up the missing tool",
         "The agent needed a tool that does not exist. Add it or teach the agent to work without it.",
         "failure: missing_tool", 120),
    ]
    for qid, title, desc, mode, xp in quests:
        conn.execute(
            "INSERT INTO quests (id, title, description, failure_mode, xp, status)"
            " VALUES (?,?,?,?,?,?)",
            (qid, title, desc, mode, xp, "open"),
        )
    conn.commit()
    conn.close()


def list_quests():
    conn = _connect()
    rows = conn.execute("SELECT * FROM quests ORDER BY xp DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def complete_quest(quest_id, done_by="human"):
    conn = _connect()
    conn.execute(
        "UPDATE quests SET status=?, done_by=?, done_at=? WHERE id=?",
        ("done", done_by, now(), quest_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM quests WHERE id=?", (quest_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ---- kv (xp, baselines) ----
def kv_get(key, default=None):
    conn = _connect()
    row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default


def kv_set(key, value):
    conn = _connect()
    conn.execute(
        "INSERT INTO kv (key, value) VALUES (?,?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()
