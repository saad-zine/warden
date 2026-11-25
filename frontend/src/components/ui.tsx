import type { ReactNode } from 'react';
import { FlaskConical } from 'lucide-react';
import type { RunStatus, TraceStatus } from '../lib/types';
import { cn } from '../lib/cn';

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('rounded-xl border border-slate-200 bg-white shadow-sm', className)}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

type BadgeTone = 'slate' | 'teal' | 'emerald' | 'amber' | 'red' | 'sky';

const toneClasses: Record<BadgeTone, string> = {
  slate: 'bg-slate-100 text-slate-700 ring-slate-200',
  teal: 'bg-teal-50 text-teal-700 ring-teal-200',
  emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-700 ring-amber-200',
  red: 'bg-red-50 text-red-700 ring-red-200',
  sky: 'bg-sky-50 text-sky-700 ring-sky-200',
};

export function Badge({ tone = 'slate', children, className }: { tone?: BadgeTone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: RunStatus | TraceStatus }) {
  const map: Record<string, { tone: BadgeTone; label: string }> = {
    completed: { tone: 'emerald', label: 'Completed' },
    running: { tone: 'sky', label: 'Running' },
    awaiting_approval: { tone: 'amber', label: 'Awaiting approval' },
    failed: { tone: 'red', label: 'Failed' },
    blocked: { tone: 'red', label: 'Blocked' },
    ok: { tone: 'emerald', label: 'OK' },
    error: { tone: 'red', label: 'Error' },
    rejected: { tone: 'red', label: 'Rejected' },
  };
  const entry = map[status] ?? { tone: 'slate' as BadgeTone, label: status };
  return <Badge tone={entry.tone}>{entry.label}</Badge>;
}

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
type ButtonSize = 'sm' | 'md';

export function Button({
  variant = 'secondary',
  size = 'md',
  className,
  disabled,
  onClick,
  children,
  type = 'button',
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  disabled?: boolean;
  onClick?: () => void;
  children: ReactNode;
  type?: 'button' | 'submit';
}) {
  const variants: Record<ButtonVariant, string> = {
    primary: 'bg-teal-600 text-white hover:bg-teal-700 shadow-sm disabled:bg-teal-300',
    secondary:
      'bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:text-slate-400',
    danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300',
    ghost: 'bg-transparent text-slate-600 hover:bg-slate-100 disabled:text-slate-300',
  };
  const sizes: Record<ButtonSize, string> = {
    sm: 'px-2.5 py-1.5 text-xs',
    md: 'px-3.5 py-2 text-sm',
  };
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 disabled:cursor-not-allowed',
        variants[variant],
        sizes[size],
        className,
      )}
    >
      {children}
    </button>
  );
}

export function DemoBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 ring-1 ring-inset ring-amber-200">
      <FlaskConical className="h-3.5 w-3.5" />
      Demo mode — mock data
    </span>
  );
}

export function LiveBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-200">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
      Live — backend connected
    </span>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <p className="text-sm font-medium text-slate-900">{title}</p>
      <p className="mt-1 max-w-sm text-sm text-slate-500">{body}</p>
    </div>
  );
}

/** Minimal SVG sparkline — no chart dependency. */
export function Sparkline({ values, width = 160, height = 40 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - 4) + 2;
    const y = height - 4 - ((v - min) / range) * (height - 8);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const area = `2,${height - 2} ${pts.join(' ')} ${width - 2},${height - 2}`;
  return (
    <svg width={width} height={height} className="overflow-visible" role="img" aria-label="Reliability trend">
      <polygon points={area} fill="#CCFBF1" opacity={0.6} />
      <polyline points={pts.join(' ')} fill="none" stroke="#0D9488" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts[pts.length - 1].split(',')[0]} cy={pts[pts.length - 1].split(',')[1]} r={3} fill="#0D9488" />
    </svg>
  );
}

/** Minimal SVG bar chart for cost over time. */
export function BarChart({ data }: { data: { day: string; cost_usd: number }[] }) {
  const max = Math.max(...data.map((d) => d.cost_usd), 0.01);
  return (
    <div className="flex items-end gap-3 px-1 pb-1 pt-2">
      {data.map((d) => (
        <div key={d.day} className="flex flex-1 flex-col items-center gap-1.5">
          <span className="text-[11px] font-medium tabular-nums text-slate-500">${d.cost_usd.toFixed(2)}</span>
          <div
            className="w-full max-w-10 rounded-t-md bg-teal-600/90"
            style={{ height: `${Math.max(6, (d.cost_usd / max) * 96)}px` }}
            title={`${d.day}: $${d.cost_usd.toFixed(2)}`}
          />
          <span className="text-[11px] text-slate-400">{new Date(d.day).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}</span>
        </div>
      ))}
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-xl bg-white shadow-xl ring-1 ring-slate-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600" aria-label="Close">
            ✕
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}
