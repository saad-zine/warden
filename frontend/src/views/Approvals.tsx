import { Check, FileText, TriangleAlert, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { markStepDone } from '../lib/gettingStarted';
import { fmtDateTime } from '../lib/format';
import type { Approval } from '../lib/types';
import { Badge, Button, Card, EmptyState, inputCls } from '../components/ui';

function ApprovalCard({ approval, onDecided }: { approval: Approval; onDecided: () => void }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(kind: 'approve' | 'reject') {
    setBusy(true);
    setError(null);
    try {
      await api.decideApproval(approval.id, kind, note);
      markStepDone('approval');
      onDecided();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Decision failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <TriangleAlert className="h-4 w-4 text-warning" strokeWidth={1.5} />
              <code className="rounded-md bg-tint-neutral px-1.5 py-0.5 font-mono text-[13px] font-medium text-ink">
                {approval.tool}
              </code>
              <Badge tone="warning">Needs approval</Badge>
            </div>
            <p className="mt-2 text-sm text-body">
              Agent <span className="font-medium capitalize text-ink">{approval.agent_id}</span> wants to run this
              tool in run <span className="font-mono text-xs text-muted">{approval.run_id}</span>.
              Requested {fmtDateTime(approval.created_at)}.
            </p>
          </div>
          <span className="font-mono text-xs text-faint">{approval.id}</span>
        </div>

        <div className="mt-4">
          <p className="text-xs font-medium uppercase tracking-wide text-faint">Arguments</p>
          <pre className="mt-1 overflow-x-auto rounded-lg bg-[#111111] px-3 py-2.5 font-mono text-xs leading-relaxed text-slate-100">
            {JSON.stringify(approval.args, null, 2)}
          </pre>
        </div>

        <div className="mt-4">
          <p className="text-xs font-medium uppercase tracking-wide text-faint">
            Policy &amp; incident context retrieved by the guardrail
          </p>
          <ul className="mt-2 space-y-2">
            {approval.policy_refs.map((ref) => (
              <li key={ref.doc} className="flex gap-2.5 rounded-lg border border-border bg-wash px-3.5 py-3">
                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-faint" strokeWidth={1.5} />
                <div>
                  <p className="font-mono text-xs font-medium text-ink">{ref.doc}</p>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-body">{ref.excerpt}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-4">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Decision note (optional, stored on the record)"
            className={inputCls}
          />
          {error && <p className="mt-2 text-sm text-error">{error}</p>}
          <div className="mt-3 flex gap-2">
            <Button variant="primary" onClick={() => decide('approve')} disabled={busy}>
              <Check className="h-4 w-4" strokeWidth={1.5} /> Approve
            </Button>
            <Button variant="danger" onClick={() => decide('reject')} disabled={busy}>
              <X className="h-4 w-4" strokeWidth={1.5} /> Reject
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

export function Approvals() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = () => {
    api
      .approvals('pending')
      .then((a) => {
        setApprovals(a);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load approvals'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-ink">Approvals</h1>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
          Every risky action pauses here first. The guardrail retrieves the relevant policy and incident
          documents before you decide — nothing that writes to the CRM, sends a message, or deletes a file
          runs without a human in the loop.
        </p>
      </div>
      {notice && (
        <div className="rounded-lg border border-accent/30 bg-tint-teal px-4 py-3 text-sm text-accent-dark">{notice}</div>
      )}
      {loading ? (
        <p className="text-sm text-muted">Loading approvals…</p>
      ) : error ? (
        <EmptyState title="Could not load the approval queue" body={error} />
      ) : approvals.length === 0 ? (
        <EmptyState
          title="Queue clear — nothing awaiting approval"
          body="When an agent hits a guarded tool (crm_update, send_message, delete_file), it pauses here with the policy context attached."
        />
      ) : (
        approvals.map((a) => (
          <ApprovalCard
            key={a.id}
            approval={a}
            onDecided={() => {
              setNotice(`Decision recorded for ${a.id}. The run has resumed.`);
              load();
            }}
          />
        ))
      )}
    </div>
  );
}
