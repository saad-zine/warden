import { Play, Plus } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { fmtDateTime, fmtMoney, fmtMs } from '../lib/format';
import type { Agent, Run } from '../lib/types';
import { Badge, Button, Card, EmptyState, StatusBadge } from '../components/ui';

export function Runs({ onOpenRun }: { onOpenRun: (id: string) => void }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [agentFilter, setAgentFilter] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [newAgent, setNewAgent] = useState('scout');
  const [newTask, setNewTask] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    Promise.all([
      api.runs({ status: statusFilter || undefined, agent_id: agentFilter || undefined, limit: 50 }),
      api.agents(),
    ])
      .then(([r, a]) => {
        setRuns(r);
        setAgents(a);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load runs'))
      .finally(() => setLoading(false));
  };

  useEffect(load, [statusFilter, agentFilter]);

  async function submitRun() {
    if (!newTask.trim()) return;
    setSubmitting(true);
    setNotice(null);
    try {
      const res = await api.createRun(newAgent, newTask.trim());
      setNotice(
        res.status === 'awaiting_approval'
          ? `Run ${res.run_id} is paused at an approval gate — see the Approvals queue.`
          : `Run ${res.run_id} completed.`,
      );
      setNewTask('');
      setShowNew(false);
      load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Failed to start run');
    } finally {
      setSubmitting(false);
    }
  }

  const selectCls =
    'rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-600';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)} className={selectCls} aria-label="Filter by agent">
          <option value="">All agents</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={selectCls} aria-label="Filter by status">
          <option value="">All statuses</option>
          <option value="completed">Completed</option>
          <option value="running">Running</option>
          <option value="awaiting_approval">Awaiting approval</option>
          <option value="failed">Failed</option>
          <option value="blocked">Blocked</option>
        </select>
        <div className="ml-auto">
          <Button variant="primary" onClick={() => setShowNew((v) => !v)}>
            <Plus className="h-4 w-4" /> New run
          </Button>
        </div>
      </div>

      {notice && (
        <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800">{notice}</div>
      )}

      {showNew && (
        <Card className="p-5">
          <h2 className="text-sm font-semibold text-slate-900">Start a new run</h2>
          <p className="mt-1 text-xs text-slate-500">
            Runs execute against the agent's tools. Actions that write to the CRM pause for human approval.
          </p>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
            <select value={newAgent} onChange={(e) => setNewAgent(e.target.value)} className={selectCls} aria-label="Agent">
              {agents.map((a) => (
                <option key={a.id} value={a.id}>{a.name} — {a.description.slice(0, 60)}…</option>
              ))}
            </select>
            <input
              value={newTask}
              onChange={(e) => setNewTask(e.target.value)}
              placeholder="e.g. Research vendor Acme Corp and draft a brief"
              className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-600"
            />
            <Button variant="primary" onClick={submitRun} disabled={submitting || !newTask.trim()}>
              <Play className="h-4 w-4" /> {submitting ? 'Running…' : 'Run agent'}
            </Button>
          </div>
        </Card>
      )}

      <Card>
        {loading ? (
          <p className="px-5 py-8 text-sm text-slate-500">Loading runs…</p>
        ) : error ? (
          <EmptyState title="Could not load runs" body={error} />
        ) : runs.length === 0 ? (
          <EmptyState title="No runs match these filters" body="Try clearing the agent or status filter." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-xs text-slate-500">
                  <th className="px-5 py-3 font-medium">Task</th>
                  <th className="px-5 py-3 font-medium">Agent</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Result</th>
                  <th className="px-5 py-3 font-medium">Cost</th>
                  <th className="px-5 py-3 font-medium">Duration</th>
                  <th className="px-5 py-3 font-medium">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {runs.map((r) => (
                  <tr key={r.run_id} className="cursor-pointer hover:bg-slate-50" onClick={() => onOpenRun(r.run_id)}>
                    <td className="max-w-sm px-5 py-3">
                      <span className="block truncate font-medium text-slate-900">{r.task}</span>
                      <span className="font-mono text-[11px] text-slate-400">{r.run_id}</span>
                    </td>
                    <td className="px-5 py-3 capitalize text-slate-600">{r.agent_id}</td>
                    <td className="px-5 py-3"><StatusBadge status={r.status} /></td>
                    <td className="px-5 py-3">
                      {r.success === null ? (
                        <span className="text-slate-400">—</span>
                      ) : r.success ? (
                        <Badge tone="emerald">Success</Badge>
                      ) : (
                        <Badge tone="red">Failed</Badge>
                      )}
                    </td>
                    <td className="px-5 py-3 tabular-nums text-slate-600">{fmtMoney(r.cost_usd)}</td>
                    <td className="px-5 py-3 tabular-nums text-slate-600">{r.duration_ms ? fmtMs(r.duration_ms) : '—'}</td>
                    <td className="px-5 py-3 whitespace-nowrap text-slate-500">{fmtDateTime(r.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
