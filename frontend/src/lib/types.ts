// Types mirroring the Warden API contract (docs/API.md v1).

export type RunStatus =
  | 'running'
  | 'awaiting_approval'
  | 'completed'
  | 'failed'
  | 'blocked';

export type TraceStatus = 'ok' | 'error' | 'awaiting_approval' | 'rejected';

export type TraceStepType = 'node' | 'tool' | 'llm' | 'gate' | 'memory';

export interface TraceStep {
  type: TraceStepType;
  name: string;
  input: string;
  output: string;
  duration_ms: number;
  tokens: number;
  cost_usd: number;
  status: TraceStatus;
  ts: string;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  tools: string[];
  version: string;
}

export interface Run {
  run_id: string;
  agent_id: string;
  task: string;
  status: RunStatus;
  success: boolean | null;
  cost_usd: number;
  duration_ms: number;
  started_at: string;
  ended_at: string | null;
}

export interface PendingApproval {
  approval_id: string;
  tool: string;
  args: Record<string, unknown>;
}

export interface RunDetail extends Run {
  trace: TraceStep[];
  pending_approval?: PendingApproval | null;
  checkpoints: number;
  result?: string;
}

export interface Checkpoint {
  checkpoint_id: string;
  step: string;
  ts: string;
}

export interface Approval {
  id: string;
  run_id: string;
  agent_id: string;
  tool: string;
  args: Record<string, unknown>;
  policy_refs: { doc: string; excerpt: string }[];
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  decided_by?: string | null;
  decided_at?: string | null;
}

export interface MemoryItem {
  id: string;
  agent_id: string;
  content: string;
  category: string;
  created_at: string;
  updated_at?: string;
}

export interface EvalScenario {
  id: string;
  name: string;
  passed: boolean;
  success_rate: number;
  tool_correctness: number;
  cost_usd: number;
  notes: string;
}

export interface EvalRun {
  id: string;
  verdict: 'pass' | 'blocked';
  scenarios: EvalScenario[];
  scenarios_passed?: number;
  scenarios_total?: number;
  baseline_delta: number;
  started_at: string;
  duration_ms: number;
}

export interface CostPoint {
  day: string;
  cost_usd: number;
}

export interface Stats {
  reliability_score: number;
  reliability_trend: number[];
  runs_total: number;
  success_rate: number;
  cost_usd_total: number;
  streak_days: number;
  level: string;
  cost_over_time: CostPoint[];
}

export interface FailureMode {
  mode: string;
  count: number;
  share: number;
  last_seen: string;
  quest: { id: string; title: string; xp: number } | null;
}

export interface LeaderboardEntry {
  agent_id: string;
  name: string;
  reliability_score: number;
  runs: number;
  success_rate: number;
  level: string;
}

export interface Quest {
  id: string;
  title: string;
  description: string;
  failure_mode: string;
  xp: number;
  status: 'open' | 'done';
  done_by: string | null;
}

export interface Health {
  status: string;
  agents: string[];
  runs: number;
  db: string;
  model: string;
}

export interface ReplayResult {
  run_id: string;
  replayed_steps: number;
  divergences: { step: string; detail: string }[];
}

export type LevelName = 'Fragile' | 'Battle-tested' | 'Production-grade';
