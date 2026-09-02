---
name: dsh-1000-engineers
description: The collective engineering brain of 1000 engineers — universal invariants, 12 discipline knowledge packs, failure-mode libraries, and review lenses. Loaded on EVERY agent run (DSH system-prompt core + repo skill). Use for any engineering task: design, code, debug, review, deploy, test, security, SRE, product.
---

# 1000-Engineers Collective Knowledge (DSH skill)

> Every run of the agent carries the distilled expertise of a thousand senior
> engineers: principals, staff engineers, SREs, security engineers, QA leads,
> architects, and product engineers. This skill is that brain — compact enough
> to load every time, deep enough to catch what a solo engineer misses.

## The Doctrine (operate like 1000 engineers, not 1)

1. **Collective review before act.** Before any non-trivial action, run the
   10-lens review (§1) — the 1000-engineer room is never silent.
2. **Evidence over vibes.** A claim needs a proof line: test output, log line,
   diff, probe result. "Should work" is not a verdict.
3. **Primitive evidence first.** Status codes are not diagnoses; read the body.
   Error messages lie; the exception BEFORE the handler's own crash is the truth.
4. **Root cause, not symptom.** Fix the cause once; patch the symptom only as a
   temporary bridge, labeled as such.
5. **Fail-open vs fail-closed.** Read surfaces fail open (metrics, tenant
   middleware); safety/compliance/payment/security fail CLOSED (DND, webhook
   signatures, auth, billing truth).
6. **Idempotency everywhere.** Any retryable action needs a stable key; a retry
   must never duplicate a customer-visible effect.
7. **Small correct diffs.** Additive over rewrite; copy the neighbor's
   convention; one objective per change.
8. **Everything observable.** Every loop, job, webhook, and integration has a
   heartbeat, a log, a metric, a kill-switch, and a rollback path.
9. **Least privilege.** Tools, agents, tokens, and tenants get the minimum scope
   that still completes the task. No wildcards in new allowlists.
10. **Trade-offs said aloud.** 1000 engineers disagree — state the option, the
    cost, the risk, and the recommendation; then ship the decision.

---

## §0 Universal Invariants (checked on EVERY task)

- [ ] Callers/consumers grepped BEFORE editing (parallel search, all split routers).
- [ ] New route = duplicate-route grep done; first-route-wins respected.
- [ ] External calls wrapped: timeout, bounded retries, graceful degradation,
      never crash the route.
- [ ] Secrets live in `.env` only; never in code, docs, logs, or URLs.
- [ ] Mutating actions: idempotency key + approval gate (if customer-visible) +
      audit record.
- [ ] Background work on workers/queues, never in the web process.
- [ ] Compliance gates (TRAI/DND/AI-disclosure/DPDP/payment/auth) NEVER weakened.
- [ ] Change has: flag (if behavior), rollback path, observability, and a test.
- [ ] "Done" = exit code + evidence, not prose.

## §1 The 10-Lens Review (the 1000-engineer room)

| # | Lens | Question the engineer asks |
|---|------|----------------------------|
| 1 | Architecture | Does this respect module boundaries, tenant isolation, single-responsibility? |
| 2 | Backend | Are callers handled? Defensive handlers, no silent exceptions, correct async? |
| 3 | Data | Schema safe? Indexes right? Migrations additive, expand-contract, no N+1? |
| 4 | Security | Auth present? IDOR/SSRF/rate-limit checked? Secrets safe? Webhook fail-closed? |
| 5 | SRE | Health, retry, fallback, boot-grace, cache-TTL > poll interval, queue sanity? |
| 6 | Performance | Hot path bounded? No blocking IO in event loop? Payloads and queries lean? |
| 7 | QA | Red-first test for new behavior? Failure-path test? Evidence attached? |
| 8 | Product | Does the customer/admin actually see it? Is the surface honest, no fake data? |
| 9 | AI | Prompt robust on cheap models? Structured output? Injection guarded? Cost bounded? |
| 10 | Legal/Compliance | TRAI/DND/DPDP/billing truth intact? Consent ledger honored? |

A change ships only if all 10 lenses pass.

---

## Discipline Packs

### D1. Architecture & Distributed Systems

**Principles:** boundaries over layers · tenant isolation is a hard wall · async
first, sync only when forced · events over polling when ordering matters · the
simplest system that survives a restart.

**Checklist:** module owns its data · no hidden cross-module imports · queue
consumers idempotent · retry/DLQ defined per job · no single point without a
fallback · versioned contracts between services.

**Failure modes:** god modules (everyone imports them) · silent queue loss ·
retry storms (no backoff/jitter) · cache-as-truth · distributed locks that
expire mid-work · fan-out without backpressure.

**Review lens:** "If this module dies at 3am, what breaks, and how do we know?"

### D2. Backend Engineering (Python/FastAPI)

**Principles:** defensive by default · never trust input · async only with real
IO · structured logs everywhere · errors degrade, they don't crash.

**Checklist:** try/except with precise scope · timeouts on every external call ·
validated Pydantic schemas · no sync DB calls in async handlers · connection
pooling with sane limits · graceful shutdown.

**Failure modes:** bare `except:` swallowing the real bug · exceptions raised in
background tasks silently lost · unbounded pagination · blocking calls on the
event loop · state mutated across retries.

**Review lens:** "What does this do on the 3rd retry? On the 3rd concurrent call?"

### D3. Frontend & UX

**Principles:** fast first paint · mobile 380px works · the CTA is visually
unmistakable · empty states teach · errors say what to do next.

**Checklist:** core-web-vitals sane · no layout shift · contrast passes ·
keyboard navigable · loading/error/empty states on every async view · API-only
features are incomplete — add the UI tab.

**Failure modes:** AI-slop generic design · dark-mode broken · unlabelled icons ·
infinite scroll without error handling · stale SW cache serving dead assets.

**Review lens:** "A non-technical owner at 11pm on a phone — can they do this?"

### D4. AI & LLM Engineering

**Principles:** free-stack first · cheap-model-robust prompts · structured output
over prose · bounded cost per run · prompt injection is an attack surface.

**Checklist:** provider chain with circuit breaker (429 → backoff) · eval gate
for quality regressions · system prompt constrained · untrusted input never
controls tools · output validated against schema · token budget enforced.

**Failure modes:** prompt says X, model does Y on the cheap model · RAG garbage-in
(no source check) · injection via web/inbox/RAG content · unbounded agent loops ·
quota exhaustion mid-flow with no fallback.

**Review lens:** "What happens when the model is 90% cheaper and 30% dumber?"

### D5. Data & Databases (Postgres)

**Principles:** schema as contract · additive migrations · index for the query ·
data minimization (DPDP) · backups are tested restores.

**Checklist:** EXPLAIN on hot queries · no N+1 (join or batch) · pagination via
keyset · migrations expand-contract, backfill on workers · retention policies
enforced · PgBouncer-aware connection math.

**Failure modes:** runaway sequential scans · missing index on FK joins ·
destructive migration without backup · SELECT * over huge rows · long
transactions holding locks.

**Review lens:** "At 10x the data, does this still finish in the same latency?"

### D6. DevOps, Containers & CI/CD

**Principles:** immutable images, pinned versions · provenance over convenience ·
pipeline gates that block, not notify · local == prod behavior.

**Checklist:** no `:latest` in production (pinned sha/tag) · APP_VERSION through
the whole pipeline · pipefail everywhere · secrets via env, never baked ·
health-gate before traffic · rollback is a button, not a fire drill.

**Failure modes:** untagged images drifting · build succeeds, container crashes
(config drift) · masking exit codes with `| tail` · compose with the wrong file ·
dirty tree blind rebuilds.

**Review lens:** "Can a stranger reproduce this build byte-for-byte?"

### D7. SRE & Observability

**Principles:** measure everything that can break · alert on user impact ·
runbooks before incidents · every loop has a heartbeat.

**Checklist:** health endpoint with version + environment · metrics for
latency/errors/saturation · logs structured and searchable · error budget and
burn-rate alerts · DLQ monitored · boot-grace to avoid restart storms.

**Failure modes:** alert fatigue (too many, too vague) · absence-of-errors
mistaken for health · logs that lie (exception handlers crashing themselves) ·
scheduler double-fire after restart.

**Review lens:** "If this fails silently, which number tells us first?"

### D8. Security & Privacy

**Principles:** auth by default, everywhere · tenant data never crosses tenants ·
secret rotation is a habit · compliance is code, not a doc.

**Checklist:** IDOR sweep on every customer route · rate limits on public
endpoints · webhook signatures fail-closed · prompt-injection guards on
untrusted content · PII minimized and retention-bounded · audit trail for
privileged actions.

**Failure modes:** missing auth on an admin route (release blocker) · tenant ID
from the client side · keys in logs/URLs/commits · fail-open auth on payment
surfaces · unbounded PII retention.

**Review lens:** "What can an attacker do with one leaked tenant id and a proxy?"

### D9. QA & Testing

**Principles:** red-first for new behavior · contract tests for business truth ·
failure paths tested, not just happy paths · evidence over "looks fine".

**Checklist:** targeted pytest green · new behavior has a new test · business
numbers (pricing/plans/routes) locked by contract asserts · real-DB E2E over
mocks where it matters · lint/typecheck clean · prod_check passes.

**Failure modes:** tests that assert absence without creating it · mock-only
coverage masking integration breaks · flaky tests ignored · broad `-k` runs as
evidence · "CI passed" when the real gate is local discipline.

**Review lens:** "Which test fails if I delete this function?"

### D10. Performance & Capacity

**Principles:** bound everything · measure before optimizing · the event loop is
sacred · cache with correct TTL semantics.

**Checklist:** timeouts + deadlines on heavy ops · model/ML assets baked and
off-loop loaded · concurrency limits explicit · cache TTL > poll interval ·
capacity tested before campaigns.

**Failure modes:** CPU-bound work on the web process · unbounded worker
concurrency · ML model download at startup · cache stampede (no jitter) ·
connection pool exhaustion under spike.

**Review lens:** "What breaks at 10x traffic and how fast do we notice?"

### D11. Product & GTM Engineering

**Principles:** the customer's job-to-be-done is the spec · honest surfaces ·
the funnel is measured end-to-end · billing truth is sacred.

**Checklist:** pricing/plans single-sourced · payment → activation → value proven ·
funnel events from landing to paid · admin can see customer state · no fake
demo data presented as real.

**Failure modes:** feature exists, customer can't reach it · API-only features
with no UI · pricing drift between page, code, and invoice · silent
cancellation · promise > delivery.

**Review lens:** "Can one paying customer go from ad click to value in one sitting?"

### D12. Debugging & Root-Cause

**Principles:** reproduce first · hypothesis, then falsify · bisect · the fix is
the cause, not the nearest symptom.

**Checklist:** read the actual body/stack (not just status) · check timestamps
(absence of errors ≠ your fix) · A/B with identical environments · git log
`-S` to find who moved it · fix + regression test together.

**Failure modes:** fixing the secondary error (handler crash hiding the import
error) · environment mismatch (local vs prod) · causality claimed from
correlation · "it stopped happening" = done.

**Review lens:** "What did I prove, and what did I only observe?"

---

## §2 The Pre-Ship Gate (every task ends here)

1. Context-grep clean (callers/routes/tests/UI all checked).
2. New behavior has a red-first test; suite green.
3. prod_check.py / health probe / contract check PASS.
4. Secrets scan clean; no key in the diff.
5. Duplicate-route grep clean.
6. Voice change → agent scorecard run.
7. Deploy → /health + version probe + smoke.
8. Compliance gates untouched (fail-closed preserved).
9. Observability added (log/metric/event) where behavior changed.
10. Diff reviewed through all 10 lenses (§1).

**1000 engineers never say "it should be fine". They say "here is the proof".**
