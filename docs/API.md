# Warden — API Contract (v1)

Base URL: `http://localhost:8000`. All responses are JSON. Interactive docs at `/docs`.

## Conventions

- **Timestamps** (`started_at`, `ended_at`, `created_at`, `updated_at`, `decided_at`, `ts`, `last_seen`) are ISO-8601 strings (UTC).
- **Trace step `input` / `output`** are JSON strings (serialised objects), so they render directly in the trace viewer.
- **Cost** (`cost_usd`) is an estimate from reference token rates ($3/1M input, $15/1M output tokens) and a word-count token proxy; it is not a bill.
- **Tokens** are a word-count proxy, not a real tokenizer count.

## Concepts

- **Agent**: a demo agent (Scout, Planner). `id`, `name`, `description`, `tools[]`, `version`.
- **Run**: one execution of an agent on a task. Has a `thread_id` (LangGraph thread), a `status` (`running`, `awaiting_approval`, `completed`, `failed`, `blocked`), a `success` flag, `cost_usd` (estimated), `duration_ms`, and a full **trace**.
- **Trace step**: one recorded event in a run — `type` (`node` | `tool` | `llm` | `gate` | `memory`), `name`, `input`, `output`, `duration_ms`, `tokens`, `cost_usd`, `status` (`ok` | `error` | `awaiting_approval` | `rejected`), `ts`.
- **Approval**: a paused risky action. `id`, `run_id`, `tool`, `args`, `policy_refs[]` (retrieved policy/incident docs), `status` (`pending` | `approved` | `rejected`), `decided_by`, `decided_at`.
- **Memory**: a stored fact/preference. `id`, `agent_id`, `content`, `category`, `created_at`, `updated_at`.
- **Eval**: one eval-suite run. `id`, `verdict` (`pass` | `blocked`), `scenarios[]` (each: `id`, `name`, `passed`, `success_rate`, `tool_correctness`, `cost_usd`, `notes`), `baseline_delta`, `started_at`, `duration_ms`.

## Endpoints

### Health & agents

- `GET /health` → `{ "status": "ok", "agents": ["scout", "planner"], "runs": 12, "db": "sqlite", "model": "local-deterministic" }`
- `GET /api/agents` → `[{ "id": "scout", "name": "Scout", "description": "...", "tools": ["web_search","web_fetch","calculator","file_writer","crm_lookup","crm_update"], "version": "1.2.0" }, { "id": "planner", ... }]`

### Runs

- `POST /api/runs` — body `{ "agent_id": "scout", "task": "Research vendor Acme Corp..." }` → `201 { "run_id": "run_...", "thread_id": "th_...", "status": "running" | "awaiting_approval", "agent_id": "scout" }`
  - Runs execute synchronously in the request for short demo tasks; if the agent hits an approval gate, the response is `status: "awaiting_approval"` with `pending_approval: { approval_id, tool, args }`.
- `GET /api/runs` — query `?agent_id=&status=&limit=50` → `[{ "run_id", "agent_id", "task", "status", "success": true|false|null, "cost_usd", "duration_ms", "started_at", "ended_at" }]`
- `GET /api/runs/{run_id}` → run detail + `trace: [trace steps]` + `pending_approval` (if any) + `checkpoints: n`
- `GET /api/runs/{run_id}/trace` → `{ "run_id": ..., "steps": [ ... ] }`
- `POST /api/runs/{run_id}/approve` — body `{ "approval_id": "...", "note": "" }` → resumes the run; returns `{ "run_id", "status": "completed" | "awaiting_approval" | "failed", "result": "..." }`
- `POST /api/runs/{run_id}/reject` — body `{ "approval_id": "...", "note": "" }` → resumes with rejection; the agent records the rejection and finishes `blocked`.
- `POST /api/runs/{run_id}/replay` — re-runs the recorded trace against the current agent version (no side effects; tools run in dry-run mode) → `{ "run_id", "replayed_steps": n, "divergences": [...] }`
- `GET /api/runs/{run_id}/checkpoints` → `{ "run_id", "checkpoints": [{ "checkpoint_id", "step", "ts" }] }`

### Approvals

- `GET /api/approvals?status=pending` → `[{ "id", "run_id", "agent_id", "tool", "args", "policy_refs": [{ "doc", "excerpt" }], "status": "pending", "created_at" }]`
- `POST /api/approvals/{approval_id}/approve` and `/reject` — same effect as the run endpoints, usable from the queue view.

### Memory

- `GET /api/memory?agent_id=scout` → `[{ "id", "agent_id", "content", "category", "created_at" }]`
- `POST /api/memory` — `{ "agent_id", "content", "category" }` → `201` the created memory.
- `PUT /api/memory/{id}` — `{ "content", "category" }` → updated memory.
- `DELETE /api/memory/{id}` → `204`.

### Evals

- `GET /api/evals` → `[{ "id", "verdict", "scenarios_passed", "scenarios_total", "baseline_delta", "started_at", "duration_ms" }]`
- `POST /api/evals/run` — body `{ "candidate": "current" | "degraded" }` → runs the fixed eval set (8 scenarios) and returns `{ "id", "verdict": "pass" | "blocked", "scenarios": [...], "baseline_delta", "duration_ms" }`. `candidate: "degraded"` runs a deliberately weakened agent variant (calculator tool removed) to demonstrate regression detection + deploy blocking.
- `GET /api/evals/{eval_id}` → full eval detail.

### Stats, analysis, gamification

- `GET /api/stats` → `{ "reliability_score": 87, "reliability_trend": [82,84,85,87], "runs_total": 42, "success_rate": 0.93, "cost_usd_total": 1.84, "streak_days": 6, "level": "Battle-tested", "cost_over_time": [{ "day": "2026-11-20", "cost_usd": 0.31 }] }`
- `GET /api/failure-modes` → `[{ "mode": "tool_error: crm_update timeout", "count": 5, "share": 0.31, "last_seen": "...", "quest": { "id": "q1", "title": "Fix the CRM timeout", "xp": 150 } }]`
- `GET /api/leaderboard` → `[{ "agent_id", "name", "reliability_score": 91, "runs": 24, "success_rate": 0.96, "level": "Production-grade" }]`
- `GET /api/quests` → `[{ "id", "title", "description", "failure_mode", "xp": 150, "status": "open" | "done", "done_by": null }]`
- `POST /api/quests/{quest_id}/complete` — `{ "note": "" }` → marks a quest done, awards XP. Returns `{ "quest_id", "xp_awarded": 150, "total_xp": 1250, "level": "Battle-tested" }`

## Policy (guardrail)

Tools are classified by policy:
- `needs_approval`: `crm_update`, `send_message`, `delete_file`
- `free`: `web_search`, `web_fetch`, `calculator`, `file_writer` (sandboxed), `crm_lookup`

Before a `needs_approval` tool runs, the guardrail retrieves the relevant policy + incident docs (BM25 over `backend/policies/` and `backend/incidents/`) and records the retrieved excerpts on the approval. Spend/token limits: a run halts if `cost_usd` exceeds `0.50` or tokens exceed `20000` (configurable in `backend/app/config.py`).

## Demo data

All runs, traces, memories, and eval results are SYNTHETIC demo data, generated locally by the demo agents. Nothing is presented as real production traffic. The demo agents use a local deterministic model (no external LLM API) so the platform runs offline; any LangChain chat model can be plugged in.
