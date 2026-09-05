const mem = new Map<string, string>();
(globalThis as any).localStorage = {
  getItem: (k: string) => mem.get(k) ?? null,
  setItem: (k: string, v: string) => {
    mem.set(k, v);
  },
  removeItem: (k: string) => {
    mem.delete(k);
  },
};

const { api, ApiError } = await import('../src/api/client');
api.setFailureRate(0);

const results: string[] = [];
const ok = (m: string) => results.push('PASS  ' + m);
const bad = (m: string) => results.push('FAIL  ' + m);

/* 1. auth */
try {
  await api.auth.login({ email: 'admin@leadsgenai.in', password: 'wrong' });
  bad('bad password rejected');
} catch (e) {
  e instanceof ApiError && e.status === 401
    ? ok('bad password -> 401')
    : bad('bad password error type');
}

const session = await api.auth.login({ email: 'admin@leadsgenai.in', password: 'admin123' });
ok('login ok (' + session.user.role + ')');
const me = await api.auth.me(session.token);
me.id === 'USR-1' ? ok('me() resolves user') : bad('me() mismatch');

try {
  await api.auth.me('garbage');
  bad('invalid token rejected');
} catch (e) {
  e instanceof ApiError && e.status === 401 ? ok('invalid token -> 401') : bad('invalid token error');
}

/* 2. leads list / search / sort / pagination */
const p1 = await api.leads.list({ page: 1, pageSize: 10, sort: 'score', dir: 'desc' });
p1.total > 200 && p1.items.length === 10
  ? ok('list page1 (total ' + p1.total + ')')
  : bad('list page1');
const descending = p1.items.every((l, i) => i === 0 || p1.items[i - 1].score >= l.score);
descending ? ok('sort score desc correct') : bad('sort score desc broken');
const searched = await api.leads.list({ q: p1.items[0].phone, pageSize: 5 });
searched.total === 1 ? ok('global search by phone') : bad('search by phone -> ' + searched.total);
const filtered = await api.leads.list({ status: 'converted', pageSize: 5 });
filtered.items.every((l) => l.status === 'converted')
  ? ok('status filter (' + filtered.total + ')')
  : bad('status filter');

/* 3. create / update / delete */
const before = (await api.leads.list({ pageSize: 1 })).total;
const created = await api.leads.create({
  name: 'Test Contact',
  businessName: 'QA Studio',
  phone: '9000000001',
  email: 'qa@test.in',
  city: 'Pune',
  state: 'Maharashtra',
  niche: 'salon',
  source: 'manual',
  status: 'new',
  temperature: 'cold',
  score: 30,
  owner: 'Unassigned',
  notes: '',
  lastContactedAt: null,
});
ok('create lead ' + created.id);
try {
  await api.leads.create({ ...created, phone: '9000000001' });
  bad('duplicate phone rejected');
} catch (e) {
  e instanceof ApiError && e.status === 409
    ? ok('duplicate phone -> 409')
    : bad('duplicate phone error');
}
const updated = await api.leads.update(created.id, { ...created, status: 'qualified', score: 80 });
updated.status === 'qualified' && updated.temperature === 'hot'
  ? ok('update lead + derived temperature')
  : bad('update lead');
await api.leads.remove(created.id);
const after = (await api.leads.list({ pageSize: 1 })).total;
after === before ? ok('delete lead restores count') : bad('delete lead (' + before + ' -> ' + after + ')');

/* 4. metrics */
const m = await api.metrics.overview(30);
const sane =
  m.totals.leads > 0 &&
  m.leadsByDay.length === 30 &&
  m.funnel.length === 5 &&
  m.totals.contactRate >= 0 &&
  m.totals.contactRate <= 100 &&
  Number.isFinite(m.totals.avgCallSeconds);
sane
  ? ok(
      'metrics sane (' +
        m.totals.leads +
        ' leads, ' +
        m.totals.minutesUsed +
        ' min, contact ' +
        m.totals.contactRate.toFixed(1) +
        '%)',
    )
  : bad('metrics shape');

/* 5. every automation triggers and reports */
const defs = await api.automations.list();
defs.length === 9
  ? ok(defs.length + ' automations registered')
  : bad('automation count ' + defs.length);
for (const def of defs) {
  const params: Record<string, string | number | boolean> = {};
  def.params.forEach((p) => {
    params[p.name] = p.defaultValue;
  });
  try {
    const run = await api.automations.trigger(def.id, params, { dryRun: def.destructive });
    run.status === 'success' && typeof run.message === 'string'
      ? ok(def.id + ': ' + run.recordsProcessed + ' rec — ' + run.message)
      : bad(def.id + ': unexpected status ' + run.status);
  } catch (e) {
    bad(def.id + ': ' + (e instanceof Error ? e.message : 'threw'));
  }
}

/* 6. dedupe actually removes rows when not a dry run */
const preDedupe = (await api.leads.list({ pageSize: 1 })).total;
const dedupe = await api.automations.trigger('dedupe_leads', {
  strategy: 'keep_newest',
  dryRun: false,
});
const postDedupe = (await api.leads.list({ pageSize: 1 })).total;
dedupe.recordsProcessed > 0 && preDedupe - postDedupe === dedupe.recordsProcessed
  ? ok('dedupe removed ' + dedupe.recordsProcessed + ' (' + preDedupe + ' -> ' + postDedupe + ')')
  : bad(
      'dedupe mismatch (' +
        preDedupe +
        ' -> ' +
        postDedupe +
        ', reported ' +
        dedupe.recordsProcessed +
        ')',
    );

/* 7. run history + failure injection */
const runs = await api.automations.runs(30);
runs.length >= 10 ? ok('run history (' + runs.length + ' entries)') : bad('run history ' + runs.length);
api.setFailureRate(1);
try {
  await api.leads.list({ pageSize: 5 });
  bad('failure injection active');
} catch (e) {
  e instanceof ApiError && e.status === 503 ? ok('failure injection -> 503') : bad('failure injection error');
}
api.setFailureRate(0);

await api.resetData();
const fresh = await api.leads.list({ pageSize: 1 });
fresh.total === 255
  ? ok('resetData restores seed (' + fresh.total + ')')
  : bad('resetData -> ' + fresh.total);

/* 8. calls */
const calls = await api.calls.list({ page: 1, pageSize: 10, sort: 'durationSec', dir: 'desc' });
calls.items.every((c, i) => i === 0 || calls.items[i - 1].durationSec >= c.durationSec)
  ? ok('calls sort desc (' + calls.total + ' total)')
  : bad('calls sort');
const noAnswer = await api.calls.list({ outcome: 'no_answer', pageSize: 5 });
noAnswer.items.every((c) => c.outcome === 'no_answer')
  ? ok('outcome filter (' + noAnswer.total + ')')
  : bad('outcome filter');

console.log(results.join('\n'));
console.log(
  '\n' +
    (results.some((r) => r.startsWith('FAIL')) ? 'RESULT: FAILURES PRESENT' : 'RESULT: ALL PASS'),
);
