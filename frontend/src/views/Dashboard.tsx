import { AlertTriangle, ArrowRight, Coins, Flame, Gauge, Play } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { fmtDateTime, fmtMoney, levelTone, pct } from '../lib/format';
import type { FailureMode, Run, Stats } from '../lib/types';
import { Badge, BarChart, Card, CardHeader, EmptyState, Sparkline, StatusBadge } from '../components/ui';

function levelLabel(level: string): string {
  if (level === 'Production-grade') return 'Production-grade — trusted with real work';
  if (level === 'Battle-tested') return 'Battle-tested — holding up under pressure';
  return 'Fragile — early days, watch it closely';
}

export function Dashboard({ onOpenRun, onGoApprovals }: { onOpenRun: (id: string) => void; onGoApprovals: () => void }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [failureModes, setFailureModes] = useState<FailureMode[]>([]);
  const [recentRuns, setRecentRuns] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);

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
  if (!stats) return <p className="text-sm text-slate-500">Loading dashboard…</p>;

  const tone = levelTone(stats.level);
  const statCards = [
    { icon: Play, label: 'Runs total', value: String(stats.runs_total), sub: 'all agents, all time' },
    { icon: Gauge, label: 'Success rate', value: pct(stats.success_rate), sub: `${Math.round(stats.success_rate * stats.runs_total)} of ${stats.runs_total} runs succeeded` },
    { icon: Coins, label: 'Total cost', value: fmtMoney(stats.cost_usd_total), sub: 'estimated, local model' },
    { icon: Flame, label: 'Streak', value: `${stats.streak_days} days`, sub: 'without a failed run' },
  ];

  return (
    <div className="space-y-6">
      {/* Reliability hero */}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="p-6 shadow-[0_12px_36px_-18px_rgba(13,148,136,0.45)] ring-1 ring-teal-100 lg:col-span-2">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Reliability score</p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-6xl font-bold tabular-nums tracking-tight text-slate-900">{stats.reliability_score}</span>
                <span className="text-lg font-medium text-slate-400">/ 100</span>
              </div>
              <div className="mt-3">
                <Badge tone={tone}>{stats.level}</Badge>
                <p className="mt-2 text-sm text-slate-500">{levelLabel(stats.level)}</p>
              </div>
            </div>
            <div className="flex flex-col items-end gap-1">
              <Sparkline values={stats.reliability_trend} width={180} height={48} />
              <p className="text-xs text-slate-400">
                Last 7 eval windows · {stats.reliability_trend[0]} → {stats.reliability_trend[stats.reliability_trend.length - 1]}
              </p>
            </div>
          </div>
        </Card>
        <Card className="flex flex-col justify-between p-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Hardening</p>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              Every failed run becomes a quest. Fix the failure mode, earn XP, and the score climbs.
            </p>
          </div>
          <div className="mt-4">
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-teal-600" style={{ width: `${stats.reliability_score}%` }} />
            </div>
            <p className="mt-2 text-xs text-slate-500">
              {100 - stats.reliability_score} points to a perfect score
            </p>
          </div>
        </Card>
      </div>

      {/* Stat cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label} className="p-5">
              <div className="flex items-center gap-2 text-slate-500">
                <Icon className="h-4 w-4" />
                <p className="text-xs font-medium">{s.label}</p>
              </div>
              <p className="mt-2 text-2xl font-bold tabular-nums tracking-tight text-slate-900">{s.value}</p>
              <p className="mt-1 text-xs text-slate-500">{s.sub}</p>
            </Card>
          );
        })}
      </div>

      {/* Cost + failure modes */}
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
              <button onClick={onGoApprovals} className="inline-flex items-center gap-1 text-xs font-medium text-teal-600 hover:text-teal-700">
                Review queue <ArrowRight className="h-3.5 w-3.5" />
              </button>
            }
          />
          <ul className="divide-y divide-slate-100">
            {failureModes.slice(0, 5).map((f) => (
              <li key={f.mode} className="flex items-center gap-3 px-5 py-3">
                <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-[13px] text-slate-800">{f.mode}</p>
                  <p className="text-xs text-slate-500">
                    {f.count} occurrences · {Math.round(f.share * 100)}% of failures · last seen {fmtDateTime(f.last_seen)}
                  </p>
                </div>
                {f.quest && <Badge tone="teal">+{f.quest.xp} XP</Badge>}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {/* Recent runs */}
      <Card>
        <CardHeader title="Recent runs" subtitle="Latest agent executions across all agents" />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs text-slate-500">
                <th className="px-5 py-3 font-medium">Task</th>
                <th className="px-5 py-3 font-medium">Agent</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Cost</th>
                <th className="px-5 py-3 font-medium">Started</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {recentRuns.map((r) => (
                <tr key={r.run_id} className="cursor-pointer hover:bg-slate-50" onClick={() => onOpenRun(r.run_id)}>
                  <td className="max-w-xs truncate px-5 py-3 font-medium text-slate-900">{r.task}</td>
                  <td className="px-5 py-3 capitalize text-slate-600">{r.agent_id}</td>
                  <td className="px-5 py-3"><StatusBadge status={r.status} /></td>
                  <td className="px-5 py-3 tabular-nums text-slate-600">{fmtMoney(r.cost_usd)}</td>
                  <td className="px-5 py-3 text-slate-500">{fmtDateTime(r.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
