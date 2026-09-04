import { useCallback, useMemo, useState } from 'react';
import { FileText, PhoneCall, RefreshCw, RotateCcw } from 'lucide-react';
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
import { Modal } from '@/components/ui/Modal';
import type { CallOutcome, CallRecord, CallSentiment, Page, SortDirection } from '@/types';
import { formatDateTime, formatDuration, inr, titleCase } from '@/lib/utils';

const OUTCOME_TONE: Record<CallOutcome, 'neutral' | 'brand' | 'ok' | 'warn' | 'danger' | 'info'> = {
  connected: 'ok',
  scheduled: 'brand',
  no_answer: 'warn',
  busy: 'warn',
  voicemail: 'info',
  failed: 'danger',
};

const SENTIMENT_TONE: Record<CallSentiment, 'ok' | 'warn' | 'danger' | 'neutral'> = {
  positive: 'ok',
  neutral: 'neutral',
  negative: 'danger',
};

export default function Calls() {
  const toast = useToast();

  const [q, setQ] = useState('');
  const [outcome, setOutcome] = useState('');
  const [intent, setIntent] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [sort, setSort] = useState('startedAt');
  const [dir, setDir] = useState<SortDirection>('desc');

  const [detail, setDetail] = useState<CallRecord | null>(null);
  const [transcribing, setTranscribing] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const fetchCalls = useCallback(
    () => api.calls.list({ q, outcome, intent, page, pageSize, sort, dir }),
    [q, outcome, intent, page, pageSize, sort, dir],
  );

  const { data, loading, error, reload } = useAsync<Page<CallRecord>>(fetchCalls, [
    q,
    outcome,
    intent,
    page,
    pageSize,
    sort,
    dir,
  ]);

  const rows = data?.items ?? [];
  const total = data?.total ?? 0;

  function handleSort(key: string) {
    if (sort === key) setDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSort(key);
      setDir(key === 'startedAt' || key === 'durationSec' || key === 'costInr' ? 'desc' : 'asc');
    }
    setPage(1);
  }

  async function runTranscribe() {
    setTranscribing(true);
    try {
      const run = await api.automations.trigger('transcribe_backlog', { limit: 40 });
      toast.success('Transcription complete', run.message);
      reload();
    } catch (err) {
      toast.error('Transcription failed', err instanceof Error ? err.message : 'Unknown error.');
    } finally {
      setTranscribing(false);
    }
  }

  async function runRetry() {
    setRetrying(true);
    try {
      const run = await api.automations.trigger('retry_no_answer', { maxAttempts: 3, backoffHours: 6 });
      toast.success('Retry batch complete', run.message);
      reload();
    } catch (err) {
      toast.error('Retry batch failed', err instanceof Error ? err.message : 'Unknown error.');
    } finally {
      setRetrying(false);
    }
  }

  const columns = useMemo<Column<CallRecord>[]>(
    () => [
      {
        key: 'id',
        header: 'Call ID',
        sortable: true,
        hideBelow: 'lg',
        render: (row) => <span className="font-mono text-xs text-faint">{row.id}</span>,
      },
      {
        key: 'leadName',
        header: 'Lead',
        sortable: true,
        render: (row) => (
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-ink">{row.leadName}</p>
            <p className="truncate text-xs text-faint">{row.businessName}</p>
          </div>
        ),
      },
      {
        key: 'direction',
        header: 'Direction',
        sortable: true,
        hideBelow: 'md',
        render: (row) => (
          <Badge tone={row.direction === 'outbound' ? 'brand' : 'info'} className="capitalize">
            {row.direction}
          </Badge>
        ),
      },
      {
        key: 'outcome',
        header: 'Outcome',
        sortable: true,
        render: (row) => (
          <Badge tone={OUTCOME_TONE[row.outcome]} dot>
            {titleCase(row.outcome)}
          </Badge>
        ),
      },
      {
        key: 'intent',
        header: 'Intent',
        sortable: true,
        hideBelow: 'lg',
        render: (row) => (
          <span className="text-sm text-muted">{titleCase(row.intent)}</span>
        ),
      },
      {
        key: 'sentiment',
        header: 'Sentiment',
        sortable: true,
        hideBelow: 'xl',
        render: (row) => (
          <Badge tone={SENTIMENT_TONE[row.sentiment]} className="capitalize">
            {row.sentiment}
          </Badge>
        ),
      },
      {
        key: 'durationSec',
        header: 'Duration',
        sortable: true,
        align: 'right',
        render: (row) => (
          <span className="whitespace-nowrap text-sm tabular-nums text-muted">
            {formatDuration(row.durationSec)}
          </span>
        ),
      },
      {
        key: 'costInr',
        header: 'Cost',
        sortable: true,
        align: 'right',
        hideBelow: 'lg',
        render: (row) => (
          <span className="whitespace-nowrap text-sm tabular-nums text-muted">
            {row.costInr > 0 ? inr.format(row.costInr) : '—'}
          </span>
        ),
      },
      {
        key: 'startedAt',
        header: 'Started',
        sortable: true,
        hideBelow: 'sm',
        render: (row) => (
          <span className="whitespace-nowrap text-xs text-muted">
            {formatDateTime(row.startedAt)}
          </span>
        ),
      },
      {
        key: 'transcript',
        header: '',
        align: 'right',
        width: '64px',
        render: (row) => (
          <Button
            variant="ghost"
            size="sm"
            disabled={!row.transcript}
            onClick={(e) => {
              e.stopPropagation();
              setDetail(row);
            }}
            leftIcon={<FileText className="h-3.5 w-3.5" />}
          >
            <span className="sr-only">View transcript</span>
          </Button>
        ),
      },
    ],
    [],
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Call log"
        description="Every AI voice call with outcome, intent, duration and transcript."
        actions={
          <>
            <Button
              variant="secondary"
              onClick={runTranscribe}
              loading={transcribing}
              leftIcon={<FileText className="h-3.5 w-3.5" />}
            >
              <span className="hidden sm:inline">Transcribe backlog</span>
            </Button>
            <Button
              variant="secondary"
              onClick={runRetry}
              loading={retrying}
              leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
            >
              <span className="hidden sm:inline">Retry no-answer</span>
            </Button>
            <Button
              variant="secondary"
              onClick={reload}
              leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
            >
              <span className="hidden sm:inline">Refresh</span>
            </Button>
          </>
        }
      />

      <Card>
        <CardHeader
          title="Voice activity"
          subtitle={
            total > 0 ? `${total.toLocaleString('en-IN')} recorded call${total === 1 ? '' : 's'}` : undefined
          }
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput
                value={q}
                onChange={(v) => {
                  setQ(v);
                  setPage(1);
                }}
                placeholder="Search lead, outcome, transcript…"
                className="w-full sm:w-64"
              />
              <Select
                value={outcome}
                onChange={(e) => {
                  setOutcome(e.target.value);
                  setPage(1);
                }}
                aria-label="Filter by outcome"
                className="w-[136px]"
              >
                <option value="">All outcomes</option>
                {(['connected', 'scheduled', 'no_answer', 'busy', 'voicemail', 'failed'] as CallOutcome[]).map(
                  (o) => (
                    <option key={o} value={o}>
                      {titleCase(o)}
                    </option>
                  ),
                )}
              </Select>
              <Select
                value={intent}
                onChange={(e) => {
                  setIntent(e.target.value);
                  setPage(1);
                }}
                aria-label="Filter by intent"
                className="w-[132px]"
              >
                <option value="">All intents</option>
                {(['interested', 'callback', 'not_interested', 'wrong_number', 'unknown'] as const).map(
                  (i) => (
                    <option key={i} value={i}>
                      {titleCase(i)}
                    </option>
                  ),
                )}
              </Select>
            </div>
          }
        />

        {error ? (
          <ErrorState title="Could not load calls" message={error} onRetry={reload} retrying={loading} />
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
              onRowClick={(row) => {
                if (row.transcript) setDetail(row);
              }}
              empty={
                <EmptyState
                  icon={<PhoneCall className="h-5 w-5" />}
                  title="No calls found"
                  description="No call records match the current search and filters."
                  action={
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setQ('');
                        setOutcome('');
                        setIntent('');
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

      <Modal
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        title={`Transcript · ${detail?.id ?? ''}`}
        description={
          detail ? `${detail.leadName} · ${detail.businessName} · ${formatDateTime(detail.startedAt)}` : undefined
        }
        size="md"
        footer={
          <Button variant="secondary" onClick={() => setDetail(null)}>
            Close
          </Button>
        }
      >
        {detail && (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge tone={OUTCOME_TONE[detail.outcome]} dot>
                {titleCase(detail.outcome)}
              </Badge>
              <Badge tone="neutral">Intent: {titleCase(detail.intent)}</Badge>
              <Badge tone={SENTIMENT_TONE[detail.sentiment]}>{detail.sentiment}</Badge>
              <Badge tone="neutral">Duration: {formatDuration(detail.durationSec)}</Badge>
              <Badge tone="neutral">Cost: {detail.costInr > 0 ? inr.format(detail.costInr) : '—'}</Badge>
            </div>

            <div className="rounded-lg border border-line bg-elevated p-3.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-faint">Transcript</p>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink">
                {detail.transcript || 'No transcript available for this call.'}
              </p>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
