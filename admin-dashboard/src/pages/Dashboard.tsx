import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Activity,
  ArrowUpRight,
  Gauge,
  Percent,
  PhoneCall,
  RefreshCw,
  Target,
  Timer,
  Users,
  Zap,
  LayoutDashboard,
} from 'lucide-react';
import { api } from '@/api/client';
import { useAsync } from '@/hooks/useAsync';
import { useToast } from '@/components/ui/Toast';
import { PageHeader } from '@/components/layout/Topbar';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorState,
  Progress,
  Skeleton,
} from '@/components/ui/primitives';
import { StatCard, StatCardSkeleton } from '@/components/dashboard/StatCard';
import { OrchestrationView } from '@/components/orchestration/OrchestrationView';
import { useTheme } from '@/lib/theme';
import {
  cn,
  formatDuration,
  formatNumber,
  formatPercent,
  formatRelative,
  titleCase,
} from '@/lib/utils';
import type { DashboardMetrics } from '@/types';

const RANGES = [
  { label: '7 days', value: 7 },
  { label: '30 days', value: 30 },
  { label: '90 days', value: 90 },
] as const;

const PIE_COLORS = ['#818cf8', '#38bdf8', '#34d399', '#fbbf24', '#fb7185', '#a78bfa', '#f472b6'];

function ChartTooltip({
  active,
  payload,
  label,
  valueSuffix = '',
}: {
  active?: boolean;
  payload?: { name?: string; value?: number | string; color?: string; dataKey?: string | number }[];
  label?: string;
  valueSuffix?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 shadow-pop">
      {label !== undefined && <p className="mb-1 text-[11px] font-semibold text-ink">{label}</p>}
      <ul className="space-y-0.5">
        {payload.map((entry, i) => (
          <li key={i} className="flex items-center gap-2 text-xs text-muted">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: entry.color ?? 'rgb(var(--brand))' }}
            />
            <span className="capitalize">{entry.name}</span>
            <span className="ml-auto font-semibold tabular-nums text-ink">
              {formatNumber(Number(entry.value ?? 0))}
              {valueSuffix}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ChartSkeleton({ height = 260 }: { height?: number }) {
  return (
    <div className="flex items-end gap-2 px-4 py-5" style={{ height }}>
      {Array.from({ length: 14 }).map((_, i) => (
        <Skeleton key={i} className="flex-1" style={{ height: `${30 + ((i * 37) % 60)}%` }} />
      ))}
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const toast = useToast();
  const { theme } = useTheme();
  const [range, setRange] = useState<number>(30);
  const [quickRunning, setQuickRunning] = useState<string | null>(null);

  const fetchMetrics = useCallback(() => api.metrics.overview(range), [range]);
  const { data, loading, error, refreshing, reload } = useAsync<DashboardMetrics>(fetchMetrics, [
    range,
  ]);

  const series = useMemo(() => {
    if (!data) return [];
    return data.leadsByDay.map((point, i) => ({
      label: point.label,
      Leads: point.value,
      Calls: data.callsByDay[i]?.value ?? 0,
    }));
  }, [data]);

  const axisColor = theme === 'dark' ? 'rgb(100 116 139)' : 'rgb(148 163 184)';
  const gridColor = theme === 'dark' ? 'rgb(38 49 66)' : 'rgb(226 232 240)';

  async function runQuick(automationId: string, label: string, params: Record<string, string | number | boolean> = {}) {
    setQuickRunning(automationId);
    try {
      const run = await api.automations.trigger(automationId, params);
      toast.success(`${label} complete`, run.message);
      reload();
    } catch (err) {
      toast.error(`${label} failed`, err instanceof Error ? err.message : 'Unknown error.');
    } finally {
      setQuickRunning(null);
    }
  }

  const totals = data?.totals;
  const minutePct = totals ? (totals.minutesUsed / totals.minutesIncluded) * 100 : 0;

  return (
      <div className="space-y-5">
      <PageHeader
        title="Overview"
        description="Pipeline health, voice operations and automation activity at a glance."
        actions={
          <>
            <div className="inline-flex rounded-lg border border-line bg-elevated p-0.5">
              {RANGES.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  onClick={() => setRange(r.value)}
                  className={cn(
                    'rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors',
                    range === r.value
                      ? 'bg-brand text-white'
                      : 'text-muted hover:bg-line/60 hover:text-ink',
                  )}
                >
                  {r.label}
                </button>
              ))}
            </div>
            <Button
              variant="secondary"
              size="md"
              onClick={reload}
              loading={refreshing}
              leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
            >
              <span className="hidden sm:inline">Refresh</span>
            </Button>
          </>
        }
      />

      <Card>
        <CardHeader title="Multi-Agent Orchestration" subtitle="Live agent fleet status and fleet-wide controls" actions={<LayoutDashboard className="h-4 w-4 text-muted" />} />
        <div className="p-4">
          <OrchestrationView />
        </div>
      </Card>

      {error ? (
        <Card>
          <ErrorState
            title="Could not load metrics"
            message={error}
            onRetry={reload}
            retrying={refreshing}
          />
        </Card>
      ) : (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            {loading || !totals || !data ? (
              Array.from({ length: 6 }).map((_, i) => <StatCardSkeleton key={i} />)
            ) : (
              <>
                <StatCard
                  label="Total leads"
                  value={formatNumber(totals.leads)}
                  delta={data.deltas.leads}
                  icon={Users}
                  hint={`+${formatNumber(data.leadsByDay.slice(-7).reduce((s, p) => s + p.value, 0))} this week`}
                />
                <StatCard
                  label="Calls placed"
                  value={formatNumber(totals.calls)}
                  delta={data.deltas.calls}
                  icon={PhoneCall}
                  hint={`last ${range}d`}
                />
                <StatCard
                  label="Converted"
                  value={formatNumber(totals.converted)}
                  delta={data.deltas.converted}
                  icon={Target}
                  hint={`${formatPercent(totals.conversionRate)} of all leads`}
                />
                <StatCard
                  label="Contact rate"
                  value={formatPercent(totals.contactRate)}
                  delta={data.deltas.contactRate}
                  icon={Percent}
                  hint="connected ÷ dialled"
                />
                <StatCard
                  label="Avg call"
                  value={formatDuration(totals.avgCallSeconds)}
                  delta={data.deltas.avgCallSeconds}
                  icon={Timer}
                  invertDelta
                  hint="connected calls"
                />
                <StatCard
                  label="Voice minutes"
                  value={formatNumber(totals.minutesUsed)}
                  icon={Gauge}
                  hint={`of ${formatNumber(totals.minutesIncluded)} included`}
                  footer={
                    <Progress
                      value={minutePct}
                      tone={minutePct > 90 ? 'danger' : minutePct > 70 ? 'warn' : 'ok'}
                    />
                  }
                />
              </>
            )}
          </div>

          {/* Trend + status */}
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader
                title="Leads captured vs calls placed"
                subtitle={`Daily volume over the last ${range} days`}
                actions={
                  <div className="flex items-center gap-3 text-[11px] text-muted">
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-brand" /> Leads
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-info" /> Calls
                    </span>
                  </div>
                }
              />
              {loading || series.length === 0 ? (
                <ChartSkeleton />
              ) : (
                <div className="h-[280px] w-full px-2 py-4 pr-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={series} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                      <defs>
                        <linearGradient id="gradLeads" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#818cf8" stopOpacity={0.45} />
                          <stop offset="100%" stopColor="#818cf8" stopOpacity={0.02} />
                        </linearGradient>
                        <linearGradient id="gradCalls" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.35} />
                          <stop offset="100%" stopColor="#38bdf8" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke={gridColor} strokeDasharray="3 3" vertical={false} />
                      <XAxis
                        dataKey="label"
                        tick={{ fill: axisColor, fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                        minTickGap={24}
                      />
                      <YAxis tick={{ fill: axisColor, fontSize: 11 }} tickLine={false} axisLine={false} width={44} />
                      <Tooltip content={<ChartTooltip />} cursor={{ stroke: gridColor, strokeWidth: 1 }} />
                      <Area
                        type="monotone"
                        dataKey="Leads"
                        stroke="#818cf8"
                        strokeWidth={2}
                        fill="url(#gradLeads)"
                      />
                      <Area
                        type="monotone"
                        dataKey="Calls"
                        stroke="#38bdf8"
                        strokeWidth={2}
                        fill="url(#gradCalls)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>

            <Card>
              <CardHeader title="Pipeline by status" subtitle="Current lead distribution" />
              {loading || !data ? (
                <ChartSkeleton height={280} />
              ) : (
                <div className="h-[280px] w-full py-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={data.leadsByStatus}
                        dataKey="value"
                        nameKey="name"
                        innerRadius="52%"
                        outerRadius="76%"
                        paddingAngle={2}
                        strokeWidth={0}
                      >
                        {data.leadsByStatus.map((entry, i) => (
                          <Cell key={entry.name} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip content={<ChartTooltip />} />
                      <Legend
                        verticalAlign="bottom"
                        height={44}
                        formatter={(value) => (
                          <span className="text-[11px] capitalize text-muted">{value}</span>
                        )}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
          </div>

          {/* Breakdowns */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
            <Card>
              <CardHeader title="Leads by niche" subtitle="Where the pipeline is concentrated" />
              {loading || !data ? (
                <ChartSkeleton height={240} />
              ) : (
                <div className="h-[240px] w-full px-2 py-4 pr-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={data.leadsByNiche}
                      layout="vertical"
                      margin={{ top: 0, right: 12, left: 8, bottom: 0 }}
                      barSize={14}
                    >
                      <CartesianGrid stroke={gridColor} strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" tick={{ fill: axisColor, fontSize: 11 }} tickLine={false} axisLine={false} />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={92}
                        tick={{ fill: axisColor, fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v: string) => titleCase(v)}
                      />
                      <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgb(var(--line))', opacity: 0.35 }} />
                      <Bar dataKey="value" name="Leads" fill="#818cf8" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>

            <Card>
              <CardHeader title="Call outcomes" subtitle={`Disposition mix for last ${range} days`} />
              {loading || !data ? (
                <ChartSkeleton height={240} />
              ) : (
                <div className="h-[240px] w-full py-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={data.outcomeSplit}
                        dataKey="value"
                        nameKey="name"
                        innerRadius="48%"
                        outerRadius="74%"
                        paddingAngle={2}
                        strokeWidth={0}
                      >
                        {data.outcomeSplit.map((entry, i) => (
                          <Cell key={entry.name} fill={PIE_COLORS[(i + 2) % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip content={<ChartTooltip />} />
                      <Legend
                        verticalAlign="bottom"
                        height={40}
                        formatter={(value) => (
                          <span className="text-[11px] capitalize text-muted">
                            {titleCase(String(value))}
                          </span>
                        )}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>

            <Card>
              <CardHeader title="Conversion funnel" subtitle="Stage-by-stage drop-off" />
              {loading || !data ? (
                <ChartSkeleton height={240} />
              ) : (
                <div className="h-[240px] w-full px-2 py-4 pr-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data.funnel} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                      <CartesianGrid stroke={gridColor} strokeDasharray="3 3" vertical={false} />
                      <XAxis
                        dataKey="stage"
                        tick={{ fill: axisColor, fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <YAxis tick={{ fill: axisColor, fontSize: 11 }} tickLine={false} axisLine={false} width={44} />
                      <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgb(var(--line))', opacity: 0.35 }} />
                      <Bar dataKey="count" name="Leads" radius={[4, 4, 0, 0]}>
                        {data.funnel.map((_, i) => (
                          <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
          </div>

          {/* Quick automation + cities */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-1">
              <CardHeader
                title="Quick actions"
                subtitle="Fire an automation on demand"
                actions={
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigate('/automations')}
                    rightIcon={<ArrowUpRight className="h-3.5 w-3.5" />}
                  >
                    All
                  </Button>
                }
              />
              <div className="space-y-2 p-4">
                {(
                  [
                    { id: 'enrich_leads', label: 'Enrich new leads', icon: Activity, params: { limit: 50 } },
                    { id: 'score_leads', label: 'Re-score all leads', icon: Gauge, params: {} },
                    { id: 'auto_dial_batch', label: 'Dial next batch', icon: PhoneCall, params: { batchSize: 10 } },
                  ] as const
                ).map((action) => (
                  <Button
                    key={action.id}
                    variant="secondary"
                    block
                    className="justify-start"
                    loading={quickRunning === action.id}
                    leftIcon={<action.icon className="h-4 w-4 text-brand" />}
                    onClick={() => runQuick(action.id, action.label, action.params)}
                  >
                    {action.label}
                  </Button>
                ))}
              </div>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader title="Top cities" subtitle="Lead concentration by geography" />
              <div className="p-4">
                {loading || !data ? (
                  <div className="space-y-3">
                    {Array.from({ length: 6 }).map((_, i) => (
                      <Skeleton key={i} className="h-4 w-full" />
                    ))}
                  </div>
                ) : (
                  <ul className="space-y-3">
                    {data.topCities.map((city, i) => {
                      const max = data.topCities[0]?.value || 1;
                      return (
                        <li key={city.name} className="flex items-center gap-3">
                          <span className="w-4 shrink-0 text-xs font-semibold text-faint">{i + 1}</span>
                          <span className="w-24 shrink-0 truncate text-sm text-ink">{city.name}</span>
                          <Progress
                            value={(city.value / max) * 100}
                            tone={i === 0 ? 'brand' : 'neutral'}
                            className="flex-1"
                          />
                          <span className="w-10 shrink-0 text-right text-xs font-semibold tabular-nums text-muted">
                            {formatNumber(city.value)}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </Card>
          </div>

          {/* Recent runs */}
          <Card>
            <CardHeader
              title="Recent automation runs"
              subtitle="Every scheduled or manual execution is logged here"
              actions={
                <Badge tone="brand" dot>
                  live
                </Badge>
              }
            />
            <RecentRuns reload={reload} />
          </Card>

          {data && (
            <p className="text-center text-[11px] text-faint">
              Metrics generated {formatRelative(data.generatedAt)} · demo dataset
            </p>
          )}
        </>
      )}
    </div>
  );
}

function RecentRuns({ reload }: { reload: () => void }) {
  const { data, loading, error, reload: refetch } = useAsync(() => api.automations.runs(6), []);

  if (loading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return <ErrorState compact title="Run history unavailable" message={error} onRetry={refetch} />;
  }

  if (!data || data.length === 0) {
    return (
      <div className="px-4 py-10 text-center">
        <p className="text-sm font-medium text-ink">No runs yet</p>
        <p className="mt-1 text-xs text-muted">
          Trigger an automation and its execution log will appear here.
        </p>
        <Button variant="secondary" size="sm" className="mt-3" onClick={reload}>
          Refresh
        </Button>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-line">
      {data.map((run) => (
        <li key={run.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
          <Zap className="h-3.5 w-3.5 shrink-0 text-brand" />
          <span className="min-w-0 flex-1 truncate text-sm text-ink">{run.automationName}</span>
          <Badge tone="neutral">{run.triggeredBy}</Badge>
          <Badge
            tone={run.status === 'success' ? 'ok' : run.status === 'failed' ? 'danger' : 'info'}
            dot
          >
            {run.status}
          </Badge>
          <span className="hidden text-xs tabular-nums text-faint sm:inline">
            {run.recordsProcessed} records
          </span>
          <span className="w-24 text-right text-xs text-faint">{formatRelative(run.startedAt)}</span>
        </li>
      ))}
    </ul>
  );
}
