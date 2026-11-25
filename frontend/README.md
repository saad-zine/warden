# Warden — Frontend

The Warden dashboard: an agent reliability platform. It shows a reliability
score, agent runs with full traces, a human approval queue, a nightly eval
suite, and gamification (levels, streaks, leaderboard, quests).

Built with React 19 + Vite + TypeScript + Tailwind CSS v4, lucide-react icons,
Inter. Clean white enterprise design, sculk-teal accent (`#0D9488`), no dark
mode.

## Branding

The product name lives in exactly one place: `src/lib/config.ts`
(`PRODUCT_NAME = 'Warden'`). The logo mark is the `WardenMark` component in
`src/components/Logo.tsx` — a minimal flat guardian figure with a small cyan
sculk glow in the chest — and the matching `public/favicon.svg`.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # tsc + vite build → dist/
npm run preview  # serve the production build
```

## Backend / demo mode

The app talks to the FastAPI backend at `VITE_API_URL` (default
`http://localhost:8000`), following the contract in
`../docs/API.md`. On startup it probes `GET /health`:

- **Backend up** → every view calls the real API. Approve/reject, run-eval,
  quest completion and memory edits all go through the API and the UI updates
  from the response.
- **Backend unreachable** → the app falls back to **demo mode**, served from
  realistic synthetic mock data in `src/lib/mock.ts` (fictional vendors only:
  Acme Corp, Globex, Initech, Hooli, Umbrella). Every screen is labelled with
  a visible "Demo mode — mock data" badge, and all actions (approve/reject,
  evals, quests, memory CRUD, new runs) work against an in-memory store so the
  UI stays fully navigable. If the backend comes back, the client switches
  back to live mode on the next call.

No endpoints beyond the contract in `../docs/API.md` are used.

## Views

| Sidebar | What it shows |
| --- | --- |
| Dashboard | Reliability score + trend sparkline, runs total, success rate, cost, streak, level badge, cost-over-time chart, top failure modes |
| Runs | Filterable table of runs; click a run for the full trace (nodes, tool calls with inputs/outputs, timings, tokens, approval gates), checkpoints, and a Replay button; start a new run |
| Approvals | Pending approval cards: tool + args, retrieved policy/incident excerpts, Approve / Reject with an optional note |
| Evals | Eval history + per-scenario pass/fail detail, verdict badge (pass / blocked), "Run eval suite" with a current/degraded candidate selector |
| Agents & quests | Leaderboard by reliability score, level definitions, incident quests with XP and a Complete button |
| Memory | Stored facts per agent — list, add, edit, delete |

## Structure

```
src/
  main.tsx            entry point
  App.tsx             view routing + backend probe + approval badge count
  index.css           Tailwind v4 + Inter + teal theme tokens
  lib/
    config.ts         PRODUCT_NAME — the single branding constant
    types.ts          types mirroring docs/API.md
    api.ts            API client with live/demo-mode fallback
    mock.ts           synthetic demo-mode data + in-memory store
    format.ts         money / duration / date helpers
  components/
    Layout.tsx        sidebar + top bar
    Logo.tsx          WardenMark (guardian logo)
    ui.tsx            Card, Badge, Button, Sparkline, BarChart, Modal…
  views/
    Dashboard.tsx  Runs.tsx  RunDetail.tsx  Approvals.tsx
    Evals.tsx  Agents.tsx  MemoryView.tsx
```

## Notes

- Nothing here is pushed to GitHub and no repo is created by this frontend.
- All mock data is synthetic; nothing is presented as real production traffic.
