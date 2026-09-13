import { useCallback, useMemo, useState } from 'react';
import { ExternalLink, MessagesSquare, RefreshCw, Send } from 'lucide-react';
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
  Skeleton,
} from '@/components/ui/primitives';
import type { TelegramApplyResult, TelegramGroup } from '@/types';
import { cn, formatRelative } from '@/lib/utils';

const PRODUCT_LABEL: Record<TelegramGroup['product'], string> = {
  marketing: 'Marketing',
  voice: 'Voice',
  cross: 'Cross-product',
};

const PRODUCT_TONE: Record<TelegramGroup['product'], 'brand' | 'info' | 'warn'> = {
  marketing: 'brand',
  voice: 'info',
  cross: 'warn',
};

const PRODUCT_ORDER: TelegramGroup['product'][] = ['marketing', 'voice', 'cross'];

function GroupCard({
  group,
  onSaved,
  onApply,
  applying,
}: {
  group: TelegramGroup;
  onSaved: () => void;
  onApply: () => void;
  applying: boolean;
}) {
  const toast = useToast();
  const [chatId, setChatId] = useState(group.chatId ?? '');
  const [inviteLink, setInviteLink] = useState(group.inviteLink ?? '');
  const [saving, setSaving] = useState(false);

  const ready = Boolean(group.chatId);

  async function handleSave() {
    setSaving(true);
    try {
      await api.telegram.update(group.id, {
        chatId: chatId.trim() || null,
        inviteLink: inviteLink.trim() || null,
      });
      toast.success('Saved', `${group.name}: chat id / invite link updated.`);
      onSaved();
    } catch (err) {
      toast.error('Could not save', err instanceof Error ? err.message : 'Unknown error.');
    } finally {
      setSaving(false);
    }
  }

  const inviteUrl =
    group.inviteLink ?? (group.handle && group.access === 'public' ? `https://t.me/${group.handle}` : null);

  return (
    <Card className={cn('flex flex-col', !ready && 'ring-1 ring-warn/20')}>
      <div className="flex flex-wrap items-center gap-2 p-4 pb-2">
        <Badge tone={PRODUCT_TONE[group.product]}>{PRODUCT_LABEL[group.product]}</Badge>
        <Badge tone={group.access === 'public' ? 'ok' : 'warn'}>{group.access}</Badge>
        <Badge tone="neutral" className="capitalize">
          {group.kind}
        </Badge>
        <span className="ml-auto">
          <Badge tone={ready ? 'ok' : 'warn'} dot>
            {ready ? 'ready' : 'needs chat_id'}
          </Badge>
        </span>
      </div>

      <div className="px-4">
        <h3 className="text-sm font-semibold text-ink">{group.name}</h3>
        <p className="mt-1 text-xs leading-relaxed text-muted">{group.purpose}</p>
        <p className="mt-2 text-[11px] text-faint">
          <span className="font-medium text-muted">Audience:</span> {group.audience}
        </p>
        {inviteUrl && (
          <a
            href={inviteUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-brand hover:underline"
          >
            <ExternalLink className="h-3 w-3" /> {inviteUrl}
          </a>
        )}
      </div>

      <div className="mt-auto space-y-2 border-t border-line px-4 py-3">
        <Field label="chat_id" htmlFor={`chat-${group.id}`} hint="Paste after manually creating the chat">
          <Input
            id={`chat-${group.id}`}
            value={chatId}
            onChange={(e) => setChatId(e.target.value)}
            placeholder="e.g. -1001234567890"
            disabled={saving}
          />
        </Field>
        <Field label="invite_link" htmlFor={`inv-${group.id}`}>
          <Input
            id={`inv-${group.id}`}
            value={inviteLink}
            onChange={(e) => setInviteLink(e.target.value)}
            placeholder="https://t.me/+..."
            disabled={saving}
          />
        </Field>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" onClick={handleSave} loading={saving}>
            Save
          </Button>
          <Button size="sm" onClick={onApply} loading={applying} disabled={applying} leftIcon={<Send className="h-3.5 w-3.5" />}>
            Apply
          </Button>
        </div>
      </div>
    </Card>
  );
}

export default function TelegramSetup() {
  const toast = useToast();
  const fetchGroups = useCallback(() => api.telegram.list(), []);
  const { data: groups, loading, error, reload } = useAsync<TelegramGroup[]>(fetchGroups, []);
  const [applying, setApplying] = useState(false);
  const [lastAppliedAt, setLastAppliedAt] = useState<string | null>(null);

  const byProduct = useMemo(() => {
    const map: Record<TelegramGroup['product'], TelegramGroup[]> = { marketing: [], voice: [], cross: [] };
    (groups ?? []).forEach((g) => map[g.product].push(g));
    return map;
  }, [groups]);

  const readyCount = useMemo(() => (groups ?? []).filter((g) => g.chatId).length, [groups]);

  async function handleApply() {
    setApplying(true);
    try {
      const res: TelegramApplyResult = await api.telegram.apply();
      setLastAppliedAt(new Date().toISOString());
      toast.info('Apply (mock)', res.note);
    } catch (err) {
      toast.error('Apply failed', err instanceof Error ? err.message : 'Unknown error.');
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Telegram setup"
        description="Enterprise groups & channels for both products. Bot API cannot create chats — create manually, paste chat_id, then Apply."
        actions={
          <Button
            variant="secondary"
            onClick={reload}
            leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
          >
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        }
      />

      {error ? (
        <Card>
          <ErrorState
            title="Could not load Telegram setup"
            message={error}
            onRetry={reload}
            retrying={loading}
          />
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader
              title="Enterprise Telegram footprint"
              subtitle="Mirror of config/telegram/setup_spec.yaml — the canonical single source of truth."
              actions={
                <Badge tone="ok">
                  {readyCount}/{groups?.length ?? 0} ready
                </Badge>
              }
            />
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-2.5 text-[11px] text-faint">
              <span>Opt-in only · DPDP 2023 · TRAI 09:00–21:00 · AI-disclosure · no cold outreach.</span>
              {lastAppliedAt && (
                <span className="ml-auto">
                  <Badge tone="info">Apply attempted {formatRelative(lastAppliedAt)}</Badge>
                </span>
              )}
            </div>
          </Card>

          {loading || !groups ? (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Card key={i} className="p-5">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="mt-3 h-3 w-full" />
                  <Skeleton className="mt-2 h-3 w-2/3" />
                  <Skeleton className="mt-5 h-9 w-full rounded-lg" />
                </Card>
              ))}
            </div>
          ) : groups.length === 0 ? (
            <Card>
              <EmptyState
                icon={<MessagesSquare className="h-5 w-5" />}
                title="No Telegram entities"
                description="The setup spec defines no groups yet."
              />
            </Card>
          ) : (
            PRODUCT_ORDER.map((prod) => {
              const items = byProduct[prod];
              if (items.length === 0) return null;
              return (
                <section key={prod} className="space-y-3">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-faint">
                    {PRODUCT_LABEL[prod]}
                  </h2>
                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
                    {items.map((g) => (
                      <GroupCard key={g.id} group={g} onSaved={reload} onApply={handleApply} applying={applying} />
                    ))}
                  </div>
                </section>
              );
            })
          )}
        </>
      )}
    </div>
  );
}
