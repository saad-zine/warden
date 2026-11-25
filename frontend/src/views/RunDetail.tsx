import {
  ArrowLeft,
  Brain,
  Check,
  GitBranch,
  Play,
  Radio,
  RotateCcw,
  TriangleAlert,
  Wrench,
  X,
  Zap,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { markStepDone } from '../lib/gettingStarted';
import { fmtDateTime, fmtMoney, fmtMs, fmtTokens } from '../lib/format';
import type { ReplayResult, RunDetail as RunDetailData, RunStatus, TraceStep, TraceStepType } from '../lib/types';
import { Badge, Button, Card, CardHeader, EmptyState, StatusBadge, inputCls } from '../components/ui';
import { cn } from '../lib/cn';

const STEP_ICON: Record<TraceStepType, typeof GitBranch> = {
  node: GitBranch,
  tool: Wrench,
  llm: Brain,
  gate: TriangleAlert,
  memory: Brain,
};

const STEP_LABEL: Record<TraceStepType, string> = {
  node: 'Node',
  tool: 'Tool call',
  llm: 'LLM call',
  gate: 'Approval gate',
  memory: 'Memory',
};

/** Statuses where a worker is (or may be) still producing steps. */
const ACTIVE_STATUSES: RunStatus[] = ['queued', 'running', 'resuming'];

function StepRow({ step, index }: { step: TraceStep; index: number }) {
  const [open, setOpen] = useState(step.status !== 'ok');
  const Icon = STEP_ICON[step.type];
  const isGate = step.type === 'gate';
  const isError = step.status === 'error';
  return (
    <li className="relative pb-6 pl-10 last:pb-0">
      <span
        className={cn(
          'absolute left-0 top-0 flex h-7 w-7 items-center justify-center rounded-full',
          isError
            ? 'bg-tint-error text-error'
            : isGate
              ? 'bg-tint-warning text-warning'
              : 'bg-tint-teal text-accent',
        )}
      >
        <Icon className="h-3.5 w-3.5" strokeWidth={1.5} />
      </span>
      {index < 99 && <span className="absolute left-[13px] top-7 h-[calc(100%-28px)] w-px bg-border" aria-hidden />}
      <div
        className={cn(
          'rounded-lg border px-4 py-3',
          isGate ? 'border-warning/30 bg-tint-warning/60' : isError ? 'border-error/30 bg-tint-error/60' : 'border-border bg-paper',
        )}
      >
        <button onClick={() => setOpen((v) => !v)} className="flex w-full cursor-pointer items-center gap-2 rounded-md text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50">
          <span className="font-mono text-xs text-faint">{String(index + 1).padStart(2, '0')}</span>
          <Badge tone={isGate ? 'warning' : isError ? 'error' : 'teal'}>{STEP_LABEL[step.type]}</Badge>
          <span className="font-mono text-sm font-medium text-ink">{step.name}</span>
          <span className="ml-auto flex items-center gap-3 text-xs tabular-nums text-muted">
            <span>{fmtMs(step.duration_ms)}</span>
            {step.tokens > 0 && <span>{fmtTokens(step.tokens)} tokens</span>}
            {step.cost_usd > 0 && <span>{fmtMoney(step.cost_usd)}</span>}
            <StatusBadge status={step.status} />
          </span>
        </button>
        {open && (
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-faint">Input</p>
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-lg border border-border/40 bg-[#111111] px-3 py-2 font-mono text-xs leading-relaxed text-slate-100 dark:border-border dark:bg-[#0d0f10]">
                {step.input}
              </pre>
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-faint">Output</p>
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-lg border border-border bg-wash px-3 py-2 font-mono text-xs leading-relaxed text-body">
                {step.output}
              </pre>
            </div>
          </div>
        )}
        <p className="mt-2 text-xs text-faint">{fmtDateTime(step.ts)}</p>
      </div>
    </li>
  );
}

export function RunDetail({ runId, onBack }: { runId: string; onBack: () => void }) {
  const [run, setRun] = useState<RunDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [replay, setReplay] = useState<ReplayResult | null>(null);
  const [sseOk, setSseOk] = useState(true);
  // Highest seq already in state, so a (re)connect asks only for new steps.
  const lastSeq = useRef(0);

  const load = useCallback(() => {
    return api
      .runDetail(runId)
      .then((detail) => {
        lastSeq.current = detail.trace.reduce((m, s) => Math.max(m, s.seq ?? 0), 0);
        setRun(detail);
        setSseOk(true);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load run'));
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const active = !!run && ACTIVE_STATUSES.includes(run.status);
  const streaming = active && sseOk;

  // Follow the run while it executes. The stream is a view over the trace
  // table, so a dropped connection only costs us the live updates — the
  // reconnect/reload reads the durable rows.
  useEffect(() => {
    if (!active) return;
    const stop = api.streamRun(runId, {
      onStep: (step) => {
        if (step.seq !== undefined) {
          if (step.seq <= lastSeq.current) return;
          lastSeq.current = step.seq;
        }
        setRun((prev) => (prev ? { ...prev, trace: [...prev.trace, step] } : prev));
      },
      onStatus: ({ status, success }) => {
        setRun((prev) => (prev ? { ...prev, status, success } : prev));
      },
      onEnd: () => {
        setSseOk(false);
        void load();
      },
      onError: () => {
        setSseOk(false);
        void load();
      },
    });
    return stop;
  }, [active, runId, load]);

  async function decide(kind: 'approve' | 'reject') {
    if (!run?.pending_approval) return;
    setBusy(true);
    setNotice(null);
    try {
      const res =
        kind === 'approve'
          ? await api.approveRun(run.run_id, run.pending_approval.approval_id, note)
          : await api.rejectRun(run.run_id, run.pending_approval.approval_id, note);
      markStepDone('approval');
      setNotice(`Decision recorded — run ${res.status}. Following it to completion below.`);
      // The run resumes in the background; pick up the remaining steps live.
      setRun((prev) => (prev ? { ...prev, status: 'resuming' as RunStatus } : prev));
      await load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Decision failed');
    } finally {
      setBusy(false);
    }
  }

  async function verifyReplay() {
    setBusy(true);
    setNotice(null);
    try {
      const res = await api.replayRun(runId, false);
      setReplay(res);
      setNotice(
        res.divergences.length === 0
          ? `Verified ${res.replayed_steps} recorded tool steps against the current plan — no divergences.`
          : `Verified ${res.replayed_steps} recorded tool steps — ${res.divergences.length} divergence(s) found.`,
      );
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Replay verification failed');
    } finally {
      setBusy(false);
    }
  }

  async function executeReplay() {
    setBusy(true);
    setNotice(null);
    try {
      const res = await api.replayRun(runId, true);
      setReplay(res);
      const exec = res.execution;
      setNotice(
        exec
          ? exec.matches
            ? `Re-executed the task as ${exec.run_id}: identical tool sequence and outcome in ${fmtMs(exec.duration_ms)}.`
            : `Re-executed the task as ${exec.run_id}: it diverged from the original (tool sequence ${exec.same_tool_sequence ? 'matched' : 'differed'}, outcome ${exec.same_outcome ? 'matched' : 'differed'}).`
          : 'Re-execution finished with no comparison data.',
      );
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Re-execution failed');
    } finally {
      setBusy(false);
    }
  }

  if (error) return <EmptyState title="Could not load this run" body={error} />;
  if (!run) return <p className="text-sm text-muted">Loading run…</p>;

  const totalCost = run.trace.reduce((s, t) => s + t.cost_usd, 0);
  const totalTokens = run.trace.reduce((s, t) => s + t.tokens, 0);

  return (
    <div className="space-y-5">
      <button onClick={onBack} className="inline-flex cursor-pointer items-center gap-1.5 rounded-md px-1 py-0.5 text-sm font-medium text-muted transition-colors hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50">
        <ArrowLeft className="h-4 w-4" strokeWidth={1.5} /> Back to runs
      </button>

      {notice && (
        <div className="rounded-lg border border-accent/30 bg-tint-teal px-4 py-3 text-sm text-accent-dark">{notice}</div>
      )}

      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold text-ink">{run.task}</h2>
            <p className="mt-1 font-mono text-xs text-faint">
              {run.run_id} · agent {run.agent_id}
              {run.version ? ` · v${run.version.replace(/^v/, '')}` : ''}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusBadge status={run.status} />
              {streaming && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-tint-teal px-2.5 py-1 text-xs font-medium text-accent-dark">
                  <Radio className="h-3 w-3 animate-pulse" strokeWidth={2} /> Streaming live
                </span>
              )}
              {run.success !== null && (
                <Badge tone={run.success ? 'success' : 'error'}>{run.success ? 'Succeeded' : 'Failed'}</Badge>
              )}
              {run.provider && <Badge tone="neutral">{run.provider}</Badge>}
              {run.model && <Badge tone="neutral">{run.model}</Badge>}
              <Badge tone="neutral">{run.checkpoints} checkpoints saved</Badge>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={verifyReplay} disabled={busy || streaming}>
              <RotateCcw className="h-4 w-4" strokeWidth={1.5} /> Verify trace
            </Button>
            <Button variant="primary" onClick={executeReplay} disabled={busy || streaming || active}>
              <Zap className="h-4 w-4" strokeWidth={1.5} /> Re-run for real
            </Button>
          </div>
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-border/60 pt-4 sm:grid-cols-4">
          {[
            ['Started', fmtDateTime(run.started_at)],
            ['Ended', run.ended_at ? fmtDateTime(run.ended_at) : '—'],
            ['Duration', run.duration_ms ? fmtMs(run.duration_ms) : '—'],
            ['Trace cost', `${fmtMoney(totalCost)} · ${fmtTokens(totalTokens)} tokens`],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-xs text-muted">{k}</dt>
              <dd className="mt-0.5 text-sm font-medium tabular-nums text-ink">{v}</dd>
            </div>
          ))}
        </dl>
        {run.result && <p className="mt-4 rounded-lg border border-border bg-wash px-4 py-3 text-sm text-body">{run.result}</p>}
      </Card>

      {replay?.execution && (
        <Card className={cn('p-5', replay.execution.matches ? 'border-success/30 bg-tint-teal/40' : 'border-warning/30 bg-tint-warning/40')}>
          <h3 className="text-sm font-semibold text-ink">
            Re-execution {replay.execution.matches ? 'reproduced the original run' : 'diverged from the original run'}
          </h3>
          <dl className="mt-3 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            {[
              ['Replay run', replay.execution.run_id],
              ['Tools', replay.execution.tools.join(' → ') || '—'],
              ['Tool sequence', replay.execution.same_tool_sequence ? 'matched' : 'differed'],
              ['Outcome', replay.execution.same_outcome ? 'matched' : 'differed'],
            ].map(([k, v]) => (
              <div key={k} className="min-w-0">
                <dt className="text-xs text-muted">{k}</dt>
                <dd className="mt-0.5 break-words font-medium text-ink">{v}</dd>
              </div>
            ))}
          </dl>
          {replay.divergences.length > 0 && (
            <ul className="mt-3 list-inside list-disc text-sm text-warning">
              {replay.divergences.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {run.pending_approval && (
        <Card className="border-warning/30 bg-tint-warning/50 p-5">
          <div className="flex items-start gap-3">
            <TriangleAlert className="mt-0.5 h-[18px] w-[18px] shrink-0 text-warning" strokeWidth={1.5} />
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-semibold text-ink">Paused at an approval gate</h3>
              <p className="mt-1 text-sm text-body">
                The agent wants to run <code className="rounded bg-paper px-1.5 py-0.5 font-mono text-xs ring-1 ring-inset ring-warning/30">{run.pending_approval.tool}</code> with
                these arguments:
              </p>
              <pre className="mt-2 overflow-x-auto rounded-lg border border-border bg-paper px-3 py-2 font-mono text-xs text-body">
                {JSON.stringify(run.pending_approval.args, null, 2)}
              </pre>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Add a note for the record (optional)"
                className={inputCls}
              />
              <div className="mt-3 flex gap-2">
                <Button variant="primary" onClick={() => decide('approve')} disabled={busy}>
                  <Check className="h-4 w-4" strokeWidth={1.5} /> Approve &amp; resume
                </Button>
                <Button variant="danger" onClick={() => decide('reject')} disabled={busy}>
                  <X className="h-4 w-4" strokeWidth={1.5} /> Reject &amp; block
                </Button>
              </div>
            </div>
          </div>
        </Card>
      )}

      <Card>
        <CardHeader
          title="Trace"
          subtitle={`${run.trace.length} steps recorded — every node, tool call, LLM call, gate and memory lookup, with timings and cost${
            streaming ? ' (updating live)' : ''
          }`}
        />
        <div className="px-5 py-5">
          {run.trace.length === 0 ? (
            <EmptyState
              title={active ? 'Waiting for the agent to start' : 'No trace steps recorded'}
              body={active ? 'Steps appear here as the worker emits them.' : 'This run has no recorded steps.'}
            />
          ) : (
            <ul>
              {run.trace.map((s, i) => (
                <StepRow key={s.seq ?? `${s.ts}-${i}`} step={s} index={i} />
              ))}
            </ul>
          )}
        </div>
      </Card>

      <p className="flex items-start gap-1.5 text-xs text-faint">
        <Play className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
        <span>
          “Verify trace” re-checks the recorded steps against the current plan without side effects. “Re-run for real”
          executes the task again against the current agent (tagged as a replay run so dashboard stats ignore it) and
          compares the tool sequence and outcome. Gated tools still pause for approval.
        </span>
      </p>
    </div>
  );
}
