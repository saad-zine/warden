import { Check, Crown, Flame, Target, Trophy } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { levelTone, pct } from '../lib/format';
import type { LeaderboardEntry, Quest } from '../lib/types';
import { Badge, Button, Card, CardHeader, EmptyState } from '../components/ui';
import { cn } from '../lib/cn';

const LEVELS = ['Fragile', 'Battle-tested', 'Production-grade'] as const;

export function Agents() {
  const [board, setBoard] = useState<LeaderboardEntry[]>([]);
  const [quests, setQuests] = useState<Quest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyQuest, setBusyQuest] = useState<string | null>(null);

  const load = () => {
    Promise.all([api.leaderboard(), api.quests()])
      .then(([b, q]) => {
        setBoard(b);
        setQuests(q);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load agents'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  async function completeQuest(quest: Quest) {
    setBusyQuest(quest.id);
    setNotice(null);
    try {
      const res = await api.completeQuest(quest.id, 'Fixed and verified in the eval suite.');
      setNotice(
        `Quest complete: "${quest.title}" — +${res.xp_awarded} XP. Total XP is now ${res.total_xp} (level: ${res.level}).`,
      );
      load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Could not complete quest');
    } finally {
      setBusyQuest(null);
    }
  }

  if (loading) return <p className="text-sm text-slate-500">Loading agents…</p>;
  if (error) return <EmptyState title="Could not load agents" body={error} />;

  const totalXp = quests.filter((q) => q.status === 'done').reduce((s, q) => s + q.xp, 0);
  const openQuests = quests.filter((q) => q.status === 'open');
  const maxScore = Math.max(...board.map((b) => b.reliability_score), 1);

  return (
    <div className="space-y-6">
      {notice && (
        <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800">{notice}</div>
      )}

      {/* Leaderboard */}
      <Card>
        <CardHeader
          title="Leaderboard"
          subtitle="Agents ranked by reliability score — the score is earned, not assigned"
          action={
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500">
              <Flame className="h-4 w-4 text-amber-500" /> {totalXp} XP earned from quests
            </span>
          }
        />
        <ul className="divide-y divide-slate-100">
          {board.map((entry, i) => (
            <li key={entry.agent_id} className="flex items-center gap-4 px-5 py-4">
              <span
                className={cn(
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold',
                  i === 0 ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600',
                )}
              >
                {i === 0 ? <Crown className="h-4 w-4" /> : i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold capitalize text-slate-900">{entry.name}</p>
                  <Badge tone={levelTone(entry.level)}>{entry.level}</Badge>
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  {entry.runs} runs · {pct(entry.success_rate)} success rate
                </p>
                <div className="mt-2 h-1.5 w-full max-w-md overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-teal-600"
                    style={{ width: `${(entry.reliability_score / maxScore) * 100}%` }}
                  />
                </div>
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold tabular-nums text-slate-900">{entry.reliability_score}</p>
                <p className="text-[11px] text-slate-400">reliability</p>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      {/* Levels */}
      <Card>
        <CardHeader title="Levels" subtitle="What each level means for an agent" />
        <div className="grid gap-4 px-5 py-4 sm:grid-cols-3">
          {LEVELS.map((level, i) => (
            <div
              key={level}
              className={cn(
                'rounded-lg border p-4',
                level === 'Production-grade'
                  ? 'border-emerald-200 bg-emerald-50/50'
                  : level === 'Battle-tested'
                    ? 'border-teal-200 bg-teal-50/50'
                    : 'border-slate-200 bg-white',
              )}
            >
              <p className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Trophy className="h-4 w-4 text-slate-400" /> {level}
              </p>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
                {i === 0 && 'Early days. Works on the happy path; failures are frequent and unexamined.'}
                {i === 1 && 'Holding up under pressure. Failures are understood, gated, and turning into quests.'}
                {i === 2 && 'Trusted with real work. Evals green, gates respected, failures rare and fixed fast.'}
              </p>
              <p className="mt-2 font-mono text-[11px] text-slate-400">
                {i === 0 ? 'score < 80' : i === 1 ? 'score 80–89' : 'score 90+'}
              </p>
            </div>
          ))}
        </div>
      </Card>

      {/* Quests */}
      <Card>
        <CardHeader
          title="Incident quests"
          subtitle="Each top failure mode becomes a quest. Fix it, complete the quest, earn XP — and the reliability score climbs."
        />
        <ul className="divide-y divide-slate-100">
          {quests.map((q) => (
            <li key={q.id} className="flex items-start gap-4 px-5 py-4">
              <span
                className={cn(
                  'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
                  q.status === 'done' ? 'bg-emerald-100 text-emerald-700' : 'bg-teal-50 text-teal-700',
                )}
              >
                {q.status === 'done' ? <Check className="h-4 w-4" /> : <Target className="h-4 w-4" />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className={cn('text-sm font-semibold', q.status === 'done' ? 'text-slate-400 line-through' : 'text-slate-900')}>
                    {q.title}
                  </p>
                  <Badge tone={q.status === 'done' ? 'emerald' : 'teal'}>+{q.xp} XP</Badge>
                  {q.status === 'done' && <Badge tone="slate">Done{q.done_by ? ` by ${q.done_by}` : ''}</Badge>}
                </div>
                <p className="mt-1 text-[13px] leading-relaxed text-slate-600">{q.description}</p>
                <p className="mt-1 font-mono text-[11px] text-slate-400">{q.failure_mode}</p>
              </div>
              {q.status === 'open' && (
                <Button size="sm" onClick={() => completeQuest(q)} disabled={busyQuest === q.id}>
                  {busyQuest === q.id ? 'Completing…' : 'Complete'}
                </Button>
              )}
            </li>
          ))}
        </ul>
        {openQuests.length === 0 && (
          <p className="px-5 py-4 text-sm text-slate-500">All quests complete. New failure modes will open new ones.</p>
        )}
      </Card>
    </div>
  );
}
