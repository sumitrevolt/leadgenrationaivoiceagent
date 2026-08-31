import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bug,
  Database,
  LogOut,
  Moon,
  RotateCcw,
  Server,
  Sun,
} from 'lucide-react';
import { api } from '@/api/client';
import { useToast } from '@/components/ui/Toast';
import { PageHeader } from '@/components/layout/Topbar';
import { Badge, Button, Card, CardHeader, Field, Input } from '@/components/ui/primitives';
import { ConfirmDialog } from '@/components/ui/Modal';
import { useAuth } from '@/auth/AuthContext';
import { useTheme } from '@/lib/theme';
import { cn, formatDateTime } from '@/lib/utils';

export default function Settings() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const toast = useToast();
  const navigate = useNavigate();

  const [failurePct, setFailurePct] = useState(() => Math.round(api.getFailureRate() * 100));
  const [resetOpen, setResetOpen] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  function applyFailureRate(next: number) {
    setFailurePct(next);
    api.setFailureRate(next / 100);
    toast.info(
      'Failure injection updated',
      next === 0
        ? 'All requests will succeed normally.'
        : `${next}% of API calls will fail so you can exercise error and retry states.`,
    );
  }

  async function confirmReset() {
    setResetting(true);
    try {
      await api.resetData();
      toast.success('Demo data reset', 'Leads, calls and run history were regenerated.');
      setResetOpen(false);
    } catch (err) {
      toast.error('Reset failed', err instanceof Error ? err.message : 'Unknown error.');
    } finally {
      setResetting(false);
    }
  }

  async function handleLogout() {
    setSigningOut(true);
    try {
      await logout();
      navigate('/login', { replace: true });
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" description="Session, appearance and demo-environment controls." />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Appearance" subtitle="Theme is persisted per browser" />
          <div className="space-y-3 p-4">
            <p className="text-sm text-muted">Choose how the console looks.</p>
            <div className="grid grid-cols-2 gap-3">
              {(
                [
                  { key: 'dark', label: 'Dark', icon: Moon },
                  { key: 'light', label: 'Light', icon: Sun },
                ] as const
              ).map((option) => (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => theme !== option.key && toggle()}
                  className={cn(
                    'flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-colors',
                    theme === option.key
                      ? 'border-brand bg-brand/10 text-ink'
                      : 'border-line bg-elevated text-muted hover:border-brand/40 hover:text-ink',
                  )}
                  aria-pressed={theme === option.key}
                >
                  <option.icon className="h-4 w-4" />
                  <span className="text-sm font-medium">{option.label}</span>
                  {theme === option.key && (
                    <Badge tone="brand" className="ml-auto">
                      active
                    </Badge>
                  )}
                </button>
              ))}
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="Session" subtitle="Signed-in operator" />
          <div className="space-y-3 p-4">
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-full bg-brand/15 text-sm font-semibold text-brand-ink">
                {user?.initials ?? '??'}
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-ink">{user?.name}</p>
                <p className="truncate text-xs text-muted">{user?.email}</p>
              </div>
              <Badge tone="brand" className="ml-auto capitalize">
                {user?.role}
              </Badge>
            </div>

            <dl className="grid grid-cols-1 gap-2 rounded-lg border border-line bg-elevated p-3 text-xs sm:grid-cols-2">
              <div>
                <dt className="text-faint">User ID</dt>
                <dd className="font-mono text-ink">{user?.id ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-faint">Session</dt>
                <dd className="text-ink">8 hour expiry</dd>
              </div>
            </dl>

            <Field label="Last login" htmlFor="last-login">
              <Input id="last-login" value={formatDateTime(new Date().toISOString())} readOnly disabled />
            </Field>

            <Button
              variant="danger"
              onClick={handleLogout}
              loading={signingOut}
              leftIcon={<LogOut className="h-4 w-4" />}
            >
              Sign out
            </Button>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Diagnostics"
            subtitle="Exercise the loading, error and retry states"
          />
          <div className="space-y-3 p-4">
            <div className="flex items-start gap-2.5 rounded-lg border border-line bg-elevated p-3">
              <Bug className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
              <p className="text-xs leading-relaxed text-muted">
                Raise the failure rate to make a share of API calls fail on purpose. Reload any page
                to see the error state and its retry action.
              </p>
            </div>

            <Field
              label={`Injected failure rate — ${failurePct}%`}
              htmlFor="failure-rate"
              hint="Set back to 0% for normal operation."
            >
              <div className="flex items-center gap-3">
                <input
                  id="failure-rate"
                  type="range"
                  min={0}
                  max={60}
                  step={5}
                  value={failurePct}
                  onChange={(e) => applyFailureRate(Number(e.target.value))}
                  className="h-2 w-full cursor-pointer appearance-none rounded-full bg-elevated accent-[rgb(var(--brand))]"
                />
                <Badge tone={failurePct === 0 ? 'ok' : 'warn'}>{failurePct}%</Badge>
              </div>
            </Field>
          </div>
        </Card>

        <Card>
          <CardHeader title="Demo data" subtitle="Backed by an in-memory + localStorage store" />
          <div className="space-y-3 p-4">
            <div className="flex items-start gap-2.5 rounded-lg border border-line bg-elevated p-3">
              <Database className="mt-0.5 h-4 w-4 shrink-0 text-info" />
              <p className="text-xs leading-relaxed text-muted">
                Leads, calls and run history live in your browser. Resetting regenerates the seeded
                dataset — useful after destructive automations.
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => setResetOpen(true)}
              leftIcon={<RotateCcw className="h-4 w-4" />}
            >
              Reset demo dataset
            </Button>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="Backend integration" subtitle="Where to wire the real API" />
          <div className="space-y-3 p-4">
            <div className="flex items-start gap-2.5 rounded-lg border border-line bg-elevated p-3">
              <Server className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
              <p className="text-xs leading-relaxed text-muted">
                All UI code talks to the <code className="font-mono text-ink">ApiClient</code>{' '}
                interface in{' '}
                <code className="font-mono text-ink">src/api/client.ts</code>. Replace the single
                export at the bottom of that file with an HTTP implementation of the same interface —
                no page or component changes are required.
              </p>
            </div>
            <dl className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
              {[
                { label: 'Auth', value: 'POST /api/auth/login' },
                { label: 'Leads', value: 'GET/POST/PATCH/DELETE /api/leads' },
                { label: 'Calls', value: 'GET /api/calls' },
                { label: 'Metrics', value: 'GET /api/metrics/overview' },
                { label: 'Automations', value: 'GET /api/automations' },
                { label: 'Manual run', value: 'POST /api/automations/{id}/run' },
              ].map((row) => (
                <div key={row.label} className="rounded-lg border border-line bg-elevated px-3 py-2">
                  <dt className="text-faint">{row.label}</dt>
                  <dd className="mt-0.5 break-all font-mono text-ink">{row.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        </Card>
      </div>

      <ConfirmDialog
        open={resetOpen}
        onClose={() => setResetOpen(false)}
        onConfirm={confirmReset}
        destructive
        loading={resetting}
        title="Reset demo dataset?"
        description="All leads, calls and automation run history will be regenerated from the seed. Local edits are lost."
        confirmLabel="Reset data"
      />
    </div>
  );
}
