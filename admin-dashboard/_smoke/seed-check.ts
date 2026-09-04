import { buildLeads, buildCalls } from '../src/api/seed';
import type { Lead, CallRecord } from '../src/types';

const leads: Lead[] = buildLeads();
const calls: CallRecord[] = buildCalls(leads);

const bad = (l: Lead) =>
  !l.id || !l.name || !l.phone || !l.city || !Number.isFinite(l.score) ||
  l.score < 0 || l.score > 100 || Number.isNaN(+new Date(l.createdAt));

const badCall = (c: CallRecord) =>
  !c.id || !c.leadId || !Number.isFinite(c.durationSec) || Number.isNaN(+new Date(c.startedAt));

const statuses: Record<string, number> = {};
leads.forEach((l) => (statuses[l.status] = (statuses[l.status] ?? 0) + 1));
const outcomes: Record<string, number> = {};
calls.forEach((c) => (outcomes[c.outcome] = (outcomes[c.outcome] ?? 0) + 1));

console.log(JSON.stringify({
  leads: leads.length,
  calls: calls.length,
  invalidLeads: leads.filter(bad).length,
  invalidCalls: calls.filter(badCall).length,
  uniqueIds: new Set(leads.map((l) => l.id)).size,
  uniquePhones: new Set(leads.map((l) => l.phone)).size,
  statuses,
  outcomes,
  sampleLead: leads[0],
  callsSorted: calls.every((c, i) => i === 0 || +new Date(calls[i - 1].startedAt) >= +new Date(c.startedAt)),
  totalMinutes: Math.round(calls.reduce((s, c) => s + c.durationSec, 0) / 60),
}, null, 2));
