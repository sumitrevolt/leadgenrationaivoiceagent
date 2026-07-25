# Skills Parity — Cursor/Composer ↔ Claude Code

> **Goal:** Claude Code is **PRIMARY** for this repo — skills encode Cursor's parallel context-first edge explicitly.
> **Start every code task:** `context-first` → `leadgen-composer` → one domain skill.
> **Project skills:** 208 folders in `.claude/skills/` (single canonical root) + `data/skills_extra/`.

## Canonical skill root (.claude/skills) — Phase 12 consolidation (2026-07-21)

- **Single canonical tracked tree: `.claude/skills/`.** The former `.agents/skills/`
  mirror was a byte-identical duplicate (399 common files, 0 divergent) plus 23 extra
  skills. Those 23 were merged into `.claude/skills/` and the duplicate tree was
  removed via `git rm`. There is now exactly one implementation per skill.
- **No junctions in repository state.** A fresh clone contains plain directories,
  never junctions — the earlier "61 junctions" note described a local workstation
  overlay, not Git state (proven: a fresh checkout reports zero junctions). Do not
  recreate workstation junctions as a repository solution.
- **Safety:** never run `rmtree`/`robocopy /MIR`/recursive filesystem delete against a
  skills tree; use `git rm` on explicit paths (junctions can delete across the link).
  A CI guard (`tests/test_skill_tree_canonical_guard.py`) fails if `.agents/skills`
  reappears, a Dockerfile bakes it, runtime code references it, or a skill id duplicates.
- Runtime `skill_pack.py` loads only `.claude/skills/` (+ `data/skills_extra/`).

## Claude loading protocol (MANDATORY)

1. `CLAUDE.md` auto-loads each turn (lean memory).
2. **Any code/debug/edit** → Read `.claude/skills/context-first/SKILL.md` FIRST.
3. Task match → Read **one** domain `.claude/skills/<name>/SKILL.md`.
4. Ambiguous single decision → `llm-council-decision`.
5. Full advancement / ROI / competitive / moat → `executive-council` (NOT generic audit).
6. Skill missing → `find-skills` → `data/skills_extra/`.
7. **Never** load entire skills folder (token burn).

## P0 — Claude beats Cursor (2026-06-21 update)

| Skill | When |
|-------|------|
| `context-first` | **Every code task — parallel Grep/Read before edit** |
| `leadgen-composer` | Primary brain + task router |
| `verify-ship` | prod_check + deploy gate |
| `production-ready` | launch / readiness / GO certification |
| `duplicate-route-guard` | new FastAPI routes |
| `windows-dev-gotchas` | Windows git/SSH/VPS |
| `product-split-adr` | Marketing vs Voice split |
| `voice-roles` | Swara / Ananya / Riya |
| `executive-council` | ROI roadmap · competitive · moat (Phases 1–6, NOT repo audit) |

## Enterprise Audit Pack (13) — installed 2026-06-27

> Hardening/audit playbooks (`leadgen-*`). Generic enterprise checks + **repo-specific paths/routes/flags baked in** + cross-linked to existing domain skill (duplicate nahi). P1 Marketing first; P2 voice readiness/compliance only. Each returns: scope → evidence → blockers → files → fix-order → tests → rollback → **readiness /100**.

**Run order (P1 first):**

| # | Enterprise skill | Audits | Related existing skill (don't dup) |
|---|------------------|--------|-------------------------------------|
| 1 | `leadgen-revenue-readiness` | P1 sellable path, `/api/activation/readiness` | `production-ready`, `revops` |
| 2 | `leadgen-product-truth` | pricing/plan single-source `packages.py` | `product-split-adr`, `pricing`, `duplicate-route-guard` |
| 3 | `leadgen-customer-journey-e2e` | landing→pay→onboard→output click-through | `onboarding`, `fde-onboard`, `verify-ship` |
| 4 | `leadgen-billing-upi` | manual UPI/approval/invoice/entitlement | `pricing`, `revops` |
| 5 | `leadgen-lead-pipeline-quality` | scrape/dedupe/score/triage, ban-risk | `pipeline-hygiene`, `prospecting` |
| 6 | `leadgen-email-deliverability` | SMTP caps/warmup/fail-fast/opt-out | `cold-email`, `cold-email-craft` |
| 7 | `leadgen-automation-reliability` | Celery durable/DLQ/idempotency/boot-grace | `automation-pipeline`, `automation-flags`, `scheduler-job` |
| 8 | `leadgen-infra-doctor` | VPS Docker/Caddy/PgBouncer/health root-cause | `hostinger-deploy`, `leadgen-ops`, `observability-ops` |
| 9 | `leadgen-observability` | product/revenue/journey signals + Sentry/OTel | `observability-ops`, `genai-observability` |
| 10 | `leadgen-security-rbac` | auth/IDOR/tenant/webhook-sig/secrets/PII | `backend-rbac`, `team-access-ops`, `llm-security` |
| 11 | `leadgen-voice-compliance` | P2 DLT/DND/consent/window gates (gate INTACT) | `voice-agent-kb`, `telephony-engineering`, `voice-roles` |
| 12 | `leadgen-test-guardian` | risk-matched coverage, `prod_check`+`run_tests` | `test-driven-development`, `verify-ship` |
| 13 | `leadgen-repo-learning-governance` | OSS pattern-extract, license-safe, native plan | `memory-vault`, `self-improve-control` |

## Enterprise-Grade SaaS Pack (9) — installed 2026-07-02

> Launch-gate se AAGE ka bar: due-diligence/bade-customer survive karne wale domains jo pehle UNCOVERED the. Master = `enterprise-readiness-audit` (12-domain scored matrix, baaki 8 + audit-pack pe dispatch). Har skill: repo-truth table + workflow + enterprise bar + evidence-mandatory output.

| # | Skill | Covers (pehle gap tha) | Related existing (don't dup) |
|---|-------|------------------------|------------------------------|
| 1 | `enterprise-readiness-audit` | 12-domain matrix + verdict /120 | `production-ready` (launch gate) |
| 2 | `dr-restore-drill` | restore-PROVEN backups, RTO/RPO, VPS rebuild | `leadgen-infra-doctor`, `hostinger-deploy` |
| 3 | `tenant-isolation-audit` | tenant-boundary microscope, Qdrant ns, wrong-tenant tests | `leadgen-security-rbac`, `api-design` |
| 4 | `slo-error-budget` | SLO targets + burn-rate + freeze policy | `observability-ops`, `prod-incident-triage` |
| 5 | `secrets-rotation` | key inventory/cadence/leak-response | `leadgen-security-rbac`, `mcp-engineer` |
| 6 | `data-retention-dpdp` | data-map har store + deletion runbook + 90d purge | `leadgen-voice-compliance`, `cso-audit` |
| 7 | `load-capacity-testing` | measured ceilings + scale triggers | `leadgen-infra-doctor`, `llm-quota-ops` |
| 8 | `db-migration-safety` | expand-contract, PgBouncer, rollback SQL | `supabase-postgres-best-practices`, `verify-ship` |
| 9 | `supply-chain-security` | pip-audit, base-image age, typosquat, Actions pinning | `security-review`, `model-asset-bake` |

## Governance — Agent Harness Standard (Master Blueprint companion)

> Vendor-neutral harness control matrix (C-01..C-15, L1–L5). Scores agent loops; does not invent new STAFF personas.

| Item | Path | Covers | Related existing (don't dup) |
|---|---|---|---|
| Skill | `agent-harness-standard/SKILL.md` (+ `reference.md`) | control matrix, self-cert checklist, maturity ladder | `agent-loop-design`, `leadgen-automation-reliability` |
| Agent | `.claude/agents/harness-conformance-auditor/AGENT.md` | scores one loop C-01..C-15 → L1–L5 | `agent-workflow-auditor` |

## Cursor built-in → Claude repo skill

| Cursor (`~/.cursor/skills-cursor/`) | Claude (repo) | Notes |
|-------------------------------------|---------------|-------|
| *(leadgen-composer)* | `leadgen-composer/` | Primary brain |
| *(parallel index)* | `context-first/` | **NEW** — Cursor default behavior for Claude |
| `automate` | `automate/` | Celery/scheduler |
| `babysit` | `babysit/` | PR merge-ready |
| `canvas` | `canvas/` | Claude = markdown/HTML |
| `create-hook` | `create-hook/` | `.cursor/hooks.json` |
| `create-rule` | `create-rule/` | rules + CLAUDE.md |
| `create-skill` | `create-skill/` | new SKILL.md |
| `create-subagent` | `create-subagent/` | Task tool |
| `loop` | `loop/` | recurring shell |
| `migrate-to-skills` | `migrate-to-skills/` | rules → skills |
| `review` | `review/` | code review |
| `review-bugbot` | `review-bugbot/` | bug-style review |
| `review-security` | `security-review/` | security |
| `shell` | `shell/` | `/shell` command |
| `split-to-prs` | `split-to-prs/` | multi-PR |
| `sdk` | `agent-sdk/` | Agent SDK |
| `statusline` | `statusline/` | Cursor IDE only |
| `update-cursor-settings` | `update-claude-settings/` | CLAUDE.md |
| `update-cli-config` | `update-cli-config/` | CLI config |
| *(gstack design-review)* | `design-review/` | **NEW 2026-06-25** — visual/UI review + AI-slop catch (MIT, ported from garrytan/gstack; no Bun dep, uses Claude Preview tools) |

## Slash commands → skills

| Command | Skill equivalent |
|---------|------------------|
| `/verify` | `verify-ship` (quick) |
| `/ship` | `verify-ship` + `leadgen-ops` |
| `/checkpoint` | `memory-vault` |
| `/learn` | SESSION_LOG append (Edit only) |
| `/compact-check` | `leadgen-start` token rules |
| `/optimize` | growth-optimizer |
| `/test-expand` | `tdd-contract-first` |
| `/council-advancement` | `executive-council` + `docs/EXECUTIVE_ADVANCEMENT_COUNCIL_PROMPT.md` |

## VPS

Skills baked in Docker image (`.claude/skills/` COPY). `data/skills_extra/` bind-mount — git pull live, no rebuild.

## Production truth probe

```text
curl.exe https://leadsgenai.in/api/activation/summary
→ ready_for_first_paid_customer, blocker_count, warns
```

Detail: `production-ready` skill.
