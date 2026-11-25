import { AlertTriangle, ArrowRight, Calendar, Coins, Flame, Gauge, Play } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { fmtDateTime, fmtMoney, levelTone, pct } from '../lib/format';
import type { FailureMode, Run, Stats } from '../lib/types';
import { Badge, BarChart, Button, Card, CardHeader, EmptyState, SectionHeader, Sparkline, StatusBadge } from '../components/ui';
import { AskBox } from '../components/AskBox';

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning, Saad.';
  if (hour < 18) return 'Good afternoon, Saad.';
  return 'Good evening, Saad.';
}

function levelLabel(level: string): string {
  if (level === 'Production-grade') return 'Production-grade — trusted with real work';
  if (level === 'Battle-tested') return 'Battle-tested — holding up under pressure';
  return 'Fragile — early days, watch it closely';
}

const SUGGESTIONS = [
  { label: 'Research a vendor', task: 'Research vendor Acme Corp and draft a brief' },
  { label: 'Update the CRM', task: 'Update the CRM record for Globex Ltd with the latest contact' },
  { label: 'Draft a vendor brief', task: 'Draft a brief on vendor Initech from the latest research' },
];

export function Dashboard({ onOpenRun, onGoApprovals, onGoRuns }: { onOpenRun: (id: string) => void; onGoApprovals: () => void; onGoRuns: () => void }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [failureModes, setFailureModes] = useState<FailureMode[]>([]);
  const [recentRuns, setRecentRuns] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [askTask, setAskTask] = useState('');
  const [askSeed, setAskSeed] = useState(0);
  const askRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.stats(), api.failureModes(), api.runs({ limit: 5 })])
      .then(([s, f, r]) => {
        if (cancelled) return;
        setStats(s);
        setFailureModes(f);
        setRecentRuns(r);
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : 'Failed to load stats'));
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <EmptyState title="Could not load the dashboard" body={error} />;
  if (!stats) return <p className="text-sm text-muted">Loading dashboard…</p>;

  const tone = levelTone(stats.level);
  const statCards = [
    { icon: Play, label: 'Runs total', value: String(stats.runs_total), sub: 'all agents, all time' },
    { icon: Gauge, label: 'Success rate', value: pct(stats.success_rate), sub: `${Math.round(stats.success_rate * stats.runs_total)} of ${stats.runs_total} runs succeeded` },
    { icon: Coins, label: 'Total cost', value: fmtMoney(stats.cost_usd_total), sub: 'estimated, local model' },
    { icon: Flame, label: 'Streak', value: `${stats.streak_days} days`, sub: 'without a failed run' },
  ];

  return (
    <div className="space-y-8">
      {/* Greeting + ask — Attio's home: a large greeting, then the big "Ask anything…" box */}
      <div className="mx-auto max-w-[720px] pt-2">
        <h1 className="text-[28px] font-semibold leading-tight tracking-tight text-ink">{greeting()}</h1>
        <div className="mt-5">
          <AskBox
            key={askSeed}
            initialTask={askTask}
            inputRef={askRef}
            onRunCreated={onOpenRun}
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s.label}
              onClick={() => {
                // Remount the AskBox with the suggestion pre-filled, then focus it.
                setAskTask(s.task);
                setAskSeed((n) => n + 1);
                setTimeout(() => askRef.current?.focus(), 0);
              }}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-border bg-paper px-3 py-1.5 text-[13px] text-body transition-colors hover:border-border-strong hover:bg-wash focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
            >
              <Calendar className="h-3.5 w-3.5 text-muted" strokeWidth={1.5} />
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Reliability */}
      <section>
        <SectionHeader title="Reliability" meta={`${stats.reliability_score} / 100 · ${stats.level}`} />
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="p-6 lg:col-span-2">
            <div className="flex flex-wrap items-start justify-between gap-6">
              <div>
                <p className="text-[13px] font-medium text-muted">Reliability score</p>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-[40px] font-semibold tabular-nums leading-none tracking-tight text-ink">{stats.reliability_score}</span>
                  <span className="text-lg font-medium text-faint">/ 100</span>
                </div>
                <div className="mt-3">
                  <Badge tone={tone}>{stats.level}</Badge>
                  <p className="mt-2 text-sm text-muted">{levelLabel(stats.level)}</p>
                </div>
              </div>
              <div className="flex flex-col items-end gap-1">
                <Sparkline values={stats.reliability_trend} width={180} height={48} />
                <p className="text-xs text-faint">
                  Last 7 eval windows · {stats.reliability_trend[0]} → {stats.reliability_trend[stats.reliability_trend.length - 1]}
                </p>
              </div>
            </div>
          </Card>
          <Card className="flex flex-col justify-between p-6">
            <div>
              <p className="text-[13px] font-medium text-muted">Hardening</p>
              <p className="mt-2 text-sm leading-relaxed text-body">
                Every failed run becomes a quest. Fix the failure mode, earn XP, and the score climbs.
              </p>
            </div>
            <div className="mt-4">
              <div className="h-2 overflow-hidden rounded-full bg-tint-neutral">
                <div className="h-full rounded-full bg-accent" style={{ width: `${stats.reliability_score}%` }} />
              </div>
              <p className="mt-2 text-xs text-muted">
                {100 - stats.reliability_score} points to a perfect score
              </p>
            </div>
          </Card>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {statCards.map((s) => {
            const Icon = s.icon;
            return (
              <Card key={s.label} className="p-5">
                <div className="flex items-center gap-2 text-muted">
                  <Icon className="h-4 w-4" strokeWidth={1.5} />
                  <p className="text-[13px] font-medium">{s.label}</p>
                </div>
                <p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight text-ink">{s.value}</p>
                <p className="mt-1 text-xs text-muted">{s.sub}</p>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Cost + failure modes */}
      <section>
        <SectionHeader title="Cost & failure modes" />
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Cost over time" subtitle="Estimated spend per day, local deterministic model" />
            <div className="px-4 py-3">
              <BarChart data={stats.cost_over_time} />
            </div>
          </Card>
          <Card>
            <CardHeader
              title="Top failure modes"
              subtitle="Where reliability is lost — each one has a quest attached"
              action={
                <button onClick={onGoApprovals} className="inline-flex cursor-pointer items-center gap-1 rounded-md px-1 py-0.5 text-[13px] font-medium text-accent transition-colors hover:text-accent-dark focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50">
                  Review queue <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.5} />
                </button>
              }
            />
            <ul className="divide-y divide-border/60">
              {failureModes.slice(0, 5).map((f) => (
                <li key={f.mode} className="flex items-center gap-3 px-5 py-3">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-warning" strokeWidth={1.5} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-[13px] text-ink">{f.mode}</p>
                    <p className="text-xs text-muted">
                      {f.count} occurrences · {Math.round(f.share * 100)}% of failures · last seen {fmtDateTime(f.last_seen)}
                    </p>
                  </div>
                  {f.quest && <Badge tone="teal">+{f.quest.xp} XP</Badge>}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </section>

      {/* Recent runs */}
      <section>
        <SectionHeader
          title="Recent runs"
          action={
            <button onClick={onGoRuns} className="inline-flex cursor-pointer items-center gap-1 rounded-md px-1 py-0.5 text-[13px] font-medium text-accent transition-colors hover:text-accent-dark focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50">
              View all <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.5} />
            </button>
          }
        />
        <Card>
          {recentRuns.length === 0 ? (
            <EmptyState
              title="No runs yet"
              body="Ask an agent to do something above — the run will show up here with its full trace."
              action={
                <Button variant="accent" onClick={() => askRef.current?.focus()}>
                  <Play className="h-4 w-4" strokeWidth={1.5} /> Start a run
                </Button>
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border/60 text-xs uppercase tracking-[0.04em] text-muted">
                    <th className="px-5 py-3 font-medium">Task</th>
                    <th className="px-5 py-3 font-medium">Agent</th>
                    <th className="px-5 py-3 font-medium">Status</th>
                    <th className="px-5 py-3 font-medium">Cost</th>
                    <th className="px-5 py-3 font-medium">Started</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {recentRuns.map((r) => (
                    <tr key={r.run_id} className="cursor-pointer transition-colors hover:bg-wash" onClick={() => onOpenRun(r.run_id)}>
                      <td className="max-w-xs truncate px-5 py-3 font-medium text-ink">{r.task}</td>
                      <td className="px-5 py-3 capitalize text-body">{r.agent_id}</td>
                      <td className="px-5 py-3"><StatusBadge status={r.status} /></td>
                      <td className="px-5 py-3 tabular-nums text-body">{fmtMoney(r.cost_usd)}</td>
                      <td className="px-5 py-3 text-muted">{fmtDateTime(r.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </section>
    </div>
  );
}
