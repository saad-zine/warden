import {
  ArrowLeft,
  Brain,
  Check,
  GitBranch,
  Play,
  RotateCcw,
  TriangleAlert,
  Wrench,
  X,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { fmtDateTime, fmtMoney, fmtMs, fmtTokens } from '../lib/format';
import type { RunDetail, TraceStep, TraceStepType } from '../lib/types';
import { Badge, Button, Card, CardHeader, EmptyState, StatusBadge } from '../components/ui';
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

function StepRow({ step, index }: { step: TraceStep; index: number }) {
  const [open, setOpen] = useState(step.status !== 'ok');
  const Icon = STEP_ICON[step.type];
  const isGate = step.type === 'gate';
  const isError = step.status === 'error';
  return (
    <li className="relative pb-6 pl-10 last:pb-0">
      <span
        className={cn(
          'absolute left-0 top-0 flex h-7 w-7 items-center justify-center rounded-full ring-1',
          isError
            ? 'bg-red-50 text-red-600 ring-red-200'
            : isGate
              ? 'bg-amber-50 text-amber-600 ring-amber-200'
              : 'bg-teal-50 text-teal-600 ring-teal-200',
        )}
      >
        <Icon className="h-3.5 w-3.5" />
      </span>
      {index < 99 && <span className="absolute left-[13px] top-7 h-[calc(100%-28px)] w-px bg-slate-200" aria-hidden />}
      <div
        className={cn(
          'rounded-lg border px-4 py-3',
          isGate ? 'border-amber-200 bg-amber-50/50' : isError ? 'border-red-200 bg-red-50/50' : 'border-slate-200 bg-white',
        )}
      >
        <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center gap-2 text-left">
          <span className="font-mono text-xs text-slate-400">{String(index + 1).padStart(2, '0')}</span>
          <Badge tone={isGate ? 'amber' : isError ? 'red' : 'teal'}>{STEP_LABEL[step.type]}</Badge>
          <span className="font-mono text-sm font-medium text-slate-900">{step.name}</span>
          <span className="ml-auto flex items-center gap-3 text-xs tabular-nums text-slate-500">
            <span>{fmtMs(step.duration_ms)}</span>
            {step.tokens > 0 && <span>{fmtTokens(step.tokens)} tokens</span>}
            {step.cost_usd > 0 && <span>{fmtMoney(step.cost_usd)}</span>}
            <StatusBadge status={step.status} />
          </span>
        </button>
        {open && (
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Input</p>
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-md bg-slate-900 px-3 py-2 font-mono text-xs leading-relaxed text-slate-100">
                {step.input}
              </pre>
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Output</p>
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-md bg-slate-50 px-3 py-2 font-mono text-xs leading-relaxed text-slate-700 ring-1 ring-inset ring-slate-200">
                {step.output}
              </pre>
            </div>
          </div>
        )}
        <p className="mt-2 text-[11px] text-slate-400">{fmtDateTime(step.ts)}</p>
      </div>
    </li>
  );
}

export function RunDetail({ runId, onBack }: { runId: string; onBack: () => void }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');

  const load = () => {
    api
      .runDetail(runId)
      .then(setRun)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load run'));
  };

  useEffect(load, [runId]);

  async function decide(kind: 'approve' | 'reject') {
    if (!run?.pending_approval) return;
    setBusy(true);
    setNotice(null);
    try {
      const res =
        kind === 'approve'
          ? await api.approveRun(run.run_id, run.pending_approval.approval_id, note)
          : await api.rejectRun(run.run_id, run.pending_approval.approval_id, note);
      setNotice(`Run ${res.status === 'completed' ? 'resumed and completed' : res.status}.`);
      load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Decision failed');
    } finally {
      setBusy(false);
    }
  }

  async function replay() {
    setBusy(true);
    setNotice(null);
    try {
      const res = await api.replayRun(runId);
      setNotice(
        res.divergences.length === 0
          ? `Replayed ${res.replayed_steps} steps against the current agent version — no divergences. The trace reproduces cleanly.`
          : `Replayed ${res.replayed_steps} steps — ${res.divergences.length} divergence(s) found. See the run history for details.`,
      );
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Replay failed');
    } finally {
      setBusy(false);
    }
  }

  if (error) return <EmptyState title="Could not load this run" body={error} />;
  if (!run) return <p className="text-sm text-slate-500">Loading run…</p>;

  const totalCost = run.trace.reduce((s, t) => s + t.cost_usd, 0);
  const totalTokens = run.trace.reduce((s, t) => s + t.tokens, 0);

  return (
    <div className="space-y-5">
      <button onClick={onBack} className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
        <ArrowLeft className="h-4 w-4" /> Back to runs
      </button>

      {notice && (
        <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800">{notice}</div>
      )}

      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-slate-900">{run.task}</h2>
            <p className="mt-1 font-mono text-xs text-slate-400">
              {run.run_id} · thread {run.run_id.replace('run_', 'th_')} · agent {run.agent_id}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusBadge status={run.status} />
              {run.success !== null && (
                <Badge tone={run.success ? 'emerald' : 'red'}>{run.success ? 'Succeeded' : 'Failed'}</Badge>
              )}
              <Badge tone="slate">{run.checkpoints} checkpoints saved</Badge>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={replay} disabled={busy}>
              <RotateCcw className="h-4 w-4" /> Replay trace
            </Button>
          </div>
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-slate-100 pt-4 sm:grid-cols-4">
          {[
            ['Started', fmtDateTime(run.started_at)],
            ['Ended', run.ended_at ? fmtDateTime(run.ended_at) : '—'],
            ['Duration', run.duration_ms ? fmtMs(run.duration_ms) : '—'],
            ['Trace cost', `${fmtMoney(totalCost)} · ${fmtTokens(totalTokens)} tokens`],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-xs text-slate-500">{k}</dt>
              <dd className="mt-0.5 text-sm font-medium tabular-nums text-slate-900">{v}</dd>
            </div>
          ))}
        </dl>
        {run.result && <p className="mt-4 rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">{run.result}</p>}
      </Card>

      {run.pending_approval && (
        <Card className="border-amber-200 p-5">
          <div className="flex items-start gap-3">
            <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-semibold text-slate-900">Paused at an approval gate</h3>
              <p className="mt-1 text-sm text-slate-600">
                The agent wants to run <code className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-xs">{run.pending_approval.tool}</code> with
                these arguments:
              </p>
              <pre className="mt-2 overflow-x-auto rounded-md bg-white px-3 py-2 font-mono text-xs text-slate-700 ring-1 ring-amber-200">
                {JSON.stringify(run.pending_approval.args, null, 2)}
              </pre>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Add a note for the record (optional)"
                className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-600"
              />
              <div className="mt-3 flex gap-2">
                <Button variant="primary" onClick={() => decide('approve')} disabled={busy}>
                  <Check className="h-4 w-4" /> Approve &amp; resume
                </Button>
                <Button variant="danger" onClick={() => decide('reject')} disabled={busy}>
                  <X className="h-4 w-4" /> Reject &amp; block
                </Button>
              </div>
            </div>
          </div>
        </Card>
      )}

      <Card>
        <CardHeader
          title="Trace"
          subtitle={`${run.trace.length} steps recorded — every node, tool call, LLM call, gate and memory lookup, with timings and cost`}
        />
        <div className="px-5 py-5">
          {run.trace.length === 0 ? (
            <EmptyState title="No trace steps recorded" body="This run has no recorded steps yet." />
          ) : (
            <ul>
              {run.trace.map((s, i) => (
                <StepRow key={`${s.ts}-${i}`} step={s} index={i} />
              ))}
            </ul>
          )}
        </div>
      </Card>

      <p className="flex items-center gap-1.5 text-xs text-slate-400">
        <Play className="h-3.5 w-3.5" />
        Replay re-runs the recorded trace against the current agent version with tools in dry-run mode — no side effects.
      </p>
    </div>
  );
}
