---
name: thousand-engineers
description: The 1000-engineers collective engineering brain — universal invariants, 10-lens review, 12 discipline knowledge packs (architecture, backend, frontend, AI/LLM, data, DevOps, SRE, security, QA, performance, product, debugging). Use when designing, building, debugging, reviewing, or shipping ANY code change. MANDATORY on EVERY task: load before design/code/debug/review/deploy/test. Canonical knowledge = deploy/dsh/skills/1000-engineers.md (DSH skill).
---

# Thousand Engineers — Collective Engineering Brain (LeadGen)

> **Har task pe load karo.** This skill is the distilled expertise of 1000 senior
> engineers — principals, staff engineers, SREs, security, QA leads, architects.
> Canonical full knowledge: `deploy/dsh/skills/1000-engineers.md` (same content is
> injected into the DeepSeek Harness system-prompt via `deploy/dsh/cordis.yml`).
> Here = lean operating core; deep packs = canonical file.

## Doctrine (10 rules)

1. **Evidence over vibes** — claim = proof line (test output, log, diff, probe).
2. **Primitive evidence first** — read bodies/stacks, not status codes; the
   exception BEFORE the handler's own crash is the truth.
3. **Root cause, not symptom** — fix the cause once; label bridges.
4. **Fail-open reads, fail-CLOSED safety** — DND/webhook/auth/billing gates never weakened.
5. **Idempotency** — retries never duplicate customer-visible effects.
6. **Least privilege** — minimum scope; no wildcards in new allowlists.
7. **Everything observable** — heartbeat, log, metric, kill-switch, rollback.
8. **Trade-offs said aloud** — then ship the decision.
9. **Small correct diffs** — additive, copy neighbor convention, one objective.
10. **"Done" = exit code + evidence, not prose.**

## The 10-Lens Review (every change passes all)

Architecture (boundaries/tenant-isolation) · Backend (callers, defensive, async) ·
Data (schema/indexes/migrations) · Security (auth/IDOR/SSRF/secrets/fail-closed) ·
SRE (health/retry/fallback/boot-grace) · Performance (hot path/bounded) ·
QA (red-first test + failure-path) · Product (customer/admin sees it, honest) ·
AI (cheap-model-robust, structured, injection-guarded, cost-bounded) ·
Compliance (TRAI/DND/DPDP/billing truth intact).

## Always-on gates

- Context-grep FIRST (callers/routes/tests/UI) — parallel, before any edit.
- Duplicate-route grep on every new route (first-route-wins).
- External calls: timeout + bounded retries + graceful degradation.
- Secrets: `.env` only; never in code/docs/logs/URLs.
- Background work on workers, never web process.
- New behavior = new test; contract tests for pricing/plans/routes.
- Voice/telephony change = voice scorecard (repo-root `agent_tester.py`) + compliance gates.
- Local evidence: `python .claude/skills/thousand-engineers/scripts/preflight_gate.py --paths <changed files> --pytest <target tests>` → PASS/FAIL lines per gate.

## Task → Discipline routing (load the pack from canonical file)

| Task type | Packs |
|-----------|-------|
| API/backend change | D2 + D0 + D5 |
| Architecture/module design | D1 + D0 |
| Frontend/UI | D3 |
| LLM/agent/prompt work | D4 + D9 |
| DB/migration | D5 |
| Deploy/CI/Docker | D6 + D7 |
| Monitoring/alerting | D7 |
| Security/compliance review | D8 + D0 |
| Test writing | D9 |
| Performance work | D10 |
| Pricing/product/funnel | D11 |
| Bug/incident | D12 + D2 |

Deep checklists, failure-mode libraries, and review lenses for each pack:
`deploy/dsh/skills/1000-engineers.md` → Discipline Packs D1–D12 + §0 + §2.

## Pre-ship gate (every task)

grep clean → test green → prod_check PASS → secrets scan clean → duplicate-route
clean → (voice: scorecard) → deploy + /health probe → compliance untouched →
observability added → 10-lens diff review. **"Here is the proof" — kabhi "should
be fine" nahi.**
