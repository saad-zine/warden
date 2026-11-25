// API client for the Warden backend (docs/API.md v1).
//
// Behaviour: on startup the app probes GET /health. If the backend answers,
// every call goes to the real API. If it is unreachable, the client falls
// back to DEMO MODE — the same calls are served from the synthetic mock
// store in mock.ts, and mutations update that in-memory store so the UI
// stays fully interactive. The UI always knows which mode it is in.
import {
  makeEvalRun,
  mockAgents,
  mockApprovals,
  mockEvals,
  mockFailureModes,
  mockLeaderboard,
  mockMemory,
  mockQuests,
  mockRunDetail,
  mockRuns,
  mockStats,
} from './mock';
import type {
  Agent,
  Approval,
  EvalRun,
  FailureMode,
  Health,
  LeaderboardEntry,
  MemoryItem,
  Quest,
  ReplayResult,
  Run,
  RunDetail,
  RunStatus,
  Stats,
  TraceStep,
} from './types';

export type Mode = 'checking' | 'live' | 'demo';

const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

let mode: Mode = 'checking';
const listeners = new Set<(m: Mode) => void>();
let probePromise: Promise<boolean> | null = null;

export function getMode(): Mode {
  return mode;
}

export function subscribeMode(fn: (m: Mode) => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

function setMode(m: Mode) {
  if (mode === m) return;
  mode = m;
  listeners.forEach((fn) => fn(m));
}

/** Probe the backend once. Returns true when the real API is reachable. */
export function probeBackend(): Promise<boolean> {
  if (probePromise) return probePromise;
  probePromise = (async () => {
    try {
      const res = await fetch(`${API_URL}/health`, { signal: AbortSignal.timeout(2500) });
      if (!res.ok) throw new Error(`health ${res.status}`);
      setMode('live');
      return true;
    } catch {
      setMode('demo');
      return false;
    }
  })();
  return probePromise;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    signal: AbortSignal.timeout(10000),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** If a live call fails with a network error, drop to demo mode and re-run the mock. */
async function liveOrDemo<T>(path: string, init: RequestInit | undefined, mockFn: () => T): Promise<T> {
  // While the backend probe is still in flight, wait for it — otherwise a
  // view that mounts before the probe settles would render demo data even
  // though the backend is live.
  if (mode === 'checking') await probeBackend();
  if (mode === 'live') {
    try {
      return await request<T>(path, init);
    } catch (err) {
      if (err instanceof TypeError || (err as Error).message.includes('Failed to fetch')) {
        setMode('demo');
        return mockFn();
      }
      throw err;
    }
  }
  // Small artificial delay so demo interactions still feel like real calls.
  await new Promise((r) => setTimeout(r, 250));
  return mockFn();
}

// ---------------------------------------------------------------------------
// Mutable in-memory demo store (a working copy of the mock data).
// ---------------------------------------------------------------------------
class DemoStore {
  runs: Run[] = structuredClone(mockRuns);
  approvals: Approval[] = structuredClone(mockApprovals);
  memory: MemoryItem[] = structuredClone(mockMemory);
  quests: Quest[] = structuredClone(mockQuests);
  evals: EvalRun[] = structuredClone(mockEvals);
  private runCounter = 100;

  runDetail(runId: string): RunDetail {
    const base = mockRunDetail(runId);
    const local = this.runs.find((r) => r.run_id === runId);
    if (!local) throw new Error(`run not found: ${runId}`);
    if (base) {
      // Overlay the live status from the store (approvals may have changed it).
      return { ...base, status: local.status, success: local.success, ended_at: local.ended_at };
    }
    return {
      ...local,
      trace: [],
      checkpoints: 0,
      pending_approval: null,
    };
  }

  createRun(agentId: string, task: string): { run_id: string; thread_id: string; status: string; agent_id: string } {
    const id = `run_demo_${this.runCounter++}`;
    const now = new Date().toISOString();
    const needsApproval = /crm|update|delete|send|billing/i.test(task);
    this.runs.unshift({
      run_id: id,
      agent_id: agentId,
      task,
      status: needsApproval ? 'awaiting_approval' : 'completed',
      success: needsApproval ? null : true,
      cost_usd: 0.006,
      duration_ms: needsApproval ? 0 : 2400,
      started_at: now,
      ended_at: needsApproval ? null : now,
    });
    if (needsApproval) {
      this.approvals.unshift({
        id: `appr_demo_${this.runCounter}`,
        run_id: id,
        agent_id: agentId,
        tool: 'crm_update',
        args: { account_id: 'acct_demo', fields: { note: 'Updated from demo task' } },
        policy_refs: [
          {
            doc: 'policies/crm-write.md',
            excerpt:
              'CRM writes require human approval. Verify the account id and the fields against the source document before approving.',
          },
        ],
        status: 'pending',
        created_at: now,
      });
    }
    return { run_id: id, thread_id: `th_demo_${this.runCounter}`, status: needsApproval ? 'awaiting_approval' : 'completed', agent_id: agentId };
  }

  decideApproval(approvalId: string, decision: 'approved' | 'rejected', note: string): Approval {
    const a = this.approvals.find((x) => x.id === approvalId);
    if (!a) throw new Error(`approval not found: ${approvalId}`);
    a.status = decision;
    a.decided_by = 'you';
    a.decided_at = new Date().toISOString();
    const run = this.runs.find((r) => r.run_id === a.run_id);
    if (run) {
      run.status = decision === 'approved' ? 'completed' : 'blocked';
      run.success = decision === 'approved';
      run.ended_at = new Date().toISOString();
      if (decision === 'approved') run.duration_ms = 3200;
    }
    void note;
    return a;
  }

  replay(runId: string): ReplayResult {
    const detail = this.runDetail(runId);
    return { run_id: runId, replayed_steps: detail.trace.length, divergences: [] };
  }

  runEval(candidate: 'current' | 'degraded'): EvalRun {
    const ev = makeEvalRun(candidate, `eval_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}`, new Date().toISOString());
    this.evals.unshift(ev);
    return ev;
  }

  completeQuest(questId: string, note: string): { quest_id: string; xp_awarded: number; total_xp: number; level: string } {
    const q = this.quests.find((x) => x.id === questId);
    if (!q) throw new Error(`quest not found: ${questId}`);
    q.status = 'done';
    q.done_by = 'you';
    void note;
    const totalXp = this.quests.filter((x) => x.status === 'done').reduce((s, x) => s + x.xp, 0);
    return { quest_id: questId, xp_awarded: q.xp, total_xp: totalXp, level: totalXp >= 500 ? 'Production-grade' : 'Battle-tested' };
  }
}

const demo = new DemoStore();

// ---------------------------------------------------------------------------
// Public API — same signatures in live and demo mode.
// ---------------------------------------------------------------------------
export const api = {
  health: () => liveOrDemo<Health>('/health', undefined, () => ({ status: 'ok', agents: ['scout', 'planner'], runs: demo.runs.length, db: 'demo', model: 'local-deterministic' })),

  agents: () => liveOrDemo<Agent[]>('/api/agents', undefined, () => mockAgents),

  createRun: (agentId: string, task: string) =>
    liveOrDemo('/api/runs', { method: 'POST', body: JSON.stringify({ agent_id: agentId, task }) }, () => demo.createRun(agentId, task)),

  runs: (params?: { agent_id?: string; status?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.agent_id) qs.set('agent_id', params.agent_id);
    if (params?.status) qs.set('status', params.status);
    if (params?.limit) qs.set('limit', String(params.limit));
    const q = qs.toString() ? `?${qs}` : '';
    return liveOrDemo<Run[]>(`/api/runs${q}`, undefined, () => {
      let list = demo.runs;
      if (params?.agent_id) list = list.filter((r) => r.agent_id === params.agent_id);
      if (params?.status) list = list.filter((r) => r.status === params.status);
      return list.slice(0, params?.limit ?? 50);
    });
  },

  runDetail: (runId: string) =>
    liveOrDemo<RunDetail>(`/api/runs/${runId}`, undefined, () => demo.runDetail(runId)),

  approveRun: (runId: string, approvalId: string, note = '') =>
    liveOrDemo(`/api/runs/${runId}/approve`, { method: 'POST', body: JSON.stringify({ approval_id: approvalId, note }) }, () => {
      demo.decideApproval(approvalId, 'approved', note);
      return { run_id: runId, status: 'completed', result: 'Run resumed and completed after approval.' };
    }),

  rejectRun: (runId: string, approvalId: string, note = '') =>
    liveOrDemo(`/api/runs/${runId}/reject`, { method: 'POST', body: JSON.stringify({ approval_id: approvalId, note }) }, () => {
      demo.decideApproval(approvalId, 'rejected', note);
      return { run_id: runId, status: 'blocked', result: 'Run blocked: the requested action was rejected.' };
    }),

  replayRun: (runId: string, execute = false) =>
    liveOrDemo<ReplayResult>(
      `/api/runs/${runId}/replay`,
      { method: 'POST', body: JSON.stringify({ execute }) },
      () => demo.replay(runId),
    ),

  /**
   * Stream a run's trace steps over SSE. Returns an unsubscribe function.
   * In demo mode there is nothing to stream, so the caller just keeps its
   * existing snapshot (which is already complete).
   */
  streamRun: (
    runId: string,
    handlers: {
      onStep?: (step: TraceStep) => void;
      onStatus?: (status: { status: RunStatus; success: boolean }) => void;
      onEnd?: () => void;
      onError?: () => void;
    },
  ): (() => void) => {
    if (mode !== 'live') return () => undefined;
    const es = new EventSource(`${API_URL}/api/runs/${runId}/events`);
    const parse = <T,>(e: Event): T | null => {
      try {
        return JSON.parse((e as MessageEvent).data) as T;
      } catch {
        return null;
      }
    };
    es.addEventListener('step', (e) => {
      const step = parse<TraceStep>(e);
      if (step) handlers.onStep?.(step);
    });
    es.addEventListener('status', (e) => {
      const status = parse<{ status: RunStatus; success: boolean }>(e);
      if (status) handlers.onStatus?.(status);
    });
    es.addEventListener('end', () => {
      es.close();
      handlers.onEnd?.();
    });
    es.onerror = () => {
      // Network drop or server restart: stop retrying and let the caller
      // reconcile from the database (the trace is durable, SSE is a view).
      es.close();
      handlers.onError?.();
    };
    return () => es.close();
  },

  approvals: (status = 'pending') =>
    liveOrDemo<Approval[]>(`/api/approvals?status=${status}`, undefined, () =>
      status === 'all' ? demo.approvals : demo.approvals.filter((a) => a.status === status),
    ),

  decideApproval: (approvalId: string, decision: 'approve' | 'reject', note = '') =>
    liveOrDemo(`/api/approvals/${approvalId}/${decision}`, { method: 'POST', body: JSON.stringify({ note }) }, () =>
      demo.decideApproval(approvalId, decision === 'approve' ? 'approved' : 'rejected', note),
    ),

  memory: (agentId?: string) => {
    const q = agentId ? `?agent_id=${agentId}` : '';
    return liveOrDemo<MemoryItem[]>(`/api/memory${q}`, undefined, () =>
      agentId ? demo.memory.filter((m) => m.agent_id === agentId) : demo.memory,
    );
  },

  addMemory: (agentId: string, content: string, category: string) =>
    liveOrDemo<MemoryItem>('/api/memory', { method: 'POST', body: JSON.stringify({ agent_id: agentId, content, category }) }, () => {
      const item: MemoryItem = { id: `mem_${Date.now()}`, agent_id: agentId, content, category, created_at: new Date().toISOString() };
      demo.memory.unshift(item);
      return item;
    }),

  updateMemory: (id: string, content: string, category: string) =>
    liveOrDemo<MemoryItem>(`/api/memory/${id}`, { method: 'PUT', body: JSON.stringify({ content, category }) }, () => {
      const item = demo.memory.find((m) => m.id === id);
      if (!item) throw new Error(`memory not found: ${id}`);
      item.content = content;
      item.category = category;
      item.updated_at = new Date().toISOString();
      return item;
    }),

  deleteMemory: (id: string) =>
    liveOrDemo<void>(`/api/memory/${id}`, { method: 'DELETE' }, () => {
      demo.memory = demo.memory.filter((m) => m.id !== id);
    }),

  evals: () => liveOrDemo<EvalRun[]>('/api/evals', undefined, () => demo.evals),

  evalDetail: (evalId: string) =>
    liveOrDemo<EvalRun>(`/api/evals/${evalId}`, undefined, () => {
      const ev = demo.evals.find((e) => e.id === evalId);
      if (!ev) throw new Error(`eval not found: ${evalId}`);
      return ev;
    }),

  runEval: (candidate: 'current' | 'degraded') =>
    liveOrDemo<EvalRun>('/api/evals/run', { method: 'POST', body: JSON.stringify({ candidate }) }, () => demo.runEval(candidate)),

  stats: () => liveOrDemo<Stats>('/api/stats', undefined, () => mockStats),

  failureModes: () => liveOrDemo<FailureMode[]>('/api/failure-modes', undefined, () => mockFailureModes),

  leaderboard: () => liveOrDemo<LeaderboardEntry[]>('/api/leaderboard', undefined, () => mockLeaderboard),

  quests: () => liveOrDemo<Quest[]>('/api/quests', undefined, () => demo.quests),

  completeQuest: (questId: string, note = '') =>
    liveOrDemo(`/api/quests/${questId}/complete`, { method: 'POST', body: JSON.stringify({ note }) }, () => demo.completeQuest(questId, note)),
};
