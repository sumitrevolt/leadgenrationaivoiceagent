import type {
  AutomationDef,
  AutomationRun,
  CallRecord,
  DashboardMetrics,
  Lead,
  LeadInput,
  LeadTemperature,
  ListQuery,
  Niche,
  Page,
  Session,
  SortDirection,
  User,
} from '@/types';
import { buildCalls, buildLeads } from './seed';
import { sleep } from '@/lib/utils';

/* ==================================================================
 * API seam
 * ------------------------------------------------------------------
 * The whole UI talks to the `ApiClient` interface below. Today it is
 * backed by an in-memory + localStorage implementation so the app is
 * immediately runnable. To go live, implement the same interface with
 * `fetch` against the FastAPI service and change the single export at
 * the bottom of this file. No UI code needs to change.
 * ================================================================== */

export class ApiError extends Error {
  status: number;
  constructor(message: string, status = 500) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export interface SessionCredentials {
  email: string;
  password: string;
  remember?: boolean;
}

export interface LeadFilters {
  status?: string;
  niche?: string;
  temperature?: string;
  source?: string;
  owner?: string;
}

export interface CallFilters {
  outcome?: string;
  intent?: string;
  sentiment?: string;
  direction?: string;
}

export interface ApiClient {
  auth: {
    login(c: SessionCredentials): Promise<Session>;
    logout(): Promise<void>;
    me(token: string): Promise<User>;
  };
  leads: {
    list(q: ListQuery & LeadFilters): Promise<Page<Lead>>;
    get(id: string): Promise<Lead>;
    create(input: LeadInput): Promise<Lead>;
    update(id: string, input: LeadInput): Promise<Lead>;
    remove(id: string): Promise<void>;
    removeMany(ids: string[]): Promise<number>;
    exportAll(q: ListQuery & LeadFilters): Promise<Lead[]>;
  };
  calls: {
    list(q: ListQuery & CallFilters): Promise<Page<CallRecord>>;
  };
  metrics: {
    overview(rangeDays: number): Promise<DashboardMetrics>;
  };
  automations: {
    list(): Promise<AutomationDef[]>;
    setEnabled(id: string, enabled: boolean): Promise<AutomationDef>;
    trigger(
      id: string,
      params: Record<string, string | number | boolean>,
      opts?: { dryRun?: boolean },
    ): Promise<AutomationRun>;
    runs(limit?: number): Promise<AutomationRun[]>;
  };
  /** Test hook: force a failure rate so error/retry UI can be exercised. */
  setFailureRate(rate: number): void;
  getFailureRate(): number;
  resetData(): Promise<void>;
}

/* ---------------- persistence helpers ---------------- */

const STORE_KEY = 'lg_admin_store_v1';

interface StoreShape {
  leads: Lead[];
  calls: CallRecord[];
  runs: AutomationRun[];
  automations: AutomationDef[];
}

function freshStore(): StoreShape {
  const leads = buildLeads();
  const calls = buildCalls(leads);
  return { leads, calls, runs: [], automations: defaultAutomations() };
}

function loadStore(): StoreShape {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return freshStore();
    const parsed = JSON.parse(raw) as Partial<StoreShape>;
    if (!Array.isArray(parsed.leads) || !Array.isArray(parsed.calls)) return freshStore();
    const base = freshStore();
    return {
      leads: parsed.leads,
      calls: parsed.calls,
      runs: Array.isArray(parsed.runs) ? parsed.runs : [],
      // Automation *definitions* always come from code, but runtime flags persist.
      automations: base.automations.map((a) => {
        const saved = (parsed.automations ?? []).find((x) => x.id === a.id);
        return saved ? { ...a, enabled: saved.enabled, lastRun: saved.lastRun ?? null } : a;
      }),
    };
  } catch {
    return freshStore();
  }
}

function persist(store: StoreShape) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch {
    /* quota or private mode — in-memory state still works */
  }
}

/* ---------------- automation catalogue ---------------- */

function defaultAutomations(): AutomationDef[] {
  return [
    {
      id: 'enrich_leads',
      name: 'Lead Enrichment',
      summary: 'Fill missing email / notes and pull firmographic signals.',
      detail:
        'Runs each un-enriched lead through the free provider chain (SearXNG → Google Maps Places → Mistral) and back-fills email, notes and city/state. Promotes status from `new` to `enriched`.',
      category: 'data',
      cron: 'Every 30 minutes',
      enabled: true,
      avgDurationMs: 1600,
      destructive: false,
      params: [
        {
          name: 'limit',
          label: 'Batch size',
          type: 'number',
          defaultValue: 50,
          min: 1,
          max: 250,
          help: 'Max leads processed in one run.',
        },
        {
          name: 'provider',
          label: 'Provider chain',
          type: 'select',
          defaultValue: 'auto',
          options: [
            { label: 'Auto (free chain)', value: 'auto' },
            { label: 'Google Maps only', value: 'maps' },
            { label: 'SearXNG only', value: 'searxng' },
          ],
        },
      ],
      lastRun: null,
    },
    {
      id: 'score_leads',
      name: 'Lead Scoring',
      summary: 'Recompute 0-100 score and hot / warm / cold band.',
      detail:
        'Applies the scoring heuristic (status weight + recency decay + source quality + call history) to every lead and re-bands temperature. Hot ≥ 72, Warm ≥ 45, else Cold.',
      category: 'data',
      cron: 'Hourly',
      enabled: true,
      avgDurationMs: 900,
      destructive: false,
      params: [
        {
          name: 'model',
          label: 'Scoring model',
          type: 'select',
          defaultValue: 'heuristic_v2',
          options: [
            { label: 'Heuristic v2 (recency aware)', value: 'heuristic_v2' },
            { label: 'Heuristic v1 (flat)', value: 'baseline' },
          ],
        },
      ],
      lastRun: null,
    },
    {
      id: 'dedupe_leads',
      name: 'Duplicate Cleanup',
      summary: 'Merge leads that share the same phone number.',
      detail:
        'Groups leads by normalised phone number and keeps one record per group. This permanently deletes the losing rows — run a dry run first if you are unsure.',
      category: 'hygiene',
      cron: 'Daily at 02:00 IST',
      enabled: true,
      avgDurationMs: 1400,
      destructive: true,
      params: [
        {
          name: 'strategy',
          label: 'Keep which record?',
          type: 'select',
          defaultValue: 'keep_newest',
          options: [
            { label: 'Keep newest', value: 'keep_newest' },
            { label: 'Keep oldest', value: 'keep_oldest' },
            { label: 'Keep highest score', value: 'keep_best' },
          ],
        },
        {
          name: 'dryRun',
          label: 'Dry run (report only, no deletes)',
          type: 'boolean',
          defaultValue: true,
        },
      ],
      lastRun: null,
    },
    {
      id: 'auto_dial_batch',
      name: 'AI Auto-Dial Batch',
      summary: 'Place outbound AI voice calls to the next batch of leads.',
      detail:
        'Picks the highest-scoring leads that have not been contacted recently and places AI voice calls through Vobiz. Writes a call record per attempt and advances the lead to `contacted`.',
      category: 'voice',
      cron: 'Every 15 minutes (09:00–20:00 IST)',
      enabled: true,
      avgDurationMs: 2600,
      destructive: false,
      params: [
        {
          name: 'batchSize',
          label: 'Calls to place',
          type: 'number',
          defaultValue: 25,
          min: 1,
          max: 100,
        },
        {
          name: 'niche',
          label: 'Restrict to niche',
          type: 'select',
          defaultValue: 'all',
          options: [
            { label: 'All niches', value: 'all' },
            { label: 'Salon', value: 'salon' },
            { label: 'Clinic', value: 'clinic' },
            { label: 'Gym', value: 'gym' },
            { label: 'Real estate', value: 'real_estate' },
            { label: 'Coaching', value: 'coaching' },
            { label: 'Restaurant', value: 'restaurant' },
            { label: 'Boutique', value: 'boutique' },
            { label: 'Automobile', value: 'automobile' },
          ],
        },
        {
          name: 'respectDnd',
          label: 'Skip DND-flagged numbers',
          type: 'boolean',
          defaultValue: true,
        },
      ],
      lastRun: null,
    },
    {
      id: 'retry_no_answer',
      name: 'No-Answer Retry',
      summary: 'Re-dial leads whose previous calls were not answered.',
      detail:
        'Finds call records with outcome no_answer / busy / failed and re-queues them, capped by attempt count and a minimum back-off window.',
      category: 'voice',
      cron: 'Every 3 hours',
      enabled: true,
      avgDurationMs: 1800,
      destructive: false,
      params: [
        { name: 'maxAttempts', label: 'Attempt ceiling', type: 'number', defaultValue: 3, min: 1, max: 6 },
        { name: 'backoffHours', label: 'Back-off (hours)', type: 'number', defaultValue: 6, min: 1, max: 72 },
      ],
      lastRun: null,
    },
    {
      id: 'followup_sequences',
      name: 'Follow-up Sequences',
      summary: 'Send WhatsApp / email follow-ups to qualified leads.',
      detail:
        'Advances every qualified or nurturing lead to the next step of its sequence and stamps `lastContactedAt`. Uses the Hostinger SMTP relay and WAHA for WhatsApp.',
      category: 'outreach',
      cron: 'Daily at 11:00 IST',
      enabled: true,
      avgDurationMs: 1500,
      destructive: false,
      params: [
        {
          name: 'channel',
          label: 'Channel',
          type: 'select',
          defaultValue: 'both',
          options: [
            { label: 'WhatsApp + Email', value: 'both' },
            { label: 'WhatsApp only', value: 'whatsapp' },
            { label: 'Email only', value: 'email' },
          ],
        },
        { name: 'limit', label: 'Max sends', type: 'number', defaultValue: 100, min: 1, max: 500 },
      ],
      lastRun: null,
    },
    {
      id: 'transcribe_backlog',
      name: 'Call Transcription',
      summary: 'Transcribe connected calls that are missing a transcript.',
      detail:
        'Pushes call audio through Groq whisper-large-v3 (with EdgeTTS/Gemini fallback) and stores the transcript plus intent and sentiment classification.',
      category: 'voice',
      cron: 'Every 20 minutes',
      enabled: true,
      avgDurationMs: 2200,
      destructive: false,
      params: [{ name: 'limit', label: 'Calls per run', type: 'number', defaultValue: 40, min: 1, max: 200 }],
      lastRun: null,
    },
    {
      id: 'stale_lead_reaper',
      name: 'Stale Lead Reaper',
      summary: 'Demote or disqualify leads with no activity for N days.',
      detail:
        'Leads untouched beyond the inactivity threshold are moved to `nurturing`, and beyond twice the threshold to `disqualified`. This is a destructive state change.',
      category: 'hygiene',
      cron: 'Weekly, Sunday 23:30 IST',
      enabled: false,
      avgDurationMs: 1100,
      destructive: true,
      params: [
        { name: 'daysInactive', label: 'Inactivity threshold (days)', type: 'number', defaultValue: 30, min: 7, max: 180 },
        {
          name: 'action',
          label: 'Action',
          type: 'select',
          defaultValue: 'nurture',
          options: [
            { label: 'Move to nurturing', value: 'nurture' },
            { label: 'Disqualify', value: 'disqualify' },
          ],
        },
      ],
      lastRun: null,
    },
    {
      id: 'nightly_digest',
      name: 'Nightly Digest Report',
      summary: 'Build and email the daily performance digest.',
      detail:
        'Aggregates lead, call and conversion metrics for the day, renders the digest and emails it to the configured recipients through Hostinger SMTP.',
      category: 'reporting',
      cron: 'Daily at 21:00 IST',
      enabled: true,
      avgDurationMs: 1000,
      destructive: false,
      params: [
        {
          name: 'recipient',
          label: 'Recipient',
          type: 'text',
          defaultValue: 'admin@leadsgenai.in',
          help: 'Comma separated for multiple recipients.',
        },
        {
          name: 'includeTranscripts',
          label: 'Attach call transcripts',
          type: 'boolean',
          defaultValue: false,
        },
      ],
      lastRun: null,
    },
  ];
}

/* ---------------- mock implementation ---------------- */

const DEMO_USERS: Record<string, { password: string; user: User }> = {
  'admin@leadsgenai.in': {
    password: 'admin123',
    user: {
      id: 'USR-1',
      name: 'Sumit Revolt',
      email: 'admin@leadsgenai.in',
      role: 'owner',
      initials: 'SR',
    },
  },
  'ops@leadsgenai.in': {
    password: 'ops123',
    user: {
      id: 'USR-2',
      name: 'Riya Nair',
      email: 'ops@leadsgenai.in',
      role: 'operator',
      initials: 'RN',
    },
  },
};

function compare(a: unknown, b: unknown): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  const sa = String(a ?? '').toLowerCase();
  const sb = String(b ?? '').toLowerCase();
  return sa.localeCompare(sb);
}

function applySort<T extends Record<string, unknown>>(
  items: T[],
  sort?: string,
  dir: SortDirection = 'asc',
) {
  if (!sort) return items;
  const sorted = [...items].sort((x, y) => compare(x[sort], y[sort]));
  return dir === 'desc' ? sorted.reverse() : sorted;
}

/** Temperature is a derived band, so the API owns the invariant — never trust a client value. */
function bandFor(score: number): LeadTemperature {
  return score >= 72 ? 'hot' : score >= 45 ? 'warm' : 'cold';
}

function createMockApiClient(): ApiClient {
  let store: StoreShape = loadStore();
  let failureRate = 0; // configurable from the Settings page

  const save = () => persist(store);

  async function hop(ms: number) {
    await sleep(ms);
    if (failureRate > 0 && Math.random() < failureRate) {
      throw new ApiError('Upstream service is temporarily unavailable.', 503);
    }
  }

  const latency = (base: number) => base * (0.6 + Math.random() * 0.8);

  function findAutomation(id: string) {
    const found = store.automations.find((a) => a.id === id);
    if (!found) throw new ApiError(`Unknown automation "${id}".`, 404);
    return found;
  }

  function pushRun(run: AutomationRun) {
    store.runs = [run, ...store.runs].slice(0, 60);
    const def = store.automations.find((a) => a.id === run.automationId);
    if (def) def.lastRun = run;
    save();
  }

  /* --- automation effects --- */

  function runAutomation(
    def: AutomationDef,
    params: Record<string, string | number | boolean>,
    dryRun: boolean,
  ): { processed: number; message: string } {
    const now = new Date().toISOString();

    switch (def.id) {
      case 'enrich_leads': {
        const limit = Number(params.limit ?? 50);
        const targets = store.leads
          .filter((l) => !l.email || l.status === 'new')
          .sort((a, b) => +new Date(b.createdAt) - +new Date(a.createdAt))
          .slice(0, limit);
        if (dryRun) {
          return { processed: targets.length, message: `${targets.length} leads would be enriched.` };
        }
        targets.forEach((l) => {
          if (!l.email) l.email = `owner.${l.phone.slice(-6)}@${l.niche}mail.in`;
          if (!l.notes) l.notes = 'Auto-enriched: firmographics pulled from public sources.';
          if (l.status === 'new') l.status = 'enriched';
          l.updatedAt = now;
        });
        return { processed: targets.length, message: `Enriched ${targets.length} leads.` };
      }

      case 'score_leads': {
        const useV2 = (params.model ?? 'heuristic_v2') === 'heuristic_v2';
        if (dryRun) return { processed: store.leads.length, message: `${store.leads.length} leads would be re-scored.` };
        store.leads.forEach((l) => {
          const statusWeight: Record<string, number> = {
            converted: 92,
            qualified: 78,
            nurturing: 60,
            contacted: 58,
            enriched: 48,
            new: 34,
            disqualified: 12,
          };
          const sourceWeight: Record<string, number> = {
            referral: 12,
            website_audit: 8,
            campaign: 5,
            seo_page: 3,
            google_maps: 0,
            manual: -4,
          };
          const ageDays = (Date.now() - +new Date(l.createdAt)) / 86400000;
          const recency = useV2 ? Math.max(-14, -Math.round(ageDays / 6)) : 0;
          const base = (statusWeight[l.status] ?? 40) + (sourceWeight[l.source] ?? 0) + recency;
          l.score = Math.max(1, Math.min(99, Math.round(base)));
          l.temperature = l.score >= 72 ? 'hot' : l.score >= 45 ? 'warm' : 'cold';
          l.updatedAt = now;
        });
        return { processed: store.leads.length, message: `Re-scored ${store.leads.length} leads.` };
      }

      case 'dedupe_leads': {
        const strategy = String(params.strategy ?? 'keep_newest');
        const byPhone = new Map<string, Lead[]>();
        store.leads.forEach((l) => {
          const key = l.phone.replace(/\D/g, '').slice(-10);
          const group = byPhone.get(key) ?? [];
          group.push(l);
          byPhone.set(key, group);
        });
        const doomed: string[] = [];
        byPhone.forEach((group) => {
          if (group.length < 2) return;
          const sorted = [...group].sort((a, b) => {
            if (strategy === 'keep_oldest') return +new Date(a.createdAt) - +new Date(b.createdAt);
            if (strategy === 'keep_best') return b.score - a.score;
            return +new Date(b.createdAt) - +new Date(a.createdAt);
          });
          doomed.push(...sorted.slice(1).map((l) => l.id));
        });
        if (dryRun) {
          return { processed: doomed.length, message: `${doomed.length} duplicates would be removed.` };
        }
        store.leads = store.leads.filter((l) => !doomed.includes(l.id));
        return { processed: doomed.length, message: `Removed ${doomed.length} duplicate leads.` };
      }

      case 'auto_dial_batch': {
        const size = Number(params.batchSize ?? 25);
        const niche = String(params.niche ?? 'all');
        const pool = store.leads
          .filter(
            (l) =>
              l.status !== 'converted' &&
              l.status !== 'disqualified' &&
              (niche === 'all' || l.niche === niche),
          )
          .sort((a, b) => b.score - a.score)
          .slice(0, size);
        if (dryRun) return { processed: pool.length, message: `${pool.length} calls would be placed.` };

        const outcomes = ['connected', 'connected', 'no_answer', 'busy', 'voicemail', 'failed'];
        const intents = ['interested', 'callback', 'not_interested', 'unknown'];
        let callSeq = store.calls.length + 60000;
        pool.forEach((lead) => {
          const outcome = outcomes[Math.floor(Math.random() * outcomes.length)];
          const connected = outcome === 'connected';
          const durationSec = connected ? Math.floor(35 + Math.random() * 480) : Math.floor(Math.random() * 16);
          store.calls.unshift({
            id: `CL-${callSeq++}`,
            leadId: lead.id,
            leadName: lead.name,
            businessName: lead.businessName,
            direction: 'outbound',
            outcome: outcome as CallRecord['outcome'],
            intent: (connected ? intents[Math.floor(Math.random() * intents.length)] : 'unknown') as CallRecord['intent'],
            sentiment: connected
              ? (['positive', 'neutral', 'negative'][Math.floor(Math.random() * 3)] as CallRecord['sentiment'])
              : 'neutral',
            durationSec,
            costInr: connected ? Number(((durationSec / 60) * 1.9).toFixed(2)) : 0,
            transcript: connected
              ? 'AI: Namaste, main LeadsGen AI se bol rahi hoon. Kya aap apne business ke liye naye customers dhoondh rahe hain?'
              : '',
            startedAt: now,
          });
          if (lead.status === 'new' || lead.status === 'enriched') lead.status = 'contacted';
          lead.lastContactedAt = now;
          lead.updatedAt = now;
        });
        return { processed: pool.length, message: `Placed ${pool.length} AI calls.` };
      }

      case 'retry_no_answer': {
        const maxAttempts = Number(params.maxAttempts ?? 3);
        const backoffHours = Number(params.backoffHours ?? 6);
        const cutoff = Date.now() - backoffHours * 3600_000;
        const attempts = new Map<string, number>();
        store.calls.forEach((c) => {
          attempts.set(c.leadId, (attempts.get(c.leadId) ?? 0) + 1);
        });
        const targets = store.leads.filter((l) => {
          if (l.status === 'converted' || l.status === 'disqualified') return false;
          if ((attempts.get(l.id) ?? 0) >= maxAttempts) return false;
          const last = l.lastContactedAt ? +new Date(l.lastContactedAt) : 0;
          return last === 0 || last < cutoff;
        });
        if (dryRun) return { processed: targets.length, message: `${targets.length} retries would be queued.` };
        let seq = store.calls.length + 70000;
        targets.forEach((lead) => {
          const outcome = Math.random() < 0.62 ? 'connected' : 'no_answer';
          const connected = outcome === 'connected';
          const durationSec = connected ? Math.floor(40 + Math.random() * 400) : 0;
          store.calls.unshift({
            id: `CL-${seq++}`,
            leadId: lead.id,
            leadName: lead.name,
            businessName: lead.businessName,
            direction: 'outbound',
            outcome: outcome as CallRecord['outcome'],
            intent: (connected ? 'callback' : 'unknown') as CallRecord['intent'],
            sentiment: connected ? 'positive' : 'neutral',
            durationSec,
            costInr: connected ? Number(((durationSec / 60) * 1.9).toFixed(2)) : 0,
            transcript: connected ? 'AI: Follow-up call connected. Prospect requested a callback window.' : '',
            startedAt: now,
          });
          lead.lastContactedAt = now;
          lead.updatedAt = now;
        });
        return { processed: targets.length, message: `Queued ${targets.length} retry calls.` };
      }

      case 'followup_sequences': {
        const limit = Number(params.limit ?? 100);
        const targets = store.leads
          .filter((l) => l.status === 'qualified' || l.status === 'nurturing')
          .slice(0, limit);
        if (dryRun)
          return { processed: targets.length, message: `${targets.length} follow-ups would be sent.` };
        targets.forEach((l) => {
          l.lastContactedAt = now;
          l.notes = l.notes
            ? `${l.notes} | Follow-up sent ${new Date(now).toLocaleDateString('en-IN')}.`
            : `Follow-up sent ${new Date(now).toLocaleDateString('en-IN')}.`;
          l.updatedAt = now;
        });
        return { processed: targets.length, message: `Sent ${targets.length} follow-ups.` };
      }

      case 'transcribe_backlog': {
        const limit = Number(params.limit ?? 40);
        const targets = store.calls
          .filter((c) => c.outcome === 'connected' && !c.transcript)
          .slice(0, limit);
        if (dryRun)
          return { processed: targets.length, message: `${targets.length} calls would be transcribed.` };
        targets.forEach((c) => {
          c.transcript =
            'AI: Namaste, main LeadsGen AI se bol rahi hoon. / Prospect: Haan, batayiye aapki service kya hai?';
          if (c.intent === 'unknown') c.intent = Math.random() < 0.5 ? 'interested' : 'callback';
          c.sentiment = c.intent === 'interested' ? 'positive' : 'neutral';
        });
        return { processed: targets.length, message: `Transcribed ${targets.length} calls.` };
      }

      case 'stale_lead_reaper': {
        const days = Number(params.daysInactive ?? 30);
        const action = String(params.action ?? 'nurture');
        const threshold = Date.now() - days * 86400_000;
        const hard = Date.now() - days * 2 * 86400_000;
        const targets = store.leads.filter((l) => {
          if (l.status === 'converted') return false;
          const ref = l.lastContactedAt ? +new Date(l.lastContactedAt) : +new Date(l.createdAt);
          return ref < threshold;
        });
        if (dryRun) return { processed: targets.length, message: `${targets.length} leads would be demoted.` };
        targets.forEach((l) => {
          const ref = l.lastContactedAt ? +new Date(l.lastContactedAt) : +new Date(l.createdAt);
          l.status = action === 'disqualify' && ref < hard ? 'disqualified' : 'nurturing';
          l.temperature = 'cold';
          l.updatedAt = now;
        });
        return { processed: targets.length, message: `Demoted ${targets.length} stale leads.` };
      }

      case 'nightly_digest': {
        const connected = store.calls.filter((c) => c.outcome === 'connected').length;
        const converted = store.leads.filter((l) => l.status === 'converted').length;
        const recipient = String(params.recipient ?? 'admin@leadsgenai.in');
        return {
          processed: 1,
          message: `Digest built (${connected} connected calls, ${converted} conversions) → ${recipient}.`,
        };
      }

      default:
        throw new ApiError(`No handler wired for automation "${def.id}".`, 501);
    }
  }

  /* --- client surface --- */

  return {
    auth: {
      async login({ email, password }) {
        await hop(latency(550));
        const entry = DEMO_USERS[email.trim().toLowerCase()];
        if (!entry || entry.password !== password) {
          throw new ApiError('Invalid email or password.', 401);
        }
        const issuedAt = new Date();
        const expiresAt = new Date(issuedAt.getTime() + 8 * 3600_000);
        return {
          token: `sess_${entry.user.id}_${Math.random().toString(36).slice(2)}_${issuedAt.getTime()}`,
          user: entry.user,
          issuedAt: issuedAt.toISOString(),
          expiresAt: expiresAt.toISOString(),
        };
      },
      async logout() {
        await hop(latency(180));
      },
      async me(token) {
        await hop(latency(160));
        const parts = token.split('_');
        if (parts[0] !== 'sess' || !parts[1]) throw new ApiError('Session expired.', 401);
        const entry = Object.values(DEMO_USERS).find((u) => u.user.id === parts[1]);
        if (!entry) throw new ApiError('Session expired.', 401);
        return entry.user;
      },
    },

    leads: {
      async list(q) {
        await hop(latency(420));
        const needle = (q.q ?? '').trim();
        let rows = store.leads;
        if (needle) {
          rows = rows.filter((l) =>
            [l.name, l.businessName, l.phone, l.email, l.city, l.owner, l.id, l.niche, l.status]
              .join(' ')
              .toLowerCase()
              .includes(needle.toLowerCase()),
          );
        }
        if (q.status) rows = rows.filter((l) => l.status === q.status);
        if (q.niche) rows = rows.filter((l) => l.niche === q.niche);
        if (q.temperature) rows = rows.filter((l) => l.temperature === q.temperature);
        if (q.source) rows = rows.filter((l) => l.source === q.source);
        if (q.owner) rows = rows.filter((l) => l.owner === q.owner);

        rows = applySort(rows as unknown as Record<string, unknown>[], q.sort, q.dir) as unknown as Lead[];

        const pageSize = q.pageSize ?? 10;
        const page = q.page ?? 1;
        const start = (page - 1) * pageSize;
        return { items: rows.slice(start, start + pageSize), total: rows.length, page, pageSize };
      },

      async get(id) {
        await hop(latency(220));
        const found = store.leads.find((l) => l.id === id);
        if (!found) throw new ApiError('Lead not found.', 404);
        return found;
      },

      async create(input) {
        await hop(latency(520));
        const dupe = store.leads.find(
          (l) => l.phone.replace(/\D/g, '').slice(-10) === input.phone.replace(/\D/g, '').slice(-10),
        );
        if (dupe) throw new ApiError(`A lead with this phone already exists (${dupe.id}).`, 409);
        const now = new Date().toISOString();
        const lead: Lead = {
          ...input,
          id: `LD-${1000 + store.leads.length + Math.floor(Math.random() * 90)}`,
          createdAt: now,
          updatedAt: now,
        };
        store.leads = [lead, ...store.leads];
        save();
        return lead;
      },

      async update(id, input) {
        await hop(latency(480));
        const idx = store.leads.findIndex((l) => l.id === id);
        if (idx === -1) throw new ApiError('Lead not found.', 404);
        const next: Lead = { ...store.leads[idx], ...input, id, updatedAt: new Date().toISOString() };
        store.leads[idx] = next;
        save();
        return next;
      },

      async remove(id) {
        await hop(latency(420));
        const before = store.leads.length;
        store.leads = store.leads.filter((l) => l.id !== id);
        if (store.leads.length === before) throw new ApiError('Lead not found.', 404);
        save();
      },

      async removeMany(ids) {
        await hop(latency(700));
        const set = new Set(ids);
        const before = store.leads.length;
        store.leads = store.leads.filter((l) => !set.has(l.id));
        save();
        return before - store.leads.length;
      },

      async exportAll(q) {
        await hop(latency(300));
        const needle = (q.q ?? '').trim().toLowerCase();
        return store.leads.filter((l) => {
          if (needle && ![l.name, l.businessName, l.phone, l.email, l.city].join(' ').toLowerCase().includes(needle))
            return false;
          if (q.status && l.status !== q.status) return false;
          if (q.niche && l.niche !== q.niche) return false;
          if (q.temperature && l.temperature !== q.temperature) return false;
          return true;
        });
      },
    },

    calls: {
      async list(q) {
        await hop(latency(420));
        const needle = (q.q ?? '').trim().toLowerCase();
        let rows = store.calls;
        if (needle) {
          rows = rows.filter((c) =>
            [c.id, c.leadName, c.businessName, c.leadId, c.outcome, c.intent, c.transcript]
              .join(' ')
              .toLowerCase()
              .includes(needle),
          );
        }
        if (q.outcome) rows = rows.filter((c) => c.outcome === q.outcome);
        if (q.intent) rows = rows.filter((c) => c.intent === q.intent);
        if (q.sentiment) rows = rows.filter((c) => c.sentiment === q.sentiment);
        if (q.direction) rows = rows.filter((c) => c.direction === q.direction);

        rows = applySort(
          rows as unknown as Record<string, unknown>[],
          q.sort,
          q.dir,
        ) as unknown as CallRecord[];

        const pageSize = q.pageSize ?? 10;
        const page = q.page ?? 1;
        const start = (page - 1) * pageSize;
        return { items: rows.slice(start, start + pageSize), total: rows.length, page, pageSize };
      },
    },

    metrics: {
      async overview(rangeDays) {
        await hop(latency(600));
        const since = Date.now() - rangeDays * 86400_000;
        const recentLeads = store.leads.filter((l) => +new Date(l.createdAt) >= since);
        const recentCalls = store.calls.filter((c) => +new Date(c.startedAt) >= since);

        const connected = recentCalls.filter((c) => c.outcome === 'connected' || c.outcome === 'scheduled');
        const converted = store.leads.filter((l) => l.status === 'converted');
        const minutesUsed = Math.round(
          recentCalls.reduce((sum, c) => sum + c.durationSec, 0) / 60,
        );

        const contactRate = recentCalls.length
          ? (connected.length / recentCalls.length) * 100
          : 0;
        const conversionRate = store.leads.length ? (converted.length / store.leads.length) * 100 : 0;
        const avgCallSeconds = connected.length
          ? connected.reduce((s, c) => s + c.durationSec, 0) / connected.length
          : 0;

        /* daily series */
        const dayLabels: string[] = [];
        for (let i = rangeDays - 1; i >= 0; i--) {
          const d = new Date();
          d.setDate(d.getDate() - i);
          dayLabels.push(d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }));
        }
        const leadsByDay = dayLabels.map((label) => ({
          label,
          value: recentLeads.filter(
            (l) =>
              new Date(l.createdAt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }) ===
              label,
          ).length,
        }));
        const callsByDay = dayLabels.map((label) => ({
          label,
          value: recentCalls.filter(
            (c) =>
              new Date(c.startedAt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }) ===
              label,
          ).length,
        }));

        const slice = (items: Record<string, unknown>[], key: string) => {
          const counts = new Map<string, number>();
          items.forEach((it) => {
            const k = String(it[key]);
            counts.set(k, (counts.get(k) ?? 0) + 1);
          });
          return [...counts.entries()]
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => b.value - a.value);
        };

        const niches: Niche[] = [
          'salon',
          'clinic',
          'gym',
          'real_estate',
          'coaching',
          'restaurant',
          'boutique',
          'automobile',
        ];

        return {
          totals: {
            leads: store.leads.length,
            calls: recentCalls.length,
            converted: converted.length,
            contactRate,
            conversionRate,
            avgCallSeconds,
            minutesUsed,
            minutesIncluded: 500,
          },
          deltas: {
            leads: 12.4,
            calls: 8.1,
            converted: 21.7,
            contactRate: 3.2,
            conversionRate: 1.9,
            avgCallSeconds: -4.6,
          },
          leadsByDay,
          callsByDay,
          leadsByStatus: slice(store.leads as unknown as Record<string, unknown>[], 'status'),
          leadsByNiche: niches
            .map((n) => ({ name: n, value: store.leads.filter((l) => l.niche === n).length }))
            .sort((a, b) => b.value - a.value),
          outcomeSplit: slice(recentCalls as unknown as Record<string, unknown>[], 'outcome'),
          topCities: slice(store.leads as unknown as Record<string, unknown>[], 'city').slice(0, 6),
          funnel: [
            { stage: 'Captured', count: store.leads.length },
            { stage: 'Enriched', count: store.leads.filter((l) => l.status !== 'new').length },
            { stage: 'Contacted', count: store.leads.filter((l) => l.lastContactedAt).length },
            {
              stage: 'Qualified',
              count: store.leads.filter((l) => l.status === 'qualified' || l.status === 'converted').length,
            },
            { stage: 'Converted', count: converted.length },
          ],
          generatedAt: new Date().toISOString(),
        };
      },
    },

    automations: {
      async list() {
        await hop(latency(320));
        return store.automations.map((a) => ({ ...a }));
      },

      async setEnabled(id, enabled) {
        await hop(latency(260));
        const def = findAutomation(id);
        def.enabled = enabled;
        save();
        return { ...def };
      },

      async trigger(id, params, opts) {
        const def = findAutomation(id);
        const startedAt = new Date().toISOString();
        const runId = `RUN-${Date.now().toString(36).toUpperCase()}`;
        const dryRun = Boolean(opts?.dryRun ?? (params.dryRun as boolean | undefined));

        const run: AutomationRun = {
          id: runId,
          automationId: def.id,
          automationName: def.name,
          status: 'running',
          triggeredBy: 'manual',
          startedAt,
          finishedAt: null,
          recordsProcessed: 0,
          message: dryRun ? 'Dry run in progress…' : 'Running…',
        };
        pushRun(run);

        const duration = def.avgDurationMs * (0.7 + Math.random() * 0.7);
        await sleep(duration);
        if (failureRate > 0 && Math.random() < failureRate) {
          const failed: AutomationRun = {
            ...run,
            status: 'failed',
            finishedAt: new Date().toISOString(),
            message: 'Run failed.',
            error: 'Upstream provider returned 503 after 3 retries.',
          };
          pushRun(failed);
          throw new ApiError('Automation run failed: upstream provider returned 503.', 502);
        }

        const { processed, message } = runAutomation(def, params, dryRun);
        const finished: AutomationRun = {
          ...run,
          status: 'success',
          finishedAt: new Date().toISOString(),
          recordsProcessed: processed,
          message: dryRun ? `Dry run — ${message}` : message,
        };
        pushRun(finished);
        return finished;
      },

      async runs(limit = 30) {
        await hop(latency(200));
        return store.runs.slice(0, limit);
      },
    },

    setFailureRate(rate) {
      failureRate = Math.max(0, Math.min(1, rate));
    },
    getFailureRate() {
      return failureRate;
    },
    async resetData() {
      await hop(latency(400));
      store = freshStore();
      save();
    },
  };
}

/** 👇 The single seam: swap this for an HTTP-backed implementation. */
export const api: ApiClient = createMockApiClient();
