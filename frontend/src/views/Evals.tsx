import { CheckCircle2, FlaskConical, Play, XCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { markStepDone } from '../lib/gettingStarted';
import { fmtDateTime, fmtMoney, fmtMs, pct } from '../lib/format';
import type { EvalRun } from '../lib/types';
import { Badge, Button, Card, CardHeader, EmptyState, selectCls } from '../components/ui';
import { cn } from '../lib/cn';

export function Evals() {
  const [evals, setEvals] = useState<EvalRun[]>([]);
  const [selected, setSelected] = useState<EvalRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<'current' | 'degraded'>('current');
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = () => {
    api
      .evals()
      .then((list) => {
        setEvals(list);
        setError(null);
        setSelected((prev) => prev ?? (list.length > 0 ? list[0] : null));
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load evals'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  async function runSuite() {
    setRunning(true);
    setNotice(null);
    try {
      const ev = await api.runEval(candidate);
      markStepDone('eval');
      setEvals((prev) => [ev, ...prev]);
      setSelected(ev);
      setNotice(
        ev.verdict === 'pass'
          ? `Eval suite passed: ${ev.scenarios_passed}/${ev.scenarios_total} scenarios.`
          : `Eval suite BLOCKED the deploy: ${ev.scenarios_passed}/${ev.scenarios_total} scenarios passed. The degraded candidate regressed — see the failed scenarios.`,
      );
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Eval run failed');
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-ink">Evals</h1>
        <p className="mt-1 text-sm text-muted">
          A nightly suite of 8 scenarios runs against the current agent. If it regresses, the verdict is
          <span className="font-medium text-ink"> blocked</span> and the deploy does not ship.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="ml-auto flex items-center gap-2">
          <select value={candidate} onChange={(e) => setCandidate(e.target.value as 'current' | 'degraded')} className={selectCls} aria-label="Candidate">
            <option value="current">Candidate: current</option>
            <option value="degraded">Candidate: degraded (no calculator)</option>
          </select>
          <Button variant="primary" onClick={runSuite} disabled={running}>
            <Play className="h-4 w-4" strokeWidth={1.5} /> {running ? 'Running suite…' : 'Run eval suite'}
          </Button>
        </div>
      </div>

      {notice && (
        <div
          className={cn(
            'rounded-lg border px-4 py-3 text-sm',
            notice.includes('BLOCKED')
              ? 'border-error/30 bg-tint-error text-error'
              : 'border-accent/30 bg-tint-teal text-accent-dark',
          )}
        >
          {notice}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-muted">Loading evals…</p>
      ) : error ? (
        <EmptyState title="Could not load evals" body={error} />
      ) : evals.length === 0 ? (
        <EmptyState title="No eval runs yet" body="Run the suite to get the first verdict." />
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          {/* History */}
          <Card className="lg:col-span-1">
            <CardHeader title="Eval history" subtitle="Nightly runs, newest first" />
            <ul className="divide-y divide-border/60">
              {evals.map((ev) => (
                <li key={ev.id}>
                  <button
                    onClick={() => setSelected(ev)}
                    className={cn(
                      'flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-wash',
                      selected?.id === ev.id && 'bg-tint-teal',
                    )}
                  >
                    <FlaskConical className="h-4 w-4 shrink-0 text-faint" strokeWidth={1.5} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-mono text-[13px] text-ink">{ev.id}</p>
                      <p className="text-xs text-muted">
                        {fmtDateTime(ev.started_at)} · {fmtMs(ev.duration_ms)}
                      </p>
                    </div>
                    <Badge tone={ev.verdict === 'pass' ? 'success' : 'error'}>
                      {ev.verdict === 'pass' ? 'Pass' : 'Blocked'}
                    </Badge>
                    <span className="text-xs tabular-nums text-muted">
                      {ev.scenarios_passed}/{ev.scenarios_total}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          {/* Detail */}
          <div className="lg:col-span-2">
            {selected && (
              <Card>
                <CardHeader
                  title={`Eval ${selected.id}`}
                  subtitle={`Started ${fmtDateTime(selected.started_at)} · ${fmtMs(selected.duration_ms)} · baseline delta ${selected.baseline_delta >= 0 ? '+' : ''}${Math.round(selected.baseline_delta * 100)} pts`}
                  action={
                    <Badge tone={selected.verdict === 'pass' ? 'success' : 'error'}>
                      {selected.verdict === 'pass' ? 'Verdict: pass' : 'Verdict: blocked'}
                    </Badge>
                  }
                />
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-border/60 text-xs uppercase tracking-[0.04em] text-muted">
                        <th className="px-5 py-3 font-medium">Scenario</th>
                        <th className="px-5 py-3 font-medium">Result</th>
                        <th className="px-5 py-3 font-medium">Success</th>
                        <th className="px-5 py-3 font-medium">Tool correctness</th>
                        <th className="px-5 py-3 font-medium">Cost</th>
                        <th className="px-5 py-3 font-medium">Notes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {selected.scenarios.map((s) => (
                        <tr key={s.id}>
                          <td className="px-5 py-3 font-medium text-ink">{s.name}</td>
                          <td className="px-5 py-3">
                            {s.passed ? (
                              <span className="inline-flex items-center gap-1 text-success">
                                <CheckCircle2 className="h-4 w-4" strokeWidth={1.5} /> Pass
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-error">
                                <XCircle className="h-4 w-4" strokeWidth={1.5} /> Fail
                              </span>
                            )}
                          </td>
                          <td className="px-5 py-3 tabular-nums text-body">{pct(s.success_rate)}</td>
                          <td className="px-5 py-3 tabular-nums text-body">{pct(s.tool_correctness)}</td>
                          <td className="px-5 py-3 tabular-nums text-body">{fmtMoney(s.cost_usd)}</td>
                          <td className="max-w-xs px-5 py-3 text-xs leading-relaxed text-muted">{s.notes}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="border-t border-border/60 px-5 py-4">
                  <p className="text-xs leading-relaxed text-muted">
                    Hardening score: {selected.scenarios_passed} of {selected.scenarios_total} scenarios green.
                    {selected.verdict === 'blocked'
                      ? ' A blocked verdict stops the deploy until the regression is fixed — that is the point of the suite.'
                      : ' Every green run lifts the reliability score on the dashboard.'}
                  </p>
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
