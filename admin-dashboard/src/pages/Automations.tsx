import { useCallback, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Database,
  Eye,
  FlaskConical,
  ListChecks,
  Mail,
  Play,
  RefreshCw,
  ShieldAlert,
  Zap,
  type LucideIcon,
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
  EmptyState,
  ErrorState,
  Field,
  Input,
  Select,
  Skeleton,
  Switch,
} from '@/components/ui/primitives';
import { ConfirmDialog } from '@/components/ui/Modal';
import type {
  AutomationCategory,
  AutomationDef,
  AutomationParam,
  AutomationRun,
} from '@/types';
import { cn, formatDateTime, formatRelative } from '@/lib/utils';

const CATEGORY_META: Record<AutomationCategory, { icon: LucideIcon; tone: 'brand' | 'ok' | 'warn' | 'info' | 'neutral' }> = {
  data: { icon: Database, tone: 'brand' },
  outreach: { icon: Mail, tone: 'info' },
  voice: { icon: Zap, tone: 'ok' },
  hygiene: { icon: ShieldAlert, tone: 'warn' },
  reporting: { icon: Activity, tone: 'neutral' },
};

type ParamValues = Record<string, string | number | boolean>;

function defaultParams(def: AutomationDef): ParamValues {
  const out: ParamValues = {};
  def.params.forEach((p) => {
    out[p.name] = p.defaultValue;
  });
  return out;
}

function ParamControl({
  param,
  value,
  onChange,
  disabled,
}: {
  param: AutomationParam;
  value: string | number | boolean;
  onChange: (next: string | number | boolean) => void;
  disabled?: boolean;
}) {
  const id = `param-${param.name}`;
  if (param.type === 'boolean') {
    return (
      <div className="flex items-center justify-between gap-3 rounded-lg border border-line bg-elevated px-3 py-2">
        <span className="text-sm text-ink">{param.label}</span>
        <Switch checked={Boolean(value)} onChange={onChange} label={param.label} disabled={disabled} />
      </div>
    );
  }

  return (
    <Field label={param.label} htmlFor={id} hint={param.help}>
      {param.type === 'select' ? (
        <Select
          id={id}
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        >
          {param.options?.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      ) : param.type === 'number' ? (
        <Input
          id={id}
          type="number"
          min={param.min}
          max={param.max}
          value={Number(value)}
          onChange={(e) => onChange(Number(e.target.value))}
          disabled={disabled}
        />
      ) : (
        <Input
          id={id}
          type="text"
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        />
      )}
    </Field>
  );
}

function RunStatusBadge({ run }: { run: AutomationRun | null }) {
  if (!run) return <Badge tone="neutral">never run</Badge>;
  const tone = run.status === 'success' ? 'ok' : run.status === 'failed' ? 'danger' : 'info';
  return (
    <Badge tone={tone} dot>
      {run.status} · {formatRelative(run.startedAt)}
    </Badge>
  );
}

export default function Automations() {
  const toast = useToast();

  const fetchDefs = useCallback(() => api.automations.list(), []);
  const {
    data: defs,
    loading,
    error,
    reload,
    setData: setDefs,
  } = useAsync<AutomationDef[]>(fetchDefs, []);

  const { data: runs, loading: runsLoading, reload: reloadRuns } = useAsync<AutomationRun[]>(
    () => api.automations.runs(25),
    [],
  );

  const [params, setParams] = useState<Record<string, ParamValues>>({});
  const [running, setRunning] = useState<Record<string, boolean>>({});
  const [detailOpen, setDetailOpen] = useState<string | null>(null);
  const [runAllOpen, setRunAllOpen] = useState(false);
  const [runAllBusy, setRunAllBusy] = useState(false);

  const paramValuesFor = useCallback(
    (def: AutomationDef): ParamValues => params[def.id] ?? defaultParams(def),
    [params],
  );

  const enabledCount = useMemo(() => defs?.filter((d) => d.enabled).length ?? 0, [defs]);

  function setParam(automationId: string, name: string, value: string | number | boolean) {
    setParams((prev) => ({
      ...prev,
      [automationId]: { ...(prev[automationId] ?? {}), [name]: value },
    }));
  }

  async function toggleEnabled(def: AutomationDef, next: boolean) {
    try {
      const updated = await api.automations.setEnabled(def.id, next);
      setDefs((defs ?? []).map((d) => (d.id === updated.id ? { ...d, ...updated } : d)));
      toast.success(
        next ? `${def.name} enabled` : `${def.name} paused`,
        next ? 'It will continue running on schedule.' : 'Scheduled runs are paused; manual runs still work.',
      );
    } catch (err) {
      toast.error('Could not update schedule', err instanceof Error ? err.message : 'Unknown error.');
    }
  }

  async function runOne(def: AutomationDef, dryRun = false) {
    setRunning((prev) => ({ ...prev, [def.id]: true }));
    try {
      const run = await api.automations.trigger(def.id, paramValuesFor(def), { dryRun });
      toast.success(dryRun ? `${def.name} · dry run` : `${def.name} complete`, run.message);
      reload();
      reloadRuns();
    } catch (err) {
      toast.error(
        `${def.name} failed`,
        err instanceof Error ? err.message : 'Unknown error.',
      );
      reload();
      reloadRuns();
    } finally {
      setRunning((prev) => ({ ...prev, [def.id]: false }));
    }
  }

  async function runAll() {
    if (!defs) return;
    setRunAllBusy(true);
    setRunAllOpen(false);
    const targets = defs.filter((d) => d.enabled);
    let ok = 0;
    let failed = 0;
    for (const def of targets) {
      setRunning((prev) => ({ ...prev, [def.id]: true }));
      try {
        const run = await api.automations.trigger(def.id, paramValuesFor(def));
        toast.success(`${def.name} complete`, run.message);
        ok += 1;
      } catch (err) {
        toast.error(`${def.name} failed`, err instanceof Error ? err.message : 'Unknown error.');
        failed += 1;
      } finally {
        setRunning((prev) => ({ ...prev, [def.id]: false }));
      }
    }
    toast.info('Batch finished', `${ok} succeeded, ${failed} failed.`);
    reload();
    reloadRuns();
    setRunAllBusy(false);
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Automation center"
        description="Every scheduled workflow below can also be fired by hand. Nothing runs silently."
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                reload();
                reloadRuns();
              }}
              leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
            >
              <span className="hidden sm:inline">Refresh</span>
            </Button>
            <Button
              onClick={() => setRunAllOpen(true)}
              loading={runAllBusy}
              disabled={!defs || enabledCount === 0}
              leftIcon={<Play className="h-4 w-4" />}
            >
              Run all enabled ({enabledCount})
            </Button>
          </>
        }
      />

      {error ? (
        <Card>
          <ErrorState
            title="Could not load automations"
            message={error}
            onRetry={reload}
            retrying={loading}
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
            {loading || !defs
              ? Array.from({ length: 6 }).map((_, i) => (
                  <Card key={i} className="p-5">
                    <Skeleton className="h-4 w-40" />
                    <Skeleton className="mt-3 h-3 w-full" />
                    <Skeleton className="mt-2 h-3 w-2/3" />
                    <Skeleton className="mt-5 h-9 w-full rounded-lg" />
                  </Card>
                ))
              : defs.map((def) => {
                  const Icon = CATEGORY_META[def.category].icon;
                  const busy = running[def.id] ?? false;
                  const expanded = detailOpen === def.id;
                  const values = paramValuesFor(def);
                  return (
                    <Card key={def.id} className={cn('flex flex-col', !def.enabled && 'opacity-75')}>
                      <div className="flex items-start gap-3 p-4 pb-3">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand/12 text-brand">
                          <Icon className="h-4 w-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="truncate text-sm font-semibold text-ink">{def.name}</h3>
                            <Badge tone={CATEGORY_META[def.category].tone} className="capitalize">
                              {def.category}
                            </Badge>
                            {def.destructive && (
                              <Badge tone="danger">
                                <AlertTriangle className="h-3 w-3" /> destructive
                              </Badge>
                            )}
                          </div>
                          <p className="mt-1 text-xs leading-relaxed text-muted">{def.summary}</p>
                        </div>
                        <Switch
                          checked={def.enabled}
                          onChange={(next) => toggleEnabled(def, next)}
                          label={`${def.enabled ? 'Pause' : 'Enable'} ${def.name}`}
                        />
                      </div>

                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-y border-line bg-elevated/40 px-4 py-2 text-[11px] text-faint">
                        <span className="inline-flex items-center gap-1.5">
                          <Clock className="h-3 w-3" /> {def.cron}
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                          <ListChecks className="h-3 w-3" /> last:{' '}
                          {def.lastRun ? `${def.lastRun.recordsProcessed} records` : 'n/a'}
                        </span>
                        <span className="ml-auto">
                          <RunStatusBadge run={def.lastRun} />
                        </span>
                      </div>

                      <div className="flex-1 px-4 py-3">
                        {def.lastRun?.message && (
                          <p className="text-xs text-muted">{def.lastRun.message}</p>
                        )}
                        {def.lastRun?.status === 'failed' && def.lastRun.error && (
                          <p className="mt-1 text-xs text-danger">{def.lastRun.error}</p>
                        )}

                        {expanded && (
                          <div className="mt-3 space-y-3 border-t border-line pt-3">
                            <p className="text-xs leading-relaxed text-muted">{def.detail}</p>
                            {def.params.length > 0 && (
                              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                {def.params.map((p) => (
                                  <ParamControl
                                    key={p.name}
                                    param={p}
                                    value={values[p.name] ?? p.defaultValue}
                                    onChange={(v) => setParam(def.id, p.name, v)}
                                    disabled={busy}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3">
                        <Button
                          size="sm"
                          onClick={() => runOne(def)}
                          loading={busy}
                          disabled={busy}
                          leftIcon={<Play className="h-3.5 w-3.5" />}
                        >
                          Run now
                        </Button>
                        {def.destructive && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => runOne(def, true)}
                            loading={busy}
                            disabled={busy}
                            leftIcon={<FlaskConical className="h-3.5 w-3.5" />}
                          >
                            Dry run
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="ml-auto"
                          onClick={() => setDetailOpen(expanded ? null : def.id)}
                          leftIcon={<Eye className="h-3.5 w-3.5" />}
                        >
                          {expanded ? 'Hide' : 'Configure'}
                        </Button>
                      </div>
                    </Card>
                  );
                })}
          </div>

          {/* Run history */}
          <Card>
            <CardHeader
              title="Run history"
              subtitle="Manual and scheduled executions, newest first"
              actions={<Badge tone="brand">{runs?.length ?? 0} entries</Badge>}
            />
            {runsLoading ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full" />
                ))}
              </div>
            ) : !runs || runs.length === 0 ? (
              <EmptyState
                icon={<Zap className="h-5 w-5" />}
                title="No runs recorded yet"
                description="Trigger any workflow above and its execution will be logged here."
              />
            ) : (
              <ul className="divide-y divide-line">
                {runs.map((run) => (
                  <li key={run.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2.5">
                    {run.status === 'success' ? (
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" />
                    ) : run.status === 'failed' ? (
                      <AlertTriangle className="h-4 w-4 shrink-0 text-danger" />
                    ) : (
                      <Clock className="h-4 w-4 shrink-0 text-info" />
                    )}

                    <span className="min-w-0 flex-1 truncate text-sm text-ink">
                      {run.automationName}
                      {run.error && <span className="text-danger"> — {run.error}</span>}
                      {!run.error && run.message && (
                        <span className="text-faint"> — {run.message}</span>
                      )}
                    </span>

                    <Badge tone="neutral">{run.triggeredBy}</Badge>
                    <span className="hidden text-xs tabular-nums text-faint sm:inline">
                      {run.recordsProcessed} rec
                    </span>
                    <span className="hidden text-xs text-faint md:inline">
                      {formatDateTime(run.startedAt)}
                    </span>
                    <Badge
                      tone={run.status === 'success' ? 'ok' : run.status === 'failed' ? 'danger' : 'info'}
                      className="capitalize"
                    >
                      {run.status}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}

      <ConfirmDialog
        open={runAllOpen}
        onClose={() => setRunAllOpen(false)}
        onConfirm={runAll}
        title="Run all enabled automations?"
        description={`This will execute ${enabledCount} workflow${enabledCount === 1 ? '' : 's'} sequentially using the parameters shown in each card. Actions mutate the live dataset.`}
        confirmLabel={`Run ${enabledCount}`}
      />
    </div>
  );
}
