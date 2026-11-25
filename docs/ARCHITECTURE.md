# Warden — Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (React 19 + Vite + TypeScript + Tailwind v4)          │
│  Dashboard · Runs (+ trace) · Approvals · Evals · Agents &      │
│  quests · Memory — clean white enterprise UI, teal accent.      │
│  Live mode against the API; labelled demo mode (mock data)      │
│  when the backend is unreachable.                               │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP (JSON)
┌──────────────────────────────▼──────────────────────────────────┐
│  Backend (FastAPI, Python 3.12)  —  app/                        │
│                                                                 │
│  main.py            REST API + serializers (ISO timestamps,     │
│                     JSON-string trace I/O)                      │
│  agents/            LangGraph graphs (Scout, Planner), tools,   │
│    graphs.py        run_agent / resume_run / replay_run,         │
│                     LangGraph checkpointer (SQLite)             │
│    scout.py         ReAct loop: setup → agent → gate → tools    │
│                     → finalize; approval gate via interrupt();  │
│                     loop detection, spend + iteration limits    │
│    planner.py       planner → executor (Scout subgraph) →       │
│                     summarizer with plan-coverage check         │
│    model.py         DeterministicModel — rule-based ReAct       │
│                     policy (derives a step plan from the task,  │
│                     retries a failed tool once). Any LangChain  │
│                     chat model can be plugged in here.          │
│    tools.py         8 mock tools + a behaviour dict to simulate │
│                     failures (fail / timeout / flaky)           │
│  guardrail.py       Policy: which tools need approval; RAG over │
│                     policies/ + incidents/ (BM25) before a gate │
│  memory.py          BM25 retrieval over stored facts            │
│  trace.py           Per-run trace writer (seq, resume-safe)     │
│  analysis.py        Trace cleaning, failure modes, dashboard    │
│                     stats, leaderboard, eval datasets from      │
│                     real traces                                 │
│  evals/suite.py     Fixed 8-scenario suite; baseline compare;   │
│                     verdict pass/blocked                        │
│  db.py              SQLite: runs, trace_steps, memories,        │
│                     approvals, evals, quests, kv                │
└──────────────────────────────┬──────────────────────────────────┘
                               │ SQLite files
                   warden.db (runs/traces/…) · checkpoints.db
                   (LangGraph checkpoints)
```

## Key design decisions

- **LangGraph as a dependency, not a fork.** The orchestration library is `pip install langgraph` (MIT). Warden is the product built on it: the guardrail, trace store, eval suite, memory, and UI are ours.
- **Deterministic demo model.** The demo agents run on a local rule-based model (`DeterministicModel`) so the platform runs offline and the eval suite is reproducible. It is a *demo* model: it derives a step plan from the task text and executes it through tool calls. A real LLM is plugged in by swapping the model in `app/agents/model.py` — the graph, gates, and trace code do not change.
- **Checkpoints are the durability story.** LangGraph's `SqliteSaver` persists graph state after every node. On resume (`Command(resume=…)`), the gate node re-executes from the checkpoint and continues. The run survives a process restart: the run row and trace live in `warden.db`, the graph state in `checkpoints.db`.
- **The approval gate is a real pause, not a flag.** The gate node calls LangGraph's `interrupt()`, which suspends the graph and persists the checkpoint. The run is `awaiting_approval` until a human decides via the API or the Approvals view. A rejected tool is never executed — the model is told, and the run finishes `blocked`.
- **Guardrail RAG is retrieval, not a prompt.** Before a gate decision, the guardrail retrieves the top policy and incident documents (BM25 over `backend/policies/` and `backend/incidents/`) and attaches them to the approval record, so the human sees *why* the action is risky and what went wrong before.
- **Eval runs are excluded from dashboard stats.** Eval traffic (version `eval-*`) is test traffic; the reliability score, success rate, and failure modes are computed from production runs only. Eval results live in the Evals view and in `backend/eval/results.json`.
- **API serializes to the contract.** Timestamps are ISO-8601 strings; trace step `input`/`output` are JSON strings; `success` is a real boolean. The internal DB stores epoch floats — the serializer in `main.py` converts on the way out (see `docs/API.md`).
- **Honest numbers.** Cost is an estimate from reference token rates and a word-count token proxy. The README and `docs/EVAL.md` report only measured numbers; anything unverified is listed under Limitations.

## Data model (SQLite, `warden.db`)

| Table | Contents |
|---|---|
| `runs` | run_id, thread_id, agent_id, task, status, success, result, failure_reason, cost_usd, tokens, duration_ms, version, started_at, ended_at |
| `trace_steps` | id, run_id, seq, type (node/tool/llm/gate/memory), name, input_json, output_json, duration_ms, tokens, cost_usd, status, ts |
| `memories` | id, agent_id, content, category, created_at, updated_at |
| `approvals` | id, run_id, agent_id, tool, args_json, policy_refs_json, status, decided_by, note, created_at, decided_at |
| `evals` | id, candidate, verdict, scenarios_json, baseline_delta, started_at, duration_ms |
| `quests` | id, title, description, failure_mode, xp, status, done_by, done_at |
| `kv` | key/value (eval baseline, total XP) |

`checkpoints.db` is LangGraph's own checkpoint store (threads, checkpoints, blobs).

## Frontend structure

```
frontend/src/
  App.tsx            view routing (state-based), backend probe, approval badge
  lib/api.ts         live/demo client — waits for the probe before fetching,
                     falls back to mock data on network error
  lib/mock.ts        clearly-synthetic demo data for demo mode
  lib/types.ts       types mirroring docs/API.md
  lib/format.ts      money / duration / date formatting
  lib/config.ts      PRODUCT_NAME (single place)
  components/Logo.tsx   WardenMark — minimal guardian figure, sculk glow
  components/Layout.tsx sidebar + live/demo badge
  components/ui.tsx     Card, Badge, BarChart, Sparkline, …
  views/ Dashboard · Runs · RunDetail · Approvals · Evals · Agents · MemoryView
```

## Running it

```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000          # docs at /docs

# frontend
cd frontend && npm install && npm run dev # http://localhost:5173

# tests
cd backend && .venv/bin/python -m pytest tests/ -q
```

## Extending it

- **Add an agent:** implement a graph in `app/agents/`, register it in `AGENT_INFO` (`app/agents/graphs.py`) and in `main.py`'s allowed list.
- **Plug in a real LLM:** replace `DeterministicModel` in `app/agents/model.py` with any LangChain chat model; the graph, gates, and traces are unchanged.
- **Add a policy or incident:** drop a Markdown file in `backend/policies/` or `backend/incidents/` — the guardrail picks it up by BM25.
- **Add an eval scenario:** add an entry to `backend/app/evals/scenarios.json` with `expect` (`success` | `failure` | `blocked` | `gate`).
