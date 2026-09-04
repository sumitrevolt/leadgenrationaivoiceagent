import type { LucideIcon } from 'lucide-react';
import { TrendingDown, TrendingUp } from 'lucide-react';
import { Card, Skeleton } from '@/components/ui/primitives';
import { cn } from '@/lib/utils';

export function StatCard({
  label,
  value,
  delta,
  icon: Icon,
  hint,
  footer,
  invertDelta = false,
}: {
  label: string;
  value: string;
  delta?: number;
  icon: LucideIcon;
  hint?: string;
  footer?: React.ReactNode;
  /** When a decrease is a good thing (e.g. cost, avg handle time). */
  invertDelta?: boolean;
}) {
  const positive = delta === undefined ? null : invertDelta ? delta < 0 : delta > 0;

  return (
    <Card className="p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-wide text-faint">{label}</p>
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand/12 text-brand">
          <Icon className="h-4 w-4" />
        </span>
      </div>

      <p className="mt-3 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</p>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {delta !== undefined && (
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold',
              positive ? 'bg-ok/12 text-ok' : 'bg-danger/12 text-danger',
            )}
          >
            {delta >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
            {delta >= 0 ? '+' : ''}
            {delta.toFixed(1)}%
          </span>
        )}
        {hint && <span className="text-[11px] text-faint">{hint}</span>}
      </div>

      {footer && <div className="mt-3">{footer}</div>}
    </Card>
  );
}

export function StatCardSkeleton() {
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex items-start justify-between">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-8 w-8 rounded-lg" />
      </div>
      <Skeleton className="mt-3 h-7 w-28" />
      <Skeleton className="mt-3 h-3 w-20" />
    </Card>
  );
}
