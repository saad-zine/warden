# Warden — Architecture

## Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  Frontend (React 19 + Vite + TypeScript + Tailwind v4)               │
│  Dashboard · Runs (+ live trace) · Approvals · Evals · Agents &      │
│  quests · Memory — clean white enterprise UI, teal accent.           │
│  SSE while a run executes; labelled demo mode when the backend is    │
│  unreachable.                                                        │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ HTTP (JSON) + SSE
┌───────────────────────────────▼──────────────────────────────────────┐
│  Backend (FastAPI, Python 3.12+)  —  app/                            │
│                                                                      │
│  main.py            REST API, SSE endpoint, serializers, request-id   │
│                     middleware, lifespan (recovery + warm caches)     │
│  runner.py          bounded ThreadPoolExecutor; start_run /           │
│                     submit_resume / is_inflight; never runs an agent  │
│                     on the request thread                             │
│  llm.py             provider resolution + chat-model factory          │
│                     (openai / anthropic / ollama / deterministic),    │
│                     system prompt with retrieved memory, traced       │
│                     retry with exponential backoff                    │
│  agents/            LangGraph graphs (Scout, Planner), tools,        │
│    graphs.py        run_agent / resume_run / replay_run;             │
│                     per-thread SqliteSaver + compiled graphs         │
│    scout.py         ReAct loop: setup → agent → gate → tools →      │
│                     finalize; approval gate via interrupt(); loop    │
│                     detection, spend/token/iteration limits,         │
│                     model_error surfaced (no silent downgrade)       │
│    planner.py       planner → executor (Scout subgraph) →           │
│                     summarizer with plan-coverage check              │
│    model.py         DeterministicModel — rule-based ReAct policy,    │
│                     honours a documented subset of memory prefs      │
│    tools.py         real web search/fetch (SSRF-guarded), calculator,│
│                     sandboxed file writer, stateful CRM; mock mode   │
│                     and labelled fallback for offline runs           │
│  guardrail.py       Policy: which tools need approval; BM25Plus RAG  │
│                     over policies/ + incidents/ before a gate        │
│  memory.py          BM25Plus retrieval over stored facts/preferences │
│  trace.py           Per-run trace writer (seq, resume-safe)          │
│  analysis.py        Trace cleaning, failure modes, dashboard stats,  │
│                     leaderboard, eval datasets from real traces      │
│  evals/suite.py     Fixed 8-scenario suite, mock tools (hermetic),   │
│                     baseline compare, verdict pass/blocked           │
│  db.py              SQLite (WAL): runs, trace_steps, memories,       │
│                     approvals, evals, quests, kv; crash recovery     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ SQLite files
                   warden.db (runs/traces/…) · checkpoints.db
                   (LangGraph checkpoints)
```

## Request lifecycle

```
POST /api/runs
  └─ main.py validates, runner.start_run()
       ├─ db.create_run(status="queued", provider, model)
       └─ executor.submit(_run_job)                     → 202 {run_id, queued}
            └─ worker thread: run_agent(precreated=True)
                 ├─ status=running; tracer writes each step to trace_steps
                 └─ approval gate → graph interrupt(), status=awaiting_approval
                      └─ POST /approve → runner.submit_resume()
                           └─ resume_run() continues from the checkpoint

GET /api/runs/{id}/events (SSE)
  └─ poll db.get_trace_after(run_id, last_seq) → event: step
     emit status changes → event: status
     terminal or paused → event: end
```

Why this shape: an agent run takes seconds to minutes, may pause for a human, and may retry a flaky model. If execution happened on the request thread, a proxy timeout would kill work that already happened and the client could not show progress. The pool is bounded so a burst cannot exhaust the machine or hammer a provider.

## Key design decisions

- **LangGraph as a dependency, not a fork.** The orchestration library is `pip install langgraph` (MIT). Warden is the product built on it: the guardrail, trace store, streaming, eval suite, memory, runner and UI are ours.
- **A provider abstraction, with an offline contract.** `llm.py` builds the chat model for a run and returns the same interface for every backend. `auto` prefers `OPENAI_API_KEY`, then `ANTHROPIC_API_KEY`, then a reachable Ollama (`/v1`), then the deterministic model. An explicitly configured provider is never silently replaced: a failure fails the run with `failure_reason="model_error"` and a traced `model_error` step. Tests force `deterministic` + `mock` so CI is offline; the provider code paths are unit-tested directly.
- **Per-thread checkpointers.** `SqliteSaver` owns one `sqlite3` connection and LangGraph compiles the checkpointer into the graph; neither is safe to share across threads. Each worker thread lazily creates its own checkpointer and compiled graphs (stored in `threading.local`). The databases run in WAL mode with `busy_timeout=30000`, so concurrent runs serialise writes instead of failing.
- **Crash semantics are explicit.** A run paused at a gate is durable and resumes from its checkpoint after a restart. A run killed mid-tool-call is marked `failed / process_restart` on startup rather than replayed, because replaying a node can duplicate a side effect (a second CRM write, a second email). Both behaviours are tested.
- **The approval gate is a real pause, not a flag.** The gate node calls LangGraph's `interrupt()`, which suspends the graph and persists the checkpoint. A rejected tool is never executed — the model is told, and the run finishes `blocked`. Decisions are idempotent (`UPDATE ... WHERE status='pending'`), so a double-click or two racing humans cannot apply twice.
- **Replay has two modes.** Static replay re-derives the plan and compares it with the recorded tool sequence — no side effects. `execute: true` genuinely re-runs the task, auto-decides gates the way the original was decided, tags the new run `version="replay-*"`, and compares tool sequence and outcome. Dashboard stats exclude replay traffic.
- **Real tools are treated as untrusted input.** `web_fetch` validates every redirect hop with `assert_public_url` (loopback/private/link-local/reserved/multicast/unspecified, IPv6 and IPv4-mapped included), caps the body at 1 MB, limits redirects, and restricts schemes to http(s). HTML is converted to text with scripts/styles dropped. Failures in `auto` mode fall back to *labelled* mock data; an SSRF attempt is always an error.
- **Memory retrieval uses BM25Plus, not BM25Okapi.** Classic BM25 IDF is negative for terms present in most documents; on a corpus of one or two memories every score was ≤ 0, so the old `score > 0` filter silently returned nothing. BM25Plus uses a positive IDF, so memory works from the first row. A test proves a stored preference changes the computed quote, and that memories are scoped per agent.
- **Evals are hermetic.** `run_suite` forces mock tools so scores do not depend on network conditions. The model is whatever the server is configured with, so a real-key deployment evaluates its real model (and pays for it).
- **Eval runs are excluded from dashboard stats.** Eval (`eval-*`) and replay (`replay-*`) traffic is test traffic; reliability score, success rate and failure modes use production runs only.
- **API serializes to the contract.** Timestamps are ISO-8601; trace step `input`/`output` are JSON strings; `success` is a real boolean. The DB stores epoch floats — `main.py` converts on the way out.
- **Honest numbers.** Cost is an estimate from reference rates and a token proxy (or provider usage metadata). The README and `docs/EVAL.md` report only measured numbers; anything unverified is under Limitations.

## Data model (SQLite, `warden.db`)

| Table | Contents |
|---|---|
| `runs` | run_id, thread_id, agent_id, task, status, success, result, failure_reason, cost_usd, tokens, duration_ms, version, provider, model, request_id, started_at, ended_at |
| `trace_steps` | id, run_id, seq, type (node/tool/llm/gate/memory), name, input_json, output_json, duration_ms, tokens, cost_usd, status, ts |
| `memories` | id, agent_id, content, category, created_at, updated_at |
| `approvals` | id, run_id, agent_id, tool, args_json, policy_refs_json, status, decided_by, note, created_at, decided_at |
| `evals` | id, candidate, verdict, scenarios_json, baseline_delta, started_at, duration_ms |
| `quests` | id, title, description, failure_mode, xp, status, done_by, done_at |
| `kv` | key/value (eval baseline, total XP) |

Migrations are additive `ALTER TABLE` checks in `db.init_db()`, so an existing database keeps working.

`checkpoints.db` is LangGraph's own checkpoint store (threads, checkpoints, blobs).

## Configuration

All settings are environment variables (see `backend/.env.example`). The important ones:

| Variable | Default | Meaning |
|---|---|---|
| `WARDEN_LLM` | `auto` | `auto` / `openai` / `anthropic` / `ollama` / `deterministic` |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | — | provider credentials |
| `WARDEN_LLM_MODEL` | provider default | model id |
| `OPENAI_BASE_URL` | — | any OpenAI-compatible gateway |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | local Ollama |
| `WARDEN_TOOLS` | `auto` | `auto` (real + labelled fallback) / `real` / `mock` |
| `TAVILY_API_KEY`, `BRAVE_API_KEY` | — | optional search providers (DDG needs no key) |
| `WARDEN_WORKERS` | `4` | background worker threads |
| `WARDEN_MAX_COST_USD` / `_TOKENS` / `_ITERATIONS` | `0.50` / `20000` / `12` | per-run guardrails |
| `WARDEN_CORS_ORIGINS` | `*` | comma-separated origins |

## Frontend structure

```
frontend/src/
  App.tsx            view routing (state-based), backend probe, approval badge
  lib/api.ts         live/demo client; waits for the probe, falls back to mock
                     data on network error; streamRun() wraps EventSource
  lib/mock.ts        clearly-synthetic demo data for demo mode
  lib/types.ts       types mirroring docs/API.md (incl. queued/resuming,
                     streamed step seq, replay execution)
  lib/format.ts      money / duration / date formatting
  components/        Layout, Logo, ui primitives
  views/             Dashboard · Runs · RunDetail (SSE + replay) · Approvals ·
                     Evals · Agents · MemoryView
```

`RunDetail` subscribes to SSE while the run is `queued`, `running` or `resuming`, appends steps by `seq`, updates status live, and reconciles from `GET /api/runs/{id}` on `end` or on stream error.

## Running it

```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                     # optional
uvicorn app.main:app --port 8000         # docs at /docs

# frontend
cd frontend && npm install && npm run dev # http://localhost:5173

# tests (offline: deterministic model + mock tools)
cd backend && .venv/bin/python -m pytest -q
```

## Extending it

- **Add an agent:** implement a graph in `app/agents/`, register it in `AGENT_INFO` (`app/agents/graphs.py`) and in `main.py`'s allowed list.
- **Add a provider:** add a branch to `llm.build_chat_model` and its default model; `resolve_provider` already validates the name.
- **Add a policy or incident:** drop a Markdown file in `backend/policies/` or `backend/incidents/` — the guardrail picks it up by BM25Plus.
- **Add an eval scenario:** add an entry to `backend/app/evals/scenarios.json` with `expect` (`success` | `failure` | `blocked` | `gate_hit_and_success` | `graceful_failure`).
