import { useCallback, useMemo, useState } from 'react';
import { Download, Pencil, Phone, Plus, Sparkles, Trash2, Users, X } from 'lucide-react';
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
  Select,
} from '@/components/ui/primitives';
import { DataTable } from '@/components/ui/DataTable';
import type { Column } from '@/components/ui/DataTable';
import { Pagination, SearchInput } from '@/components/ui/Pagination';
import { ConfirmDialog } from '@/components/ui/Modal';
import { LeadFormModal, type FormValues } from '@/components/leads/LeadForm';
import type { Lead, LeadStatus, LeadTemperature, Niche, Page, SortDirection } from '@/types';
import { cn, downloadCsv, formatPhone, formatRelative, titleCase } from '@/lib/utils';

const STATUS_TONE: Record<LeadStatus, 'neutral' | 'brand' | 'ok' | 'warn' | 'danger' | 'info'> = {
  new: 'info',
  enriched: 'brand',
  contacted: 'neutral',
  qualified: 'ok',
  nurturing: 'warn',
  converted: 'ok',
  disqualified: 'danger',
};

const TEMP_TONE: Record<LeadTemperature, 'danger' | 'warn' | 'info'> = {
  hot: 'danger',
  warm: 'warn',
  cold: 'info',
};

const NICHES: Niche[] = [
  'salon',
  'clinic',
  'gym',
  'real_estate',
  'coaching',
  'restaurant',
  'boutique',
  'automobile',
];

export default function Leads() {
  const toast = useToast();

  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [niche, setNiche] = useState('');
  const [temperature, setTemperature] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [sort, setSort] = useState('updatedAt');
  const [dir, setDir] = useState<SortDirection>('desc');
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Lead | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Lead | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [enriching, setEnriching] = useState(false);

  const fetchLeads = useCallback(
    () =>
      api.leads.list({
        q,
        status,
        niche,
        temperature,
        page,
        pageSize,
        sort,
        dir,
      }),
    [q, status, niche, temperature, page, pageSize, sort, dir],
  );

  const { data, loading, error, reload } = useAsync<Page<Lead>>(fetchLeads, [
    q,
    status,
    niche,
    temperature,
    page,
    pageSize,
    sort,
    dir,
  ]);

  const rows = data?.items ?? [];
  const total = data?.total ?? 0;

  function handleSort(key: string) {
    if (sort === key) {
      setDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSort(key);
      setDir(key === 'name' || key === 'businessName' || key === 'city' ? 'asc' : 'desc');
    }
    setPage(1);
  }

  const resetPage = <T,>(setter: (v: T) => void) => (value: T) => {
    setter(value);
    setPage(1);
  };

  function toggleRow(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll(checked: boolean) {
    setSelected(checked ? new Set(rows.map((r) => r.id)) : new Set());
  }

  async function handleSubmit(values: FormValues) {
    setSubmitting(true);
    try {
      if (editing) {
        await api.leads.update(editing.id, values);
        toast.success('Lead updated', `${values.name} was saved.`);
      } else {
        const created = await api.leads.create(values);
        toast.success('Lead created', `${created.id} · ${created.name} added to the pipeline.`);
      }
      setFormOpen(false);
      setEditing(null);
      reload();
    } catch (err) {
      toast.error(
        editing ? 'Update failed' : 'Create failed',
        err instanceof Error ? err.message : 'Unknown error.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.leads.remove(deleteTarget.id);
      toast.success('Lead deleted', `${deleteTarget.id} was removed.`);
      setDeleteTarget(null);
      reload();
    } catch (err) {
      toast.error('Delete failed', err instanceof Error ? err.message : 'Unknown error.');
    } finally {
      setDeleting(false);
    }
  }

  async function confirmBulkDelete() {
    setBulkDeleting(true);
    const count = selected.size;
    try {
      const removed = await api.leads.removeMany([...selected]);
      toast.success('Leads deleted', `${removed} record${removed === 1 ? '' : 's'} removed.`);
      setSelected(new Set());
      setBulkDeleteOpen(false);
      reload();
    } catch (err) {
      toast.error('Bulk delete failed', err instanceof Error ? err.message : `${count} records.`);
    } finally {
      setBulkDeleting(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      const all = await api.leads.exportAll({ q, status, niche, temperature });
      downloadCsv(
        `leads-${new Date().toISOString().slice(0, 10)}.csv`,
        all as unknown as Record<string, unknown>[],
      );
      toast.success('Export ready', `${all.length} leads downloaded as CSV.`);
    } catch (err) {
      toast.error('Export failed', err instanceof Error ? err.message : 'Unknown error.');
    } finally {
      setExporting(false);
    }
  }

  async function handleEnrich() {
    setEnriching(true);
    try {
      const run = await api.automations.trigger('enrich_leads', { limit: 50 });
      toast.success('Enrichment complete', run.message);
      reload();
    } catch (err) {
      toast.error('Enrichment failed', err instanceof Error ? err.message : 'Unknown error.');
    } finally {
      setEnriching(false);
    }
  }

  const columns = useMemo<Column<Lead>[]>(
    () => [
      {
        key: 'name',
        header: 'Lead',
        sortable: true,
        render: (row) => (
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-ink">{row.name}</p>
            <p className="truncate text-xs text-faint">{row.businessName}</p>
          </div>
        ),
      },
      {
        key: 'phone',
        header: 'Phone',
        hideBelow: 'lg',
        render: (row) => (
          <span className="whitespace-nowrap font-mono text-xs text-muted">
            {formatPhone(row.phone)}
          </span>
        ),
      },
      {
        key: 'city',
        header: 'Location',
        sortable: true,
        hideBelow: 'lg',
        render: (row) => (
          <span className="whitespace-nowrap text-sm text-muted">
            {row.city}
            <span className="text-faint"> · {row.state}</span>
          </span>
        ),
      },
      {
        key: 'niche',
        header: 'Niche',
        sortable: true,
        hideBelow: 'md',
        render: (row) => <span className="text-sm text-muted">{titleCase(row.niche)}</span>,
      },
      {
        key: 'status',
        header: 'Status',
        sortable: true,
        render: (row) => (
          <Badge tone={STATUS_TONE[row.status]} dot>
            {titleCase(row.status)}
          </Badge>
        ),
      },
      {
        key: 'score',
        header: 'Score',
        sortable: true,
        align: 'right',
        render: (row) => (
          <div className="flex items-center justify-end gap-2">
            <span className="w-6 text-right text-sm font-semibold tabular-nums text-ink">
              {row.score}
            </span>
            <div className="hidden h-1.5 w-14 overflow-hidden rounded-full bg-elevated sm:block">
              <div
                className={cn(
                  'h-full rounded-full',
                  row.temperature === 'hot'
                    ? 'bg-danger'
                    : row.temperature === 'warm'
                      ? 'bg-warn'
                      : 'bg-info',
                )}
                style={{ width: `${row.score}%` }}
              />
            </div>
          </div>
        ),
      },
      {
        key: 'temperature',
        header: 'Temp',
        sortable: true,
        hideBelow: 'md',
        render: (row) => (
          <Badge tone={TEMP_TONE[row.temperature]} className="capitalize">
            {row.temperature}
          </Badge>
        ),
      },
      {
        key: 'lastContactedAt',
        header: 'Last contact',
        sortable: true,
        hideBelow: 'xl',
        render: (row) => (
          <span className="whitespace-nowrap text-xs text-muted">
            {formatRelative(row.lastContactedAt)}
          </span>
        ),
      },
      {
        key: 'actions',
        header: '',
        align: 'right',
        width: '96px',
        render: (row) => (
          <div className="flex items-center justify-end gap-1">
            <button
              type="button"
              aria-label={`Edit ${row.name}`}
              title="Edit"
              onClick={(e) => {
                e.stopPropagation();
                setEditing(row);
                setFormOpen(true);
              }}
              className="rounded-md p-1.5 text-faint transition-colors hover:bg-elevated hover:text-ink"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              aria-label={`Delete ${row.name}`}
              title="Delete"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget(row);
              }}
              className="rounded-md p-1.5 text-faint transition-colors hover:bg-danger/10 hover:text-danger"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
            <a
              href={`tel:+91${row.phone}`}
              aria-label={`Call ${row.name}`}
              title="Call"
              onClick={(e) => e.stopPropagation()}
              className="rounded-md p-1.5 text-faint transition-colors hover:bg-elevated hover:text-ok"
            >
              <Phone className="h-3.5 w-3.5" />
            </a>
          </div>
        ),
      },
    ],
    [],
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Leads"
        description="Every prospect captured from maps, audits, SEO pages and referrals."
        actions={
          <>
            <Button
              variant="secondary"
              onClick={handleEnrich}
              loading={enriching}
              leftIcon={<Sparkles className="h-3.5 w-3.5" />}
            >
              <span className="hidden sm:inline">Enrich new</span>
            </Button>
            <Button
              variant="secondary"
              onClick={handleExport}
              loading={exporting}
              leftIcon={<Download className="h-3.5 w-3.5" />}
            >
              <span className="hidden sm:inline">Export</span>
            </Button>
            <Button
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
              leftIcon={<Plus className="h-4 w-4" />}
            >
              Add lead
            </Button>
          </>
        }
      />

      <Card>
        <CardHeader
          title="Pipeline"
          subtitle={
            total > 0
              ? `${total.toLocaleString('en-IN')} lead${total === 1 ? '' : 's'} match your filters`
              : undefined
          }
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput
                value={q}
                onChange={resetPage(setQ)}
                placeholder="Search name, phone, city…"
                className="w-full sm:w-64"
              />
              <Select
                value={status}
                onChange={(e) => resetPage(setStatus)(e.target.value)}
                aria-label="Filter by status"
                className="w-[132px]"
              >
                <option value="">All statuses</option>
                {(['new', 'enriched', 'contacted', 'qualified', 'nurturing', 'converted', 'disqualified'] as LeadStatus[]).map(
                  (s) => (
                    <option key={s} value={s}>
                      {titleCase(s)}
                    </option>
                  ),
                )}
              </Select>
              <Select
                value={niche}
                onChange={(e) => resetPage(setNiche)(e.target.value)}
                aria-label="Filter by niche"
                className="w-[128px]"
              >
                <option value="">All niches</option>
                {NICHES.map((n) => (
                  <option key={n} value={n}>
                    {titleCase(n)}
                  </option>
                ))}
              </Select>
              <Select
                value={temperature}
                onChange={(e) => resetPage(setTemperature)(e.target.value)}
                aria-label="Filter by temperature"
                className="w-[112px]"
              >
                <option value="">Any temp</option>
                <option value="hot">Hot</option>
                <option value="warm">Warm</option>
                <option value="cold">Cold</option>
              </Select>
            </div>
          }
        />

        {selected.size > 0 && (
          <div className="flex flex-wrap items-center gap-3 border-b border-brand/25 bg-brand/[0.07] px-4 py-2.5">
            <span className="text-xs font-medium text-brand-ink">
              {selected.size} selected
            </span>
            <Button
              size="sm"
              variant="danger"
              onClick={() => setBulkDeleteOpen(true)}
              leftIcon={<Trash2 className="h-3.5 w-3.5" />}
            >
              Delete selected
            </Button>
            <button
              type="button"
              onClick={() => setSelected(new Set())}
              className="ml-auto inline-flex items-center gap-1 text-xs text-muted hover:text-ink"
            >
              <X className="h-3 w-3" /> Clear
            </button>
          </div>
        )}

        {error ? (
          <ErrorState
            title="Could not load leads"
            message={error}
            onRetry={reload}
            retrying={loading}
          />
        ) : (
          <>
            <DataTable
              columns={columns}
              rows={rows}
              rowKey={(r) => r.id}
              sort={sort}
              dir={dir}
              onSortChange={handleSort}
              loadingRows={loading ? pageSize : 0}
              selected={selected}
              onToggleRow={toggleRow}
              onToggleAll={toggleAll}
              onRowClick={(row) => {
                setEditing(row);
                setFormOpen(true);
              }}
              empty={
                <EmptyState
                  icon={<Users className="h-5 w-5" />}
                  title="No leads match your filters"
                  description="Try clearing the search box or widening the status and niche filters."
                  action={
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setQ('');
                        setStatus('');
                        setNiche('');
                        setTemperature('');
                        setPage(1);
                      }}
                    >
                      Clear filters
                    </Button>
                  }
                />
              }
            />

            {rows.length > 0 && (
              <Pagination
                page={page}
                pageSize={pageSize}
                total={total}
                onPageChange={setPage}
                onPageSizeChange={(n) => {
                  setPageSize(n);
                  setPage(1);
                }}
              />
            )}
          </>
        )}
      </Card>

      <LeadFormModal
        open={formOpen}
        onClose={() => {
          setFormOpen(false);
          setEditing(null);
        }}
        onSubmit={handleSubmit}
        initial={editing}
        submitting={submitting}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
        destructive
        loading={deleting}
        title="Delete this lead?"
        description={`${deleteTarget?.name} (${deleteTarget?.id}) will be permanently removed. This cannot be undone.`}
        confirmLabel="Delete lead"
      />

      <ConfirmDialog
        open={bulkDeleteOpen}
        onClose={() => setBulkDeleteOpen(false)}
        onConfirm={confirmBulkDelete}
        destructive
        loading={bulkDeleting}
        title={`Delete ${selected.size} leads?`}
        description="All selected records will be permanently removed. This cannot be undone."
        confirmLabel={`Delete ${selected.size}`}
      />
    </div>
  );
}
