import type { ReactNode } from 'react';
import {
  Activity,
  Bot,
  Brain,
  CheckSquare,
  FlaskConical,
  LayoutDashboard,
  Trophy,
} from 'lucide-react';
import type { Mode } from '../lib/api';
import { PRODUCT_NAME, PRODUCT_TAGLINE } from '../lib/config';
import { cn } from '../lib/cn';
import { DemoBadge, LiveBadge } from './ui';
import { WardenMark } from './Logo';

export type View = 'dashboard' | 'runs' | 'approvals' | 'evals' | 'agents' | 'memory';

export const NAV: { id: View; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'runs', label: 'Runs', icon: Activity },
  { id: 'approvals', label: 'Approvals', icon: CheckSquare },
  { id: 'evals', label: 'Evals', icon: FlaskConical },
  { id: 'agents', label: 'Agents & quests', icon: Trophy },
  { id: 'memory', label: 'Memory', icon: Brain },
];

export function Layout({
  view,
  onNavigate,
  mode,
  pendingCount,
  children,
}: {
  view: View;
  onNavigate: (v: View) => void;
  mode: Mode;
  pendingCount: number;
  children: ReactNode;
}) {
  return (
    <div className="flex h-full bg-white">
      {/* Sidebar */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="flex items-center gap-2.5 px-5 pb-5 pt-6">
          <WardenMark size={36} />
          <div>
            <p className="text-[15px] font-bold leading-tight tracking-tight text-slate-900">{PRODUCT_NAME}</p>
            <p className="text-[11px] leading-tight text-slate-500">{PRODUCT_TAGLINE}</p>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = view === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onNavigate(item.id)}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  active ? 'bg-teal-50 text-teal-700' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900',
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {item.label}
                {item.id === 'approvals' && pendingCount > 0 && (
                  <span className="ml-auto rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800">
                    {pendingCount}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
        <div className="border-t border-slate-100 px-5 py-4">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Bot className="h-4 w-4" />
            <span>2 agents connected</span>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
            Reliability is earned run by run. Every trace, gate and eval is recorded here.
          </p>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 px-6">
          <h1 className="text-sm font-semibold text-slate-900">
            {NAV.find((n) => n.id === view)?.label}
          </h1>
          <div className="flex items-center gap-3">
            {mode === 'live' ? <LiveBadge /> : mode === 'demo' ? <DemoBadge /> : (
              <span className="text-xs text-slate-400">Connecting to backend…</span>
            )}
          </div>
        </header>
        <main className="flex-1 overflow-y-auto bg-slate-50/60 px-6 py-6">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  );
}
