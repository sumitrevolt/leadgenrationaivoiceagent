import { useState } from 'react';
import type { FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AlertCircle, Eye, EyeOff, Lock, Mail, PhoneCall, Sparkles, Zap } from 'lucide-react';
import { Button, Field, Input } from '@/components/ui/primitives';
import { useAuth } from '@/auth/AuthContext';
import { useTheme } from '@/lib/theme';
import { useToast } from '@/components/ui/Toast';
import { ApiError } from '@/api/client';

interface LoginErrors {
  email?: string;
  password?: string;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const { theme } = useTheme();

  const [email, setEmail] = useState('admin@leadsgenai.in');
  const [password, setPassword] = useState('admin123');
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<LoginErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? '/';

  function validate(next?: { email?: string; password?: string }) {
    const e = next?.email ?? email;
    const p = next?.password ?? password;
    const nextErrors: LoginErrors = {};
    if (!e.trim()) nextErrors.email = 'Email is required.';
    else if (!EMAIL_RE.test(e.trim())) nextErrors.email = 'Enter a valid email address.';
    if (!p) nextErrors.password = 'Password is required.';
    else if (p.length < 6) nextErrors.password = 'Password must be at least 6 characters.';
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!validate()) {
      toast.error('Check the form', 'Fix the highlighted fields and try again.');
      return;
    }
    setSubmitting(true);
    try {
      await login(email.trim(), password, remember);
      toast.success('Welcome back', 'Session started.');
      navigate(from, { replace: true });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : 'Unable to sign in right now. Please retry.';
      setFormError(message);
      toast.error('Sign in failed', message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen bg-canvas">
      {/* Brand panel — desktop only */}
      <div className="relative hidden w-1/2 overflow-hidden border-r border-line lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div
          className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            background:
              theme === 'dark'
                ? 'radial-gradient(900px 500px at 15% 10%, rgba(99,102,241,0.28), transparent 60%), radial-gradient(700px 500px at 85% 85%, rgba(56,189,248,0.18), transparent 60%)'
                : 'radial-gradient(900px 500px at 15% 10%, rgba(99,102,241,0.18), transparent 60%), radial-gradient(700px 500px at 85% 85%, rgba(56,189,248,0.14), transparent 60%)',
          }}
        />
        <div className="relative flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand text-base font-bold text-white">
            LG
          </div>
          <div>
            <p className="text-base font-semibold text-ink">LeadsGen AI</p>
            <p className="text-xs text-muted">Lead pipeline &amp; voice operations</p>
          </div>
        </div>

        <div className="relative max-w-md">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight text-ink">
            Every lead captured, scored and called — automatically.
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-muted">
            One console for the full loop: prospect discovery, AI enrichment, scoring, outbound voice
            calling and follow-up. Every automated workflow can also be fired by hand.
          </p>
          <ul className="mt-7 space-y-3">
            {[
              { icon: Sparkles, text: 'Free-tier AI stack — no per-call inference bill' },
              { icon: PhoneCall, text: 'AI telecaller with transcripts and intent tagging' },
              { icon: Zap, text: '9 automations, each with a manual trigger' },
            ].map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-3 text-sm text-muted">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-brand/12 text-brand">
                  <Icon className="h-3.5 w-3.5" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-faint">
          © {new Date().getFullYear()} LeadsGen AI · leadsgenai.in
        </p>
      </div>

      {/* Form panel */}
      <div className="flex w-full items-center justify-center px-4 py-10 sm:px-8 lg:w-1/2">
        <div className="w-full max-w-sm">
          <div className="mb-7 flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand text-base font-bold text-white">
              LG
            </div>
            <div>
              <p className="text-base font-semibold text-ink">LeadsGen AI</p>
              <p className="text-xs text-muted">Admin Console</p>
            </div>
          </div>

          <h2 className="text-xl font-semibold tracking-tight text-ink">Sign in</h2>
          <p className="mt-1 text-sm text-muted">Use your operator credentials to continue.</p>

          <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
            {formError && (
              <div
                role="alert"
                className="flex items-start gap-2.5 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2.5 text-sm text-danger"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{formError}</span>
              </div>
            )}

            <Field label="Email address" htmlFor="email" error={errors.email} required>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  placeholder="you@leadsgenai.in"
                  value={email}
                  invalid={Boolean(errors.email)}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (errors.email) validate({ email: e.target.value });
                  }}
                  onBlur={() => validate()}
                  className="pl-9"
                  disabled={submitting}
                />
              </div>
            </Field>

            <Field label="Password" htmlFor="password" error={errors.password} required>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={password}
                  invalid={Boolean(errors.password)}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (errors.password) validate({ password: e.target.value });
                  }}
                  onBlur={() => validate()}
                  className="pl-9 pr-10"
                  disabled={submitting}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-faint transition-colors hover:bg-elevated hover:text-ink"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </Field>

            <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="h-4 w-4 rounded border-line bg-elevated accent-[rgb(var(--brand))]"
              />
              Keep me signed in for 8 hours
            </label>

            <Button type="submit" size="lg" block loading={submitting}>
              {submitting ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>

          <div className="mt-6 rounded-xl border border-line bg-elevated/60 px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">
              Demo credentials
            </p>
            <div className="mt-2 space-y-1 text-xs text-muted">
              <p>
                <span className="font-medium text-ink">Owner:</span> admin@leadsgenai.in / admin123
              </p>
              <p>
                <span className="font-medium text-ink">Operator:</span> ops@leadsgenai.in / ops123
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
