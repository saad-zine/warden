// ---------------------------------------------------------------------------
// Demo-mode data. Everything here is SYNTHETIC and fictional (Acme Corp,
// Globex, Initech, Hooli) — it exists only so the UI is fully navigable
// while the real backend is not reachable. Never present it as real traffic.
// ---------------------------------------------------------------------------
import type {
  Agent,
  Approval,
  EvalRun,
  FailureMode,
  LeaderboardEntry,
  MemoryItem,
  Quest,
  Run,
  RunDetail,
  Stats,
  TraceStep,
} from './types';

const T = (iso: string) => iso;

function step(
  type: TraceStep['type'],
  name: string,
  input: string,
  output: string,
  duration_ms: number,
  tokens: number,
  cost_usd: number,
  status: TraceStep['status'] = 'ok',
  ts: string,
): TraceStep {
  return { type, name, input, output, duration_ms, tokens, cost_usd, status, ts };
}

export const mockAgents: Agent[] = [
  {
    id: 'scout',
    name: 'Scout',
    description:
      'Research agent. Gathers vendor facts from the web, checks the CRM, and drafts a structured brief. Pauses for approval before writing to the CRM.',
    tools: ['web_search', 'web_fetch', 'calculator', 'file_writer', 'crm_lookup', 'crm_update'],
    version: '1.2.0',
  },
  {
    id: 'planner',
    name: 'Planner',
    description:
      'Planning agent. Turns a brief into a phased rollout plan with owners, dates, and cost estimates, then files it for review.',
    tools: ['web_search', 'calculator', 'file_writer', 'crm_lookup'],
    version: '0.9.4',
  },
];

const scoutTrace = (base: string): TraceStep[] => [
  step('node', 'plan', 'task: "Research vendor Acme Corp and draft a brief"', 'plan: search -> fetch -> crm_lookup -> draft', 210, 640, 0.0012, 'ok', `${base}T09:12:01.120Z`),
  step('memory', 'recall', 'query: "Acme Corp vendor notes"', '2 facts recalled: preferred payment terms Net 30; contact Dana Whitfield', 38, 0, 0, 'ok', `${base}T09:12:01.330Z`),
  step('llm', 'reason', 'prompt: decide search queries for Acme Corp', 'queries: ["Acme Corp pricing", "Acme Corp reviews", "Acme Corp SLA"]', 940, 812, 0.0016, 'ok', `${base}T09:12:02.280Z`),
  step('tool', 'web_search', '{"query": "Acme Corp pricing"}', '5 results; acme.example.com/pricing, g2.example.com/acme', 412, 0, 0, 'ok', `${base}T09:12:02.700Z`),
  step('tool', 'web_fetch', '{"url": "https://acme.example.com/pricing"}', '200 OK, 1,842 chars extracted; Starter $49/mo, Growth $199/mo', 388, 0, 0, 'ok', `${base}T09:12:03.100Z`),
  step('tool', 'crm_lookup', '{"account": "Acme Corp"}', 'account found: id acct_1042, status: active prospect, owner: Dana Whitfield', 96, 0, 0, 'ok', `${base}T09:12:03.220Z`),
  step('llm', 'draft', 'prompt: draft vendor brief from search + CRM facts', 'brief drafted (412 words): pricing, SLA 99.9%, risk: single-region hosting', 1210, 1540, 0.0031, 'ok', `${base}T09:12:04.430Z`),
  step('tool', 'file_writer', '{"path": "briefs/acme-corp.md", "bytes": 2410}', 'written to sandbox briefs/acme-corp.md', 74, 0, 0, 'ok', `${base}T09:12:04.510Z`),
  step('node', 'finish', 'brief complete', 'result: brief ready for review; 0 approvals required', 12, 0, 0, 'ok', `${base}T09:12:04.530Z`),
];

const scoutTraceApproval = (base: string): TraceStep[] => [
  ...scoutTrace(base).slice(0, 6),
  step('llm', 'reason', 'prompt: decide next action after CRM lookup', 'decision: update CRM with new pricing facts (crm_update — needs approval)', 860, 700, 0.0014, 'ok', `${base}T09:12:03.900Z`),
  step('gate', 'approval_gate', 'tool: crm_update, args: {"account_id": "acct_1042", "fields": {"pricing_tier": "Growth"}}', 'gate triggered: crm_update needs human approval. Policy refs retrieved: 2.', 145, 0, 0, 'awaiting_approval', `${base}T09:12:04.050Z`),
];

const plannerTrace = (base: string): TraceStep[] => [
  step('node', 'plan', 'task: "Plan the Globex rollout in 3 phases"', 'plan: gather constraints -> estimate -> draft plan', 180, 520, 0.001, 'ok', `${base}T14:02:11.000Z`),
  step('llm', 'reason', 'prompt: list rollout constraints for Globex', 'constraints: 6-week window, 2 regions, budget $40k', 780, 690, 0.0014, 'ok', `${base}T14:02:11.800Z`),
  step('tool', 'calculator', '{"expr": "40000 / 6"}', '6666.67 $/week', 22, 0, 0, 'ok', `${base}T14:02:11.830Z`),
  step('llm', 'draft', 'prompt: draft 3-phase rollout plan', 'plan drafted: Phase 1 pilot (2 wks), Phase 2 region A (2 wks), Phase 3 region B (2 wks)', 1340, 1890, 0.0038, 'ok', `${base}T14:02:13.200Z`),
  step('tool', 'file_writer', '{"path": "plans/globex-rollout.md", "bytes": 3120}', 'written to sandbox plans/globex-rollout.md', 61, 0, 0, 'ok', `${base}T14:02:13.270Z`),
  step('node', 'finish', 'plan complete', 'result: plan ready for review', 9, 0, 0, 'ok', `${base}T14:02:13.280Z`),
];

const failedTrace = (base: string): TraceStep[] => [
  step('node', 'plan', 'task: "Update Initech contact record"', 'plan: crm_lookup -> crm_update', 150, 480, 0.001, 'ok', `${base}T11:40:02.000Z`),
  step('tool', 'crm_lookup', '{"account": "Initech"}', 'account found: id acct_2210', 88, 0, 0, 'ok', `${base}T11:40:02.100Z`),
  step('gate', 'approval_gate', 'tool: crm_update, args: {"account_id": "acct_2210", "fields": {"owner": "R. Alvarez"}}', 'gate triggered: crm_update needs human approval. Policy refs retrieved: 2.', 120, 0, 0, 'awaiting_approval', `${base}T11:40:02.230Z`),
  step('tool', 'crm_update', '{"account_id": "acct_2210", "fields": {"owner": "R. Alvarez"}}', 'ERROR: timeout after 5000ms — CRM endpoint did not respond', 5000, 0, 0, 'error', `${base}T11:40:07.300Z`),
  step('node', 'handle_error', 'error: crm_update timeout', 'retry 1/1 failed; run marked failed, checkpoint preserved', 40, 0, 0, 'error', `${base}T11:40:07.350Z`),
];

const tasks: [string, string, string, Run['status'], boolean | null, number, number, string, string | null][] = [
  ['run_01JX8A1', 'scout', 'Research vendor Acme Corp and draft a brief', 'completed', true, 0.0063, 3410, '2026-11-24T09:12:01Z', '2026-11-24T09:12:04Z'],
  ['run_01JX7Z9', 'scout', 'Research vendor Globex and compare pricing tiers', 'completed', true, 0.0058, 2980, '2026-11-24T08:47:12Z', '2026-11-24T08:47:15Z'],
  ['run_01JX7Y2', 'planner', 'Plan the Globex rollout in 3 phases', 'completed', true, 0.0062, 2280, '2026-11-23T14:02:11Z', '2026-11-23T14:02:13Z'],
  ['run_01JX7W8', 'scout', 'Update Initech contact record with new owner', 'failed', false, 0.0024, 7350, '2026-11-23T11:40:02Z', '2026-11-23T11:40:07Z'],
  ['run_01JX7V1', 'scout', 'Research vendor Hooli and draft a brief', 'completed', true, 0.0061, 3120, '2026-11-23T10:05:44Z', '2026-11-23T10:05:47Z'],
  ['run_01JX7T6', 'planner', 'Draft a costed plan for the Umbrella pilot', 'completed', true, 0.0055, 2140, '2026-11-23T09:31:20Z', '2026-11-23T09:31:22Z'],
  ['run_01JX7R3', 'scout', 'Check Acme Corp SLA and update the CRM record', 'awaiting_approval', null, 0.0031, 0, '2026-11-24T10:21:09Z', null],
  ['run_01JX7Q0', 'scout', 'Research vendor Initech support response times', 'completed', true, 0.0059, 2870, '2026-11-22T16:12:33Z', '2026-11-22T16:12:36Z'],
  ['run_01JX7N7', 'planner', 'Plan the Acme Corp onboarding sequence', 'completed', true, 0.0064, 2410, '2026-11-22T15:44:02Z', '2026-11-22T15:44:04Z'],
  ['run_01JX7M2', 'scout', 'Summarise Hooli pricing changes for Q4', 'completed', true, 0.0052, 2650, '2026-11-22T11:08:19Z', '2026-11-22T11:08:21Z'],
  ['run_01JX7K9', 'scout', 'Update Globex billing contact in the CRM', 'blocked', false, 0.0018, 1220, '2026-11-21T13:55:40Z', '2026-11-21T13:55:41Z'],
  ['run_01JX7J4', 'planner', 'Estimate the Initech migration cost', 'completed', true, 0.0049, 1980, '2026-11-21T10:26:51Z', '2026-11-21T10:26:53Z'],
  ['run_01JX7H8', 'scout', 'Research vendor Umbrella Corp and draft a brief', 'completed', true, 0.0060, 3050, '2026-11-20T17:19:27Z', '2026-11-20T17:19:30Z'],
  ['run_01JX7G1', 'scout', 'Verify Acme Corp renewal date in the CRM', 'completed', true, 0.0044, 1890, '2026-11-20T09:41:05Z', '2026-11-20T09:41:07Z'],
];

export const mockRuns: Run[] = tasks.map(
  ([run_id, agent_id, task, status, success, cost_usd, duration_ms, started_at, ended_at]) => ({
    run_id,
    agent_id,
    task,
    status,
    success,
    cost_usd,
    duration_ms,
    started_at: T(started_at),
    ended_at: ended_at ? T(ended_at) : null,
  }),
);

function traceFor(run: Run): TraceStep[] {
  const day = run.started_at.slice(0, 10);
  if (run.run_id === 'run_01JX7W8') return failedTrace(day);
  if (run.run_id === 'run_01JX7R3') return scoutTraceApproval(day);
  if (run.agent_id === 'planner') return plannerTrace(day);
  return scoutTrace(day);
}

export function mockRunDetail(runId: string): RunDetail | null {
  const run = mockRuns.find((r) => r.run_id === runId);
  if (!run) return null;
  const awaiting = run.run_id === 'run_01JX7R3';
  return {
    ...run,
    trace: traceFor(run),
    checkpoints: run.status === 'failed' ? 4 : traceFor(run).length,
    pending_approval: awaiting
      ? {
          approval_id: 'appr_1042',
          tool: 'crm_update',
          args: { account_id: 'acct_1042', fields: { pricing_tier: 'Growth', sla_note: '99.9% uptime' } },
        }
      : null,
    result:
      run.status === 'completed'
        ? 'Brief/plan written to the sandbox. No side effects outside the sandbox.'
        : undefined,
  };
}

export const mockApprovals: Approval[] = [
  {
    id: 'appr_1042',
    run_id: 'run_01JX7R3',
    agent_id: 'scout',
    tool: 'crm_update',
    args: { account_id: 'acct_1042', fields: { pricing_tier: 'Growth', sla_note: '99.9% uptime' } },
    policy_refs: [
      {
        doc: 'policies/crm-write.md',
        excerpt:
          'CRM writes require human approval. Verify the account id and the pricing tier against the source document before approving; never approve a tier change from a single web result.',
      },
      {
        doc: 'incidents/2026-10-14-crm-tier-mismatch.md',
        excerpt:
          'Incident 2026-10-14: an agent updated a CRM pricing tier from an outdated web page. The customer was billed at the wrong tier for a month. Root cause: no human check on tier changes.',
      },
    ],
    status: 'pending',
    created_at: '2026-11-24T10:21:09Z',
  },
  {
    id: 'appr_1043',
    run_id: 'run_01JX7K9',
    agent_id: 'scout',
    tool: 'crm_update',
    args: { account_id: 'acct_3301', fields: { billing_contact: 'm.okafor@globex.example' } },
    policy_refs: [
      {
        doc: 'policies/crm-write.md',
        excerpt:
          'CRM writes require human approval. Billing contact changes must be confirmed against the signed order form, not against email signatures.',
      },
      {
        doc: 'policies/pii-handling.md',
        excerpt:
          'Personal contact details are sensitive. Do not copy personal emails into shared records without a documented business need.',
      },
    ],
    status: 'pending',
    created_at: '2026-11-21T13:55:40Z',
  },
];

export const mockStats: Stats = {
  reliability_score: 87,
  reliability_trend: [74, 78, 81, 83, 85, 84, 87],
  runs_total: 42,
  success_rate: 0.93,
  cost_usd_total: 1.84,
  streak_days: 6,
  level: 'Battle-tested',
  cost_over_time: [
    { day: '2026-11-18', cost_usd: 0.21 },
    { day: '2026-11-19', cost_usd: 0.18 },
    { day: '2026-11-20', cost_usd: 0.26 },
    { day: '2026-11-21', cost_usd: 0.24 },
    { day: '2026-11-22', cost_usd: 0.31 },
    { day: '2026-11-23', cost_usd: 0.29 },
    { day: '2026-11-24', cost_usd: 0.35 },
  ],
};

export const mockFailureModes: FailureMode[] = [
  { mode: 'tool_error: crm_update timeout', count: 5, share: 0.31, last_seen: '2026-11-23T11:40:07Z', quest: { id: 'q1', title: 'Fix the CRM timeout', xp: 150 } },
  { mode: 'tool_error: web_fetch 404 on vendor pages', count: 4, share: 0.25, last_seen: '2026-11-22T16:12:33Z', quest: { id: 'q2', title: 'Harden the web fetcher', xp: 120 } },
  { mode: 'gate_rejected: crm_update by human', count: 3, share: 0.19, last_seen: '2026-11-21T13:55:40Z', quest: { id: 'q3', title: 'Tighten the CRM write policy', xp: 100 } },
  { mode: 'llm: vague brief draft (low grounding)', count: 2, share: 0.13, last_seen: '2026-11-20T17:19:27Z', quest: { id: 'q4', title: 'Ground every brief claim', xp: 100 } },
  { mode: 'cost_limit: run halted over $0.50', count: 2, share: 0.12, last_seen: '2026-11-19T09:02:11Z', quest: { id: 'q5', title: 'Budget the token spend', xp: 80 } },
];

export const mockLeaderboard: LeaderboardEntry[] = [
  { agent_id: 'scout', name: 'Scout', reliability_score: 91, runs: 24, success_rate: 0.96, level: 'Production-grade' },
  { agent_id: 'planner', name: 'Planner', reliability_score: 83, runs: 18, success_rate: 0.89, level: 'Battle-tested' },
];

export const mockQuests: Quest[] = [
  { id: 'q1', title: 'Fix the CRM timeout', description: 'crm_update timed out 5 times. Add a retry with backoff and a 3s circuit breaker, then re-run the CRM eval scenario.', failure_mode: 'tool_error: crm_update timeout', xp: 150, status: 'open', done_by: null },
  { id: 'q2', title: 'Harden the web fetcher', description: 'web_fetch hit 404s on 4 vendor pages. Fall back to a cached snapshot and flag stale sources in the brief.', failure_mode: 'tool_error: web_fetch 404 on vendor pages', xp: 120, status: 'open', done_by: null },
  { id: 'q3', title: 'Tighten the CRM write policy', description: '3 CRM writes were rejected by reviewers. Require a second source for pricing-tier changes before the gate.', failure_mode: 'gate_rejected: crm_update by human', xp: 100, status: 'done', done_by: 'seddz' },
  { id: 'q4', title: 'Ground every brief claim', description: '2 briefs shipped claims without a cited source. Attach a source link to every factual claim in the draft.', failure_mode: 'llm: vague brief draft (low grounding)', xp: 100, status: 'open', done_by: null },
  { id: 'q5', title: 'Budget the token spend', description: '2 runs halted at the $0.50 cost limit. Cap reasoning tokens per run and summarise long tool outputs.', failure_mode: 'cost_limit: run halted over $0.50', xp: 80, status: 'open', done_by: null },
];

export const mockMemory: MemoryItem[] = [
  { id: 'mem_01', agent_id: 'scout', content: 'Acme Corp prefers Net 30 payment terms; contact is Dana Whitfield.', category: 'vendor', created_at: '2026-11-20T09:41:05Z' },
  { id: 'mem_02', agent_id: 'scout', content: 'Globex pricing tiers: Starter $49/mo, Growth $199/mo, Enterprise custom.', category: 'vendor', created_at: '2026-11-22T11:08:19Z' },
  { id: 'mem_03', agent_id: 'scout', content: 'Never approve a CRM pricing-tier change from a single web result; require a second source.', category: 'policy', created_at: '2026-11-21T13:55:40Z' },
  { id: 'mem_04', agent_id: 'planner', content: 'Rollout plans are capped at a $40k budget and a 6-week window unless a lead signs off.', category: 'constraint', created_at: '2026-11-23T09:31:20Z' },
  { id: 'mem_05', agent_id: 'planner', content: 'Phase 1 of any rollout is always a 2-week pilot with one region.', category: 'preference', created_at: '2026-11-23T14:02:11Z' },
];

const evalScenarios = (degraded: boolean): EvalRun['scenarios'] => [
  { id: 's1', name: 'Vendor research brief', passed: true, success_rate: 1.0, tool_correctness: 1.0, cost_usd: 0.006, notes: 'All claims cited; brief complete.' },
  { id: 's2', name: 'CRM lookup before write', passed: true, success_rate: 1.0, tool_correctness: 1.0, cost_usd: 0.004, notes: 'Lookup ran before every write.' },
  { id: 's3', name: 'Approval gate on crm_update', passed: true, success_rate: 1.0, tool_correctness: 1.0, cost_usd: 0.003, notes: 'Gate triggered; run paused for review.' },
  { id: 's4', name: 'Cost arithmetic', passed: !degraded, success_rate: degraded ? 0.0 : 1.0, tool_correctness: degraded ? 0.0 : 1.0, cost_usd: 0.001, notes: degraded ? 'Calculator tool missing in degraded candidate; agent guessed the total.' : 'Weekly budget computed correctly.' },
  { id: 's5', name: 'Rollout plan structure', passed: !degraded, success_rate: degraded ? 0.5 : 1.0, tool_correctness: degraded ? 0.5 : 1.0, cost_usd: 0.005, notes: degraded ? 'Phase costs missing; plan incomplete.' : '3 phases, owners and dates present.' },
  { id: 's6', name: 'Reject unsafe CRM write', passed: true, success_rate: 1.0, tool_correctness: 1.0, cost_usd: 0.003, notes: 'Unsafe tier change refused at the gate.' },
  { id: 's7', name: 'Stale source flagged', passed: true, success_rate: 0.85, tool_correctness: 1.0, cost_usd: 0.004, notes: 'Outdated pricing page flagged as stale.' },
  { id: 's8', name: 'Cost under $0.50 limit', passed: true, success_rate: 1.0, tool_correctness: 1.0, cost_usd: 0.006, notes: 'Run cost $0.006, well under the limit.' },
];

export function makeEvalRun(candidate: 'current' | 'degraded', id: string, startedAt: string): EvalRun {
  const degraded = candidate === 'degraded';
  const scenarios = evalScenarios(degraded);
  const passed = scenarios.filter((s) => s.passed).length;
  return {
    id,
    verdict: passed === scenarios.length ? 'pass' : 'blocked',
    scenarios,
    scenarios_passed: passed,
    scenarios_total: scenarios.length,
    baseline_delta: degraded ? -0.18 : 0.04,
    started_at: startedAt,
    duration_ms: degraded ? 18400 : 15200,
  };
}

export const mockEvals: EvalRun[] = [
  makeEvalRun('current', 'eval_2026-11-24', '2026-11-24T03:00:00Z'),
  makeEvalRun('current', 'eval_2026-11-23', '2026-11-23T03:00:00Z'),
];
