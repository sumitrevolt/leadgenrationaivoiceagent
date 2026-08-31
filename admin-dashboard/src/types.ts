/* ------------------------------------------------------------------
 * Domain model — Leads & AI Voice Calls
 * ------------------------------------------------------------------ */

export type LeadStatus =
  | 'new'
  | 'enriched'
  | 'contacted'
  | 'qualified'
  | 'nurturing'
  | 'converted'
  | 'disqualified';

export type LeadTemperature = 'hot' | 'warm' | 'cold';

export type LeadSource =
  | 'google_maps'
  | 'website_audit'
  | 'seo_page'
  | 'referral'
  | 'campaign'
  | 'manual';

export type Niche =
  | 'salon'
  | 'clinic'
  | 'gym'
  | 'real_estate'
  | 'coaching'
  | 'restaurant'
  | 'boutique'
  | 'automobile';

export interface Lead {
  id: string;
  name: string;
  businessName: string;
  phone: string;
  email: string;
  city: string;
  state: string;
  niche: Niche;
  source: LeadSource;
  status: LeadStatus;
  temperature: LeadTemperature;
  score: number; // 0-100
  owner: string;
  notes: string;
  lastContactedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

/** Fields the operator is allowed to submit from the create/edit form. */
export type LeadInput = Omit<Lead, 'id' | 'createdAt' | 'updatedAt'>;

/* ---- Calls ---- */

export type CallOutcome =
  | 'connected'
  | 'no_answer'
  | 'busy'
  | 'voicemail'
  | 'failed'
  | 'scheduled';

export type CallIntent =
  | 'interested'
  | 'callback'
  | 'not_interested'
  | 'wrong_number'
  | 'unknown';

export type CallSentiment = 'positive' | 'neutral' | 'negative';

export interface CallRecord {
  id: string;
  leadId: string;
  leadName: string;
  businessName: string;
  direction: 'outbound' | 'inbound';
  outcome: CallOutcome;
  intent: CallIntent;
  sentiment: CallSentiment;
  durationSec: number;
  costInr: number;
  transcript: string;
  startedAt: string;
}

/* ---- Table plumbing ---- */

export type SortDirection = 'asc' | 'desc';

export interface ListQuery {
  q?: string;
  page?: number;
  pageSize?: number;
  sort?: string;
  dir?: SortDirection;
  [key: string]: string | number | undefined;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

/* ---- Metrics ---- */

export interface MetricPoint {
  label: string;
  value: number;
}

export interface NamedSlice {
  name: string;
  value: number;
}

export interface DashboardMetrics {
  totals: {
    leads: number;
    calls: number;
    converted: number;
    contactRate: number; // percentage
    conversionRate: number; // percentage
    avgCallSeconds: number;
    minutesUsed: number;
    minutesIncluded: number;
  };
  deltas: Record<string, number>; // percentage change vs previous period
  leadsByDay: MetricPoint[];
  callsByDay: MetricPoint[];
  leadsByStatus: NamedSlice[];
  leadsByNiche: NamedSlice[];
  outcomeSplit: NamedSlice[];
  topCities: NamedSlice[];
  funnel: { stage: string; count: number }[];
  generatedAt: string;
}

/* ---- Automations ---- */

export type AutomationCategory = 'data' | 'outreach' | 'voice' | 'hygiene' | 'reporting';

export type AutomationParamType = 'number' | 'select' | 'text' | 'boolean';

export interface AutomationParam {
  name: string;
  label: string;
  type: AutomationParamType;
  defaultValue: string | number | boolean;
  options?: { label: string; value: string }[];
  min?: number;
  max?: number;
  help?: string;
}

export interface AutomationDef {
  id: string;
  name: string;
  summary: string;
  detail: string;
  category: AutomationCategory;
  cron: string; // human-readable schedule
  enabled: boolean;
  avgDurationMs: number;
  destructive: boolean;
  params: AutomationParam[];
  lastRun: AutomationRun | null;
}

export type RunStatus = 'queued' | 'running' | 'success' | 'failed';

export interface AutomationRun {
  id: string;
  automationId: string;
  automationName: string;
  status: RunStatus;
  triggeredBy: 'manual' | 'schedule';
  startedAt: string;
  finishedAt: string | null;
  recordsProcessed: number;
  message: string;
  error?: string;
}

/* ---- Session ---- */

export type Role = 'owner' | 'operator' | 'viewer';

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  initials: string;
}

export interface Session {
  token: string;
  user: User;
  issuedAt: string;
  expiresAt: string;
}
