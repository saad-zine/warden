import { Check, Crown, Flame, Target, Trophy } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { markStepDone } from '../lib/gettingStarted';
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
      markStepDone('quest');
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

  if (loading) return <p className="text-sm text-muted">Loading agents…</p>;
  if (error) return <EmptyState title="Could not load agents" body={error} />;

  const totalXp = quests.filter((q) => q.status === 'done').reduce((s, q) => s + q.xp, 0);
  const openQuests = quests.filter((q) => q.status === 'open');
  const maxScore = Math.max(...board.map((b) => b.reliability_score), 1);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Agents &amp; quests</h1>
        <p className="mt-1 text-sm text-muted">Reliability is earned — agents ranked by score, quests turn failures into XP.</p>
      </div>
      {notice && (
        <div className="rounded-lg border border-accent/30 bg-tint-teal px-4 py-3 text-sm text-accent-dark">{notice}</div>
      )}

      {board.length === 0 ? (
        <Card>
          <EmptyState
            title="No agents yet"
            body="Agents appear here once they are registered and have run at least once."
          />
        </Card>
      ) : (
      <>
      {/* Leaderboard */}
      <Card>
        <CardHeader
          title="Leaderboard"
          subtitle="Agents ranked by reliability score — the score is earned, not assigned"
          action={
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-muted">
              <Flame className="h-4 w-4 text-warning" strokeWidth={1.5} /> {totalXp} XP earned from quests
            </span>
          }
        />
        <ul className="divide-y divide-border/60">
          {board.map((entry, i) => (
            <li key={entry.agent_id} className="flex items-center gap-4 px-5 py-4">
              <span
                className={cn(
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold',
                  i === 0 ? 'bg-tint-warning text-warning' : 'bg-tint-neutral text-muted',
                )}
              >
                {i === 0 ? <Crown className="h-4 w-4" strokeWidth={1.5} /> : i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold capitalize text-ink">{entry.name}</p>
                  <Badge tone={levelTone(entry.level)}>{entry.level}</Badge>
                </div>
                <p className="mt-0.5 text-xs text-muted">
                  {entry.runs} runs · {pct(entry.success_rate)} success rate
                </p>
                <div className="mt-2 h-1.5 w-full max-w-md overflow-hidden rounded-full bg-tint-neutral">
                  <div
                    className="h-full rounded-full bg-accent"
                    style={{ width: `${(entry.reliability_score / maxScore) * 100}%` }}
                  />
                </div>
              </div>
              <div className="text-right">
                <p className="text-2xl font-semibold tabular-nums text-ink">{entry.reliability_score}</p>
                <p className="text-xs text-faint">reliability</p>
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
                  ? 'border-success/30 bg-tint-success/60'
                  : level === 'Battle-tested'
                    ? 'border-accent/30 bg-tint-teal/60'
                    : 'border-border bg-paper',
              )}
            >
              <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                <Trophy className="h-4 w-4 text-faint" strokeWidth={1.5} /> {level}
              </p>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">
                {i === 0 && 'Early days. Works on the happy path; failures are frequent and unexamined.'}
                {i === 1 && 'Holding up under pressure. Failures are understood, gated, and turning into quests.'}
                {i === 2 && 'Trusted with real work. Evals green, gates respected, failures rare and fixed fast.'}
              </p>
              <p className="mt-2 font-mono text-xs text-faint">
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
        <ul className="divide-y divide-border/60">
          {quests.map((q) => (
            <li key={q.id} className="flex items-start gap-4 px-5 py-4">
              <span
                className={cn(
                  'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
                  q.status === 'done' ? 'bg-tint-success text-success' : 'bg-tint-teal text-accent',
                )}
              >
                {q.status === 'done' ? <Check className="h-4 w-4" strokeWidth={1.5} /> : <Target className="h-4 w-4" strokeWidth={1.5} />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className={cn('text-sm font-semibold', q.status === 'done' ? 'text-faint line-through' : 'text-ink')}>
                    {q.title}
                  </p>
                  <Badge tone={q.status === 'done' ? 'success' : 'teal'}>+{q.xp} XP</Badge>
                  {q.status === 'done' && <Badge tone="neutral">Done{q.done_by ? ` by ${q.done_by}` : ''}</Badge>}
                </div>
                <p className="mt-1 text-[13px] leading-relaxed text-body">{q.description}</p>
                <p className="mt-1 font-mono text-xs text-faint">{q.failure_mode}</p>
              </div>
              {q.status === 'open' && (
                <Button variant="secondary" size="sm" onClick={() => completeQuest(q)} disabled={busyQuest === q.id}>
                  {busyQuest === q.id ? 'Completing…' : 'Complete'}
                </Button>
              )}
            </li>
          ))}
        </ul>
        {openQuests.length === 0 && (
          <p className="px-5 py-4 text-sm text-muted">All quests complete. New failure modes will open new ones.</p>
        )}
      </Card>
      </>
      )}
    </div>
  );
}
