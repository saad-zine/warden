import { Brain, Pencil, Plus, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { fmtDateTime } from '../lib/format';
import type { Agent, MemoryItem } from '../lib/types';
import { Badge, Button, Card, EmptyState, Modal } from '../components/ui';

const CATEGORIES = ['vendor', 'policy', 'preference', 'constraint', 'fact'] as const;

export function MemoryView() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentFilter, setAgentFilter] = useState<string>('');
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [modal, setModal] = useState<'add' | MemoryItem | null>(null);
  const [content, setContent] = useState('');
  const [category, setCategory] = useState<string>('fact');
  const [modalAgent, setModalAgent] = useState('scout');
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = (agentId?: string) => {
    setLoading(true);
    Promise.all([api.agents(), api.memory(agentId || undefined)])
      .then(([a, m]) => {
        setAgents(a);
        setItems(m);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load memory'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load(agentFilter || undefined);
  }, [agentFilter]);

  function openAdd() {
    setContent('');
    setCategory('fact');
    setModalAgent(agentFilter || 'scout');
    setModal('add');
  }

  function openEdit(item: MemoryItem) {
    setContent(item.content);
    setCategory(item.category);
    setModalAgent(item.agent_id);
    setModal(item);
  }

  async function save() {
    if (!content.trim()) return;
    setSaving(true);
    setNotice(null);
    try {
      if (modal === 'add') {
        await api.addMemory(modalAgent, content.trim(), category);
        setNotice('Memory saved.');
      } else if (modal) {
        await api.updateMemory(modal.id, content.trim(), category);
        setNotice('Memory updated.');
      }
      setModal(null);
      load(agentFilter || undefined);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  async function remove(item: MemoryItem) {
    if (!window.confirm(`Delete this memory?\n\n"${item.content}"`)) return;
    setDeletingId(item.id);
    try {
      await api.deleteMemory(item.id);
      setNotice('Memory deleted.');
      load(agentFilter || undefined);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setDeletingId(null);
    }
  }

  const inputCls =
    'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-600';
  const selectCls =
    'rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-600';

  return (
    <div className="space-y-4">
      <p className="max-w-2xl text-sm leading-relaxed text-slate-600">
        Stored facts the agents recall at run time — vendor details, policies, preferences and constraints.
        What an agent remembers shapes what it does, so every fact is listed, editable and deletable.
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)} className={selectCls} aria-label="Filter by agent">
          <option value="">All agents</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
        <div className="ml-auto">
          <Button variant="primary" onClick={openAdd}>
            <Plus className="h-4 w-4" /> Add memory
          </Button>
        </div>
      </div>

      {notice && (
        <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800">{notice}</div>
      )}

      {loading ? (
        <p className="text-sm text-slate-500">Loading memory…</p>
      ) : error ? (
        <EmptyState title="Could not load memory" body={error} />
      ) : items.length === 0 ? (
        <EmptyState title="No memories stored" body="Add the first fact for this agent." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {items.map((item) => (
            <Card key={item.id} className="flex flex-col p-5">
              <div className="flex items-start gap-2.5">
                <Brain className="mt-0.5 h-4 w-4 shrink-0 text-teal-600" />
                <p className="flex-1 text-sm leading-relaxed text-slate-800">{item.content}</p>
              </div>
              <div className="mt-4 flex items-center gap-2 border-t border-slate-100 pt-3">
                <Badge tone="teal">{item.category}</Badge>
                <span className="text-xs capitalize text-slate-500">{item.agent_id}</span>
                <span className="text-xs text-slate-400">· {fmtDateTime(item.created_at)}</span>
                <span className="ml-auto flex gap-1">
                  <button
                    onClick={() => openEdit(item)}
                    className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    aria-label="Edit memory"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => remove(item)}
                    disabled={deletingId === item.id}
                    className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                    aria-label="Delete memory"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </span>
              </div>
            </Card>
          ))}
        </div>
      )}

      {modal && (
        <Modal title={modal === 'add' ? 'Add a memory' : 'Edit memory'} onClose={() => setModal(null)}>
          <div className="space-y-4">
            {modal === 'add' && (
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-600" htmlFor="mem-agent">Agent</label>
                <select id="mem-agent" value={modalAgent} onChange={(e) => setModalAgent(e.target.value)} className={selectCls}>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))}
                </select>
              </div>
            )}
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600" htmlFor="mem-content">Fact</label>
              <textarea
                id="mem-content"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={3}
                placeholder="e.g. Acme Corp prefers Net 30 payment terms."
                className={inputCls}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600" htmlFor="mem-category">Category</label>
              <select id="mem-category" value={category} onChange={(e) => setCategory(e.target.value)} className={selectCls}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setModal(null)}>Cancel</Button>
              <Button variant="primary" onClick={save} disabled={saving || !content.trim()}>
                {saving ? 'Saving…' : modal === 'add' ? 'Save memory' : 'Save changes'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
