import type { ReactNode } from 'react';
import {
  Activity,
  Bot,
  Brain,
  CheckSquare,
  ChevronDown,
  FlaskConical,
  HelpCircle,
  Home,
  Moon,
  Plus,
  Search,
  Sun,
  Trophy,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { Mode } from '../lib/api';
import { loadProgress, subscribeProgress } from '../lib/gettingStarted';
import { PRODUCT_NAME, PRODUCT_TAGLINE } from '../lib/config';
import { cn } from '../lib/cn';
import { useTheme } from '../lib/theme';
import { DemoBadge, LiveBadge } from './ui';
import { WardenMark } from './Logo';

export type View = 'dashboard' | 'runs' | 'approvals' | 'evals' | 'agents' | 'memory';

type NavItem = { id: View; label: string; icon: typeof Home };

const MAIN_NAV: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: Home },
  { id: 'runs', label: 'Runs', icon: Activity },
  { id: 'approvals', label: 'Approvals', icon: CheckSquare },
];

const RECORDS_NAV: NavItem[] = [
  { id: 'evals', label: 'Evals', icon: FlaskConical },
  { id: 'agents', label: 'Agents & quests', icon: Trophy },
  { id: 'memory', label: 'Memory', icon: Brain },
];

export const NAV: NavItem[] = [...MAIN_NAV, ...RECORDS_NAV];

/**
 * Theme toggle — Moon in light mode (switch to dark), Sun in dark mode
 * (switch to light). Persists via lib/theme.tsx (localStorage `warden-theme`).
 */
function ThemeToggle() {
  const { resolved, toggleTheme } = useTheme();
  const isDark = resolved === 'dark';
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="inline-flex cursor-pointer items-center justify-center rounded-lg p-1.5 text-muted transition-colors hover:bg-wash hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
    >
      {isDark ? <Sun className="h-4 w-4" strokeWidth={1.5} /> : <Moon className="h-4 w-4" strokeWidth={1.5} />}
    </button>
  );
}

function NavButton({
  item,
  active,
  pending,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  pending: number;
  onNavigate: (v: View) => void;
}) {
  const Icon = item.icon;
  return (
    <button
      onClick={() => onNavigate(item.id)}
      className={cn(
        'flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50',
        active ? 'bg-tint-neutral font-medium text-ink' : 'font-normal text-body hover:bg-tint-neutral/60 hover:text-ink',
      )}
    >
      <Icon
        className={cn('h-4 w-4 shrink-0', active ? 'text-ink' : 'text-muted')}
        strokeWidth={1.5}
      />
      {item.label}
      {item.id === 'approvals' && pending > 0 && (
        <span className="ml-auto rounded-full bg-tint-warning px-2 py-0.5 text-[11px] font-medium text-warning">
          {pending}
        </span>
      )}
    </button>
  );
}

function SectionLabel({
  label,
  open,
  onToggle,
}: {
  label: string;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="flex w-full cursor-pointer items-center gap-1 px-3 pb-1 pt-4 text-[11px] font-medium uppercase tracking-[0.06em] text-muted transition-colors hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
    >
      <ChevronDown
        className={cn('h-3.5 w-3.5 transition-transform', !open && '-rotate-90')}
        strokeWidth={1.5}
      />
      {label}
    </button>
  );
}

export function Layout({
  view,
  onNavigate,
  onNewRun,
  mode,
  pendingCount,
  children,
}: {
  view: View;
  onNavigate: (v: View) => void;
  onNewRun: () => void;
  mode: Mode;
  pendingCount: number;
  children: ReactNode;
}) {
  const [query, setQuery] = useState('');
  const [recordsOpen, setRecordsOpen] = useState(true);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // ⌘K / Ctrl+K focuses the sidebar search, like Attio.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Getting-started progress: real steps, recomputed when the mode changes
  // and whenever a step is marked done anywhere in the app.
  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      loadProgress(mode).then((p) => !cancelled && setProgress(p)).catch(() => undefined);
    };
    refresh();
    const unsub = subscribeProgress(refresh);
    return () => {
      cancelled = true;
      unsub();
    };
  }, [mode]);

  const q = query.trim().toLowerCase();
  const filtered = q ? NAV.filter((n) => n.label.toLowerCase().includes(q)) : null;
  const pageLabel = NAV.find((n) => n.id === view)?.label ?? 'Dashboard';

  return (
    <div className="flex h-full bg-paper">
      {/* Sidebar — Attio structure: logo, search box, grouped nav, getting-started pill, quiet footer */}
      <aside className="flex w-[220px] shrink-0 flex-col border-r border-border bg-wash">
        <div className="flex items-center gap-2.5 px-4 pb-4 pt-5">
          <WardenMark size={32} />
          <div>
            <p className="text-sm font-semibold leading-tight text-ink">{PRODUCT_NAME}</p>
            <p className="text-xs leading-tight text-muted">{PRODUCT_TAGLINE}</p>
          </div>
        </div>

        <div className="px-3 pb-2">
          <div className="flex items-center gap-2 rounded-lg border border-border bg-paper px-2.5 py-1.5 focus-within:border-accent focus-within:ring-4 focus-within:ring-accent/10">
            <Search className="h-4 w-4 shrink-0 text-muted" strokeWidth={1.5} />
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  setQuery('');
                  searchRef.current?.blur();
                }
              }}
              placeholder="Search"
              aria-label="Search views"
              className="min-w-0 flex-1 bg-transparent text-sm text-ink placeholder:text-muted focus:outline-none"
            />
            <kbd className="rounded border border-border bg-wash px-1.5 py-0.5 font-mono text-[10px] text-muted">
              ⌘K
            </kbd>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-3">
          {filtered ? (
            filtered.length === 0 ? (
              <p className="px-3 py-2 text-[13px] text-muted">No views match “{query}”.</p>
            ) : (
              filtered.map((item) => (
                <NavButton
                  key={item.id}
                  item={item}
                  active={view === item.id}
                  pending={pendingCount}
                  onNavigate={(v) => {
                    setQuery('');
                    onNavigate(v);
                  }}
                />
              ))
            )
          ) : (
            <>
              {MAIN_NAV.map((item) => (
                <NavButton key={item.id} item={item} active={view === item.id} pending={pendingCount} onNavigate={onNavigate} />
              ))}
              <SectionLabel label="Records" open={recordsOpen} onToggle={() => setRecordsOpen((v) => !v)} />
              {recordsOpen &&
                RECORDS_NAV.map((item) => (
                  <NavButton key={item.id} item={item} active={view === item.id} pending={pendingCount} onNavigate={onNavigate} />
                ))}
              <button
                onClick={onNewRun}
                className="mt-3 flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-dashed border-border-strong px-3 py-2 text-sm text-muted transition-colors hover:border-accent hover:bg-paper hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
              >
                <Plus className="h-4 w-4" strokeWidth={1.5} /> New run
              </button>
            </>
          )}
        </nav>

        <div className="px-3 pb-3">
          <button
            onClick={() => onNavigate('dashboard')}
            className="block w-full cursor-pointer rounded-full border border-border bg-paper px-3 py-2 text-left shadow-sm transition-colors hover:border-border-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
            title="Getting started — open the dashboard"
          >
            <span className="flex items-baseline justify-between gap-2 px-0.5">
              <span className="text-[13px] font-medium text-ink">Getting started</span>
              <span className="text-xs tabular-nums text-muted">
                {progress ? `${progress.done}/${progress.total}` : '…'}
              </span>
            </span>
            <span className="mt-1.5 block h-1 overflow-hidden rounded-full bg-tint-neutral">
              <span
                className="block h-full rounded-full bg-accent transition-all"
                style={{ width: progress ? `${(progress.done / progress.total) * 100}%` : '0%' }}
              />
            </span>
          </button>
        </div>

        <div className="border-t border-border px-4 py-4">
          <div className="flex items-center gap-2 text-xs text-muted">
            <Bot className="h-4 w-4" strokeWidth={1.5} />
            <span>2 agents connected</span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-faint">
            Reliability is earned run by run. Every trace, gate and eval is recorded here.
          </p>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar — Attio: breadcrumb left, quiet actions right */}
        <header className="flex h-12 shrink-0 items-center justify-between gap-4 border-b border-border bg-paper px-6">
          <div className="flex items-center gap-1.5 text-sm text-muted">
            <Home className="h-4 w-4" strokeWidth={1.5} />
            <span className="font-medium text-ink">{view === 'dashboard' ? 'Home' : pageLabel}</span>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <a
              href="https://github.com/saad-zine/warden"
              target="_blank"
              rel="noreferrer"
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-muted transition-colors hover:bg-wash hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
            >
              <HelpCircle className="h-4 w-4" strokeWidth={1.5} /> Help
            </a>
            {mode === 'live' ? <LiveBadge /> : mode === 'demo' ? <DemoBadge /> : (
              <span className="text-xs text-faint">Connecting to backend…</span>
            )}
          </div>
        </header>
        <main className="flex-1 overflow-y-auto bg-paper px-6 py-6">
          <div className="mx-auto max-w-[1100px]">{children}</div>
        </main>
      </div>
    </div>
  );
}
