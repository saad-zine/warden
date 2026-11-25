import type { ReactNode } from 'react';
import { FlaskConical, X } from 'lucide-react';
import type { RunStatus, TraceStatus } from '../lib/types';
import { cn } from '../lib/cn';

/** Shared form control styling (DESIGN.md: white, 1px hairline border, teal focus ring). */
export const inputCls =
  'w-full rounded-lg border border-border bg-paper px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none focus:ring-4 focus:ring-accent/10 disabled:bg-wash disabled:text-faint';
export const selectCls =
  'cursor-pointer rounded-lg border border-border bg-paper px-2.5 py-2 text-sm text-body focus:border-accent focus:outline-none focus:ring-4 focus:ring-accent/10';

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('rounded-lg border border-border bg-paper', className)}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border/60 px-5 py-4">
      <div>
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-[13px] text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

/**
 * Section header — Attio's "Meetings" / "Tasks 0" row: a quiet 16px semibold
 * title on the left, a muted meta note or a small action on the right.
 * Used to group the content of a view; the cards below it carry the detail.
 */
export function SectionHeader({ title, meta, action }: { title: string; meta?: string; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-4">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      {action ?? (meta ? <span className="text-[13px] text-muted">{meta}</span> : null)}
    </div>
  );
}

type BadgeTone = 'neutral' | 'teal' | 'success' | 'warning' | 'error';

const toneClasses: Record<BadgeTone, string> = {
  neutral: 'bg-tint-neutral text-body',
  teal: 'bg-tint-teal text-accent',
  success: 'bg-tint-success text-success',
  warning: 'bg-tint-warning text-warning',
  error: 'bg-tint-error text-error',
};

export function Badge({ tone = 'neutral', children, className }: { tone?: BadgeTone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium',
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
    completed: { tone: 'success', label: 'Completed' },
    running: { tone: 'teal', label: 'Running' },
    awaiting_approval: { tone: 'warning', label: 'Awaiting approval' },
    failed: { tone: 'error', label: 'Failed' },
    blocked: { tone: 'error', label: 'Blocked' },
    ok: { tone: 'success', label: 'OK' },
    error: { tone: 'error', label: 'Error' },
    rejected: { tone: 'error', label: 'Rejected' },
  };
  const entry = map[status] ?? { tone: 'neutral' as BadgeTone, label: status };
  return <Badge tone={entry.tone}>{entry.label}</Badge>;
}

type ButtonVariant = 'primary' | 'accent' | 'secondary' | 'danger' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

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
    primary:
      'border border-ink bg-ink text-white hover:bg-black dark:text-paper dark:hover:bg-white disabled:border-border disabled:bg-wash disabled:text-faint',
    accent:
      'border border-accent bg-accent text-white hover:bg-accent-dark disabled:border-border disabled:bg-wash disabled:text-faint',
    secondary:
      'border border-border bg-paper text-ink hover:border-border-strong hover:bg-wash disabled:border-border disabled:bg-wash disabled:text-faint',
    danger:
      'border border-error bg-error text-white hover:bg-[#b91c1c] dark:hover:bg-[#dc2626] disabled:border-border disabled:bg-wash disabled:text-faint',
    ghost:
      'border border-transparent bg-transparent text-muted hover:bg-wash hover:text-ink disabled:text-faint',
  };
  const sizes: Record<ButtonSize, string> = {
    sm: 'px-3 py-1.5 text-[13px]',
    md: 'px-4 py-2 text-sm',
    lg: 'px-5 py-2.5 text-[15px]',
  };
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-lg font-medium transition-colors focus:outline-none focus-visible:ring-4 focus-visible:ring-accent/20 disabled:cursor-not-allowed',
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
    <span className="inline-flex items-center gap-1.5 rounded-full bg-tint-warning px-2.5 py-1 text-xs font-medium text-warning">
      <FlaskConical className="h-3.5 w-3.5" strokeWidth={1.5} />
      Demo mode — mock data
    </span>
  );
}

export function LiveBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-tint-success px-2.5 py-1 text-xs font-medium text-success">
      <span className="h-1.5 w-1.5 rounded-full bg-success" />
      Live — backend connected
    </span>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="mt-1 max-w-sm text-[13px] text-muted">{body}</p>
      {action && <div className="mt-5">{action}</div>}
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
      <polygon points={area} className="fill-[#ccfbf1] dark:fill-[#134e4a]" opacity={0.6} />
      <polyline points={pts.join(' ')} fill="none" className="stroke-accent" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts[pts.length - 1].split(',')[0]} cy={pts[pts.length - 1].split(',')[1]} r={3} className="fill-accent" />
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
          <span className="text-xs font-medium tabular-nums text-muted">${d.cost_usd.toFixed(2)}</span>
          <div
            className="w-full max-w-10 rounded-t-md bg-accent/90"
            style={{ height: `${Math.max(6, (d.cost_usd / max) * 96)}px` }}
            title={`${d.day}: $${d.cost_usd.toFixed(2)}`}
          />
          <span className="text-xs text-faint">{new Date(d.day).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}</span>
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 dark:bg-black/70" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-xl border border-border bg-paper shadow-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-5 py-4">
          <h3 className="text-base font-semibold text-ink">{title}</h3>
          <button onClick={onClose} className="cursor-pointer rounded-md p-1.5 text-muted transition-colors hover:bg-wash hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50" aria-label="Close">
            <X className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}
