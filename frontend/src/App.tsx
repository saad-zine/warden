import { useEffect, useState } from 'react';
import { api, getMode, probeBackend, subscribeMode, type Mode } from './lib/api';
import { Layout, type View } from './components/Layout';
import { Dashboard } from './views/Dashboard';
import { Runs } from './views/Runs';
import { RunDetail } from './views/RunDetail';
import { Approvals } from './views/Approvals';
import { Evals } from './views/Evals';
import { Agents } from './views/Agents';
import { MemoryView } from './views/MemoryView';

export default function App() {
  const [mode, setMode] = useState<Mode>(getMode());
  const [view, setView] = useState<View>('dashboard');
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(0);

  // Probe the backend once on startup; the API client falls back to demo
  // mode automatically if it is unreachable.
  useEffect(() => {
    const unsub = subscribeMode(setMode);
    probeBackend();
    return unsub;
  }, []);

  // Keep the sidebar approval badge fresh whenever we are on (or leave) the
  // approvals view, and on first load.
  useEffect(() => {
    let cancelled = false;
    api
      .approvals('pending')
      .then((list) => !cancelled && setPendingCount(list.length))
      .catch(() => !cancelled && setPendingCount(0));
    return () => {
      cancelled = true;
    };
  }, [view, mode]);

  function navigate(v: View) {
    setSelectedRun(null);
    setView(v);
  }

  function openRun(runId: string) {
    setSelectedRun(runId);
    setView('runs');
  }

  return (
    <Layout view={view} onNavigate={navigate} mode={mode} pendingCount={pendingCount}>
      {view === 'dashboard' && <Dashboard onOpenRun={openRun} onGoApprovals={() => navigate('approvals')} />}
      {view === 'runs' && selectedRun === null && <Runs onOpenRun={openRun} />}
      {view === 'runs' && selectedRun !== null && <RunDetail runId={selectedRun} onBack={() => setSelectedRun(null)} />}
      {view === 'approvals' && <Approvals />}
      {view === 'evals' && <Evals />}
      {view === 'agents' && <Agents />}
      {view === 'memory' && <MemoryView />}
    </Layout>
  );
}
