# Warden — API Contract (v1.1)

Base URL: `http://localhost:8000`. All responses are JSON unless noted. Interactive docs at `/docs`.

## Conventions

- **Timestamps** (`started_at`, `ended_at`, `created_at`, `updated_at`, `decided_at`, `ts`, `last_seen`) are ISO-8601 strings (UTC).
- **Trace step `input` / `output`** are JSON strings (serialised objects), so they render directly in the trace viewer.
- **Cost** (`cost_usd`) is an estimate from reference token rates ($3/1M input, $15/1M output tokens) and a word-count token proxy; it is not a bill. Providers that report usage metadata use the real token counts for the estimate.
- **Tokens** are a word-count proxy unless the provider reports usage.
- Every response carries an `x-request-id` header (echoed from the request or generated) and the server logs a latency line per request.

## Concepts

- **Agent**: Scout (research/ops) or Planner (plans, then executes through Scout). `id`, `name`, `description`, `tools[]`, `version`.
- **Run**: one execution of an agent on a task. Has a `thread_id`, a `status` (`queued`, `running`, `resuming`, `awaiting_approval`, `completed`, `failed`, `blocked`, `interrupted`), `success`, `cost_usd` (estimated), `duration_ms`, `version`, `provider`, `model`, and a full **trace**. Runs execute in a background worker pool.
- **Trace step**: one recorded event — `seq` (monotonic per run), `type` (`node` | `tool` | `llm` | `gate` | `memory`), `name`, `input`, `output`, `duration_ms`, `tokens`, `cost_usd`, `status` (`ok` | `error` | `awaiting_approval` | `rejected`), `ts`.
- **Approval**: a paused risky action. `id` (also exposed as `approval_id` in run detail), `run_id`, `tool`, `args`, `policy_refs[]` (retrieved policy/incident docs), `status` (`pending` | `approved` | `rejected`), `decided_by`, `decided_at`.
- **Memory**: a stored fact/preference. `id`, `agent_id`, `content`, `category`, `created_at`, `updated_at`. Retrieved read-only at the start of a run.
- **Eval**: one eval-suite run. `id`, `candidate`, `verdict` (`pass` | `blocked`), `scenarios[]` (each: `id`, `name`, `passed`, `success_rate`, `tool_correctness`, `gate_hit`, `cost_usd`, `notes`), `baseline_delta`, `started_at`, `duration_ms`.

## Endpoints

### Health & agents

- `GET /health` →
  ```json
  {
    "status": "ok", "product": "Warden", "version": "1.1.0",
    "agents": ["scout", "planner"], "runs": 12, "db": "sqlite",
    "provider": "deterministic", "model": "warden-local-deterministic",
    "live_model": false, "tools": "auto", "workers": 4, "inflight": 0
  }
  ```
  `provider` is one of `openai | anthropic | ollama | deterministic`; `live_model` is false only for the deterministic model.
- `GET /api/agents` → `[{ "id": "scout", "name": "Scout", "description": "...", "tools": [...], "version": "1.2.0" }, { "id": "planner", ... }]`

### Runs

- `POST /api/runs` — body `{ "agent_id": "scout", "task": "Research vendor Acme Corp..." }`.
  - Default: returns **`202`** immediately with `{ "run_id", "thread_id", "status": "queued", "agent_id", "provider", "model" }`. Poll the run or stream it.
  - `?wait=N` (0–300 s): blocks until the run is terminal or paused, then returns the full run detail. Intended for curl demos, scripts and tests — the UI uses SSE instead.
  - If a gate is hit, the detail has `status: "awaiting_approval"` and `pending_approval: { approval_id, tool, args, policy_refs }`.
- `GET /api/runs` — query `?agent_id=&status=&limit=50` → `[{ "run_id", "agent_id", "task", "status", "success", "cost_usd", "duration_ms", "started_at", "ended_at", "version", "provider", "model" }]`
- `GET /api/runs/{run_id}` → run detail + `trace: [steps]` + `pending_approval` (or `null`) + `checkpoints: n` + `result`
- `GET /api/runs/{run_id}/trace` → `{ "run_id", "steps": [...] }`
- **`GET /api/runs/{run_id}/events`** — Server-Sent Events. Query `?after=<seq>` resumes after a known step. Frames:
  ```
  event: step      data: {trace step}
  event: status    data: {"run_id","status","success"}
  event: end       data: {}
  ```
  The stream reads durable trace rows, so a client may attach late or reconnect without missing steps. It ends when the run is terminal or paused at a gate (`end`), and sends `retry: 1000` on connect.
- `POST /api/runs/{run_id}/approve` (and `/reject`) — body `{ "approval_id"?: "...", "note": "" }` → **`202`** `{ "run_id", "status": "resuming", "approval_id" }`, or with `?wait=N` the final detail.
  - The decision is idempotent: a second decision on the same approval returns **`409`**, and so does deciding a run that is not `awaiting_approval`.
- `POST /api/runs/{run_id}/replay` — body `{}` (default) or `{ "execute": true }`.
  - Static: `{ "run_id", "replayed_steps", "expected_plan", "recorded_tools", "divergences": string[], "checkpoints": [...] }` — no side effects.
  - `execute: true`: additionally re-runs the task against the current agent (auto-deciding gates the way the original was decided), creating a new run with `version="replay-*"`, and returns
    ```json
    "execution": {
      "run_id": "...", "status": "completed", "success": true,
      "tools": ["web_search", "web_fetch", "calculator", "file_writer"],
      "same_tool_sequence": true, "same_outcome": true,
      "cost_usd": 0.0, "duration_ms": 2400, "matches": true
    }
    ```
- `GET /api/runs/{run_id}/checkpoints` → `{ "run_id", "checkpoints": [{ "checkpoint_id", "step", "ts" }] }`

### Approvals

- `GET /api/approvals?status=pending` → `[{ "id", "run_id", "agent_id", "tool", "args", "policy_refs": [{ "doc", "excerpt" }], "status", "created_at" }]`
- `POST /api/approvals/{approval_id}/approve` and `/reject` — body `{ "note": "" }` (+ optional `?wait=N`); same effect and `409` semantics as the run endpoints. This is what the Approvals view calls.

### Memory

- `GET /api/memory?agent_id=scout` → `[{ "id", "agent_id", "content", "category", "created_at" }]`
- `POST /api/memory` — `{ "agent_id", "content", "category" }` → `201` the created memory.
- `PUT /api/memory/{id}` — `{ "content", "category" }` → updated memory.
- `DELETE /api/memory/{id}` → `204`.

Memory is retrieved with BM25Plus at the start of every run and injected into the system prompt; the `memory_retrieve` trace step records what was retrieved and its score.

### Evals

- `GET /api/evals` → `[{ "id", "candidate", "verdict", "scenarios_passed", "scenarios_total", "baseline_delta", "started_at", "duration_ms" }]`
- `POST /api/evals/run` — body `{ "candidate": "current" | "degraded" }` → runs the fixed 8-scenario suite and returns `{ "id", "verdict": "pass" | "blocked", "scenarios": [...], "baseline_delta", "duration_ms" }`.
  - Scenarios run with **mock tools** so scores are reproducible and network-independent. The model is whatever the server is configured to use (add a provider key to eval a real model — that costs money).
  - `candidate: "degraded"` removes the calculator tool to demonstrate regression detection and deploy blocking. Eval runs are tagged `version="eval-*"` and excluded from dashboard stats.
- `GET /api/evals/{eval_id}` → full eval detail.

### Stats, analysis, gamification

- `GET /api/stats` → `{ "reliability_score": 87, "reliability_trend": [...], "runs_total": 42, "success_rate": 0.93, "cost_usd_total": 1.84, "streak_days": 6, "level": "Battle-tested", "cost_over_time": [...] }`
- `GET /api/failure-modes` → `[{ "mode", "count", "share", "last_seen", "quest" }]`
- `GET /api/leaderboard` → `[{ "agent_id", "name", "reliability_score", "runs", "success_rate", "level" }]`
- `GET /api/quests` → `[{ "id", "title", "description", "failure_mode", "xp", "status", "done_by" }]`
- `POST /api/quests/{quest_id}/complete` — `{ "note": "" }` → `{ "quest_id", "xp_awarded", "total_xp", "level" }`

Stats, failure modes and the leaderboard exclude `eval-*` and `replay-*` runs: they are test traffic.

## Policy (guardrail)

Tools are classified by policy:
- `needs_approval`: `crm_update`, `send_message`, `delete_file`
- `free`: `web_search`, `web_fetch`, `calculator`, `file_writer` (sandboxed to `backend/output/`), `crm_lookup`

Before a `needs_approval` tool runs, the guardrail retrieves the relevant policy + incident docs (BM25Plus over `backend/policies/` and `backend/incidents/`) and records the excerpts on the approval. A run halts if `cost_usd` exceeds `0.50`, tokens exceed `20000`, or iterations exceed `12` (configurable via `WARDEN_MAX_COST_USD`, `WARDEN_MAX_TOKENS`, `WARDEN_MAX_ITERATIONS`).

## Tool safety

`web_fetch` resolves the target and every redirect hop and refuses non-public addresses (loopback, private, link-local/metadata, reserved, multicast, unspecified, including IPv6 and IPv4-mapped IPv6). Responses are capped at `WARDEN_WEB_MAX_BYTES` (1 MB) and redirects at `WARDEN_WEB_MAX_REDIRECTS` (3). An SSRF attempt is a tool error, never downgraded to mock data.

## Demo data

Seeded runs, traces, memories, and eval results are synthetic demo data generated locally. Normal runs use real public-web tools when `WARDEN_TOOLS` is `real` or `auto`; nothing private is accessed.
