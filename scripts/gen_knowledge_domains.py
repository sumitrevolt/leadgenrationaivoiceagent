#!/usr/bin/env python3
"""Phase 1 — knowledge domain scaffold generator.

Creates the LAYER B Agentic Notebook domain structure under knowledge/.
Deliberately INDEX-ONLY: each domain index points at the authoritative
existing sources (memory/, docs/, code, APIs) instead of duplicating them
(master prompt: "Do not duplicate authoritative docs unnecessarily. Prefer
indexing and normalization.").

Run: python scripts/gen_knowledge_domains.py   (idempotent; refreshes indexes)
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge"

DOMAINS = {
    "00_OWNER_TRUTH": {
        "title": "Owner Truth",
        "desc": "Canonical project truth: prod version, flags, kill switches, revenue, blockers, priorities, decisions, escalation.",
        "sources": [
            "ops/owner_truth.yaml            — MACHINE-READABLE canonical truth (read first)",
            "docs/context/CURRENT_STATE.md   — human narrative current state (auto-loaded)",
            "docs/context/ACTIVE_WORK.md     — active workstreams",
            "HERMES_AGENT_ROSTER.yaml        — 31 agents -> 9 Hermes bots",
            "_tasks_sync.json                — Kanban/task state (REV-xxx)",
            "memory/decisions.md             — append-only ADR archive",
        ],
        "truth_routes": [
            "GET https://leadsgenai.in/health        -> .version == repo SHA",
            "GET /api/growth/infra/flags             -> runtime feature flags",
            "GET /api/ops/revenue-summary            -> revenue truth (MCP, admin+Bearer)",
            "GET /api/ops/hotqueue                   -> hot leads",
        ],
    },
    "01_ARCHITECTURE": {
        "title": "Architecture",
        "desc": "System architecture: services, APIs, DBs, queues, Redis, providers, deployment, auth, tenant isolation.",
        "sources": [
            "CLAUDE.md ## 2 ARCHITECTURE MAP   — canonical stack map (auto-loaded)",
            "knowledge/architecture/agent-os.md",
            "knowledge/architecture/knowledge-stack.md",
            "knowledge/architecture/omniroute.md",
            "knowledge/architecture/tenant-isolation.md",
            "docs/ARCHITECTURE.md / docs/ARCHITECTURE_BLUEPRINT.md",
            "deploy/ + docker-compose.vps.yml  — container topology",
            "app/ (graphify-out/graph.json)    — code knowledge graph",
            "memory/integrations.md            — external deps, rate limits",
        ],
    },
    "02_ENGINEERING": {
        "title": "Engineering",
        "desc": "Coding standards, testing protocol, CI/CD, merge policy, rollback, observability, change management.",
        "sources": [
            "CLAUDE.md ## 3-6 (COMMANDS/CODE STANDARDS/TESTING PROTOCOL) — canonical",
            "docs/AGENT_WORK_RULES.md          — 10 anti-mistake rules",
            "docs/LOOP_ENGINEER.md             — loop-engineer mode spec",
            "docs/context/AI_OPERATING_PROTOCOL.md",
            "docs/ADR-104_DEPLOY_RUNBOOK.md",
            "scripts/prod_check.py             — verify gate",
            "scripts/check_secrets.py          — secrets scan",
            "progress.md                       — loop ledger",
        ],
    },
    "03_SALES_REVENUE": {
        "title": "Sales & Revenue",
        "desc": "ICP, lead sourcing, qualification, outreach (WA/email/call), follow-ups, payments, close workflow, CRM, revenue verification.",
        "sources": [
            "docs/GTM_PILOT_PLAYBOOK.md",
            "docs/Agentic_Customer_Acquisition_Playbook.md",
            "docs/LEAD_MAGNET_PLAYBOOK.md",
            "docs/playbooks/Business_Playbook_Hinglish.md",
            "DAY_0_REVENUE_BASELINE.md / 7_DAY_REVENUE_PLAN.md / REVENUE_BLOCKERS.md",
            "ops/owner_truth.yaml (revenue section) — canonical revenue truth",
            "app/billing/packages.py            — pricing single source",
            "memory/decisions.md                — billing/UPI decisions",
            "data/hot_queue_*.csv/md            — daily hot-lead packs",
            "docs/runbooks/RUNBOOK_DUPLICATE_OUTREACH.md / RUNBOOK_BILLING_INCIDENT.md",
        ],
        "canonical_revenue_rule": "Revenue = ONLY owner_confirmed_upi + invoice/ledger id. Lead/proposal/verbal yes/unpaid invoice != revenue.",
    },
    "04_SWARA_VOICE": {
        "title": "Swara / Voice",
        "desc": "Voice AI: architecture, telephony, call flow, prompts, states, failure codes, retries, compliance, QA, incidents.",
        "sources": [
            "CLAUDE.md ## 2 (voice stack) + landmines — canonical",
            "app/voice_agent/ + app/telephony/  — code",
            "knowledge/architecture/agent-os.md (Swara section, if any)",
            "voice_stack/                       — voice assets",
            "memory/incidents.md                — voice outage postmortems (872-event lesson)",
            "swara_enterprise.patch             — Voice AI pitch option",
            "docs/runbooks/RUNBOOK_PROVIDER_OUTAGE.md",
            "scripts/agent_tester.py            — voice scorecard",
            "FREEZE: Swara/voice code = FROZEN (edit mana) — read-only domain",
        ],
    },
    "05_MARKETING_VIDEO": {
        "title": "Marketing & Video",
        "desc": "Video generation, content pipeline, approvals, social publishing, asset generation, customer templates, brand constraints.",
        "sources": [
            "video_renderer/                    — video pipeline",
            "docs/runbooks/RUNBOOK_DAILY_VIDEO.md",
            "ADRs: ADR-142 VIDEO DECISIONS (reject terminal / only Changes revises)",
            "docs/brand/ (brand constraints)",
            "frontend/ marketing pages           — 28-tab marketing.html",
            "memory/backlog.md                  — parked video ideas",
            "Pollinations (AI images/video)     — provider",
        ],
    },
    "06_CUSTOMER_SUCCESS": {
        "title": "Customer Success",
        "desc": "Onboarding, activation, delivery, feedback, escalation, renewal, customer isolation, support.",
        "sources": [
            "knowledge/operations/customer-onboarding.md",
            "docs/CLIENT_ONBOARDING_KIT.md",
            "docs/CUSTOMER_DELIVERY_AUTOMATION_2026_07_05.md",
            "CLAUDE.md ## 5 (tenant isolation invariant)",
            "memory/incidents.md                — Jiya delivery lessons",
        ],
    },
    "07_PRODUCTION_OPERATIONS": {
        "title": "Production Operations",
        "desc": "Deployments, VPS, containers, health checks, backups, DR, monitoring, release procedures.",
        "sources": [
            "CLAUDE.md ## 3 (BUILD+DEPLOY canonical) — deploy_vps.sh ONLY",
            "docs/ADR-104_DEPLOY_RUNBOOK.md",
            "knowledge/operations/deployment-runbook.md",
            "docs/DISASTER_RECOVERY.md",
            "docs/omniroute/OPERATIONS_RUNBOOK.md",
            "docs/COMPOSE_GUIDE.md",
            "deploy/ (compose + scripts)",
            "monitoring/ (Prometheus/Grafana/Alertmanager/Loki/Tempo obs stack)",
            "scripts/vps_selfheal.sh            — */10 self-heal cron",
            "memory/playbooks.md               — deploy/rollback/rotate procedures",
        ],
    },
    "08_INCIDENTS_RUNBOOKS": {
        "title": "Incidents & Runbooks",
        "desc": "Incident taxonomy, previous incidents, symptoms, root causes, fixes, validation, rollback, prevention.",
        "sources": [
            "memory/incidents.md               — postmortem archive (authoritative)",
            "docs/runbooks/                    — 9+ runbooks (RB-xxx)",
            "docs/OPERATIONAL_RUNBOOKS.md      — RB-001..013 quick reference",
            "docs/runbooks/RUNBOOK_BILLING_INCIDENT.md",
            "ops/runbooks/                     — normalized registry (THIS upgrade)",
            "docs/SECURITY_PLAYBOOK.md",
        ],
    },
    "09_PROVIDERS_APIS_MCP": {
        "title": "Providers / APIs / MCP",
        "desc": "Provider inventory, credential references, API contracts, quotas, limits, auth, costs, fallbacks, MCP capabilities.",
        "sources": [
            "memory/integrations.md            — per-provider purpose/limits/failure modes (authoritative)",
            "ops/owner_truth.yaml (providers section)",
            "docs/API.md                        — route inventory (~1295+ routes)",
            "docs/CONTEXT_MCP.md               — MCP wiring",
            "knowledge/architecture/omniroute.md",
            ".mcp.json                         — graphify-mcp + leadgen MCP (54 tools)",
            "SECRET_REF convention: secrets NEVER in docs — env vars only (.env)",
        ],
    },
    "10_EXPERIMENTS_LESSONS": {
        "title": "Experiments & Lessons",
        "desc": "Experiments, hypotheses, results, failed approaches, benchmarks, lessons, accepted/rejected decisions.",
        "sources": [
            "memory/backlog.md                 — parked ideas with why",
            "memory/decisions.md               — ADR archive (append-only)",
            "evals/ + eval results             — benchmarks",
            "docs/ADVANCEMENT_ROADMAP_2026.md",
            "knowledge/decisions/              — ADR summaries (adr-119, index)",
            "docs/archived/                    — rejected/rolled-back artifacts",
        ],
    },
}

INDEX_TEMPLATE = """# {title} — Knowledge Domain Index

> LAYER B Agentic Notebook. This index is a **normalized pointer layer**: it maps
> the domain to authoritative existing sources. Live truth lives in code/APIs/DB
> (see Owner Truth); deep archives live in `memory/`; dated docs in `docs/`.
> Updated: {updated}

## What this domain covers
{desc}

## Authoritative sources (read these, not duplicates)
{sources}

## Live truth routes (verify, don't trust chat claims)
{truth_routes}

## Recall rules
- Secrets NEVER live in knowledge files — reference env var NAMES only (SECRET_REF).
- If code and this index disagree, **code wins** — then fix this index.
- Freshness: `last_verified_at` should be bumped whenever this domain is re-verified.
"""


def fmt_list(items):
    return "\n".join(f"- {i}" for i in items)


def main():
    created = []
    for name, meta in DOMAINS.items():
        d = KB / name
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch(exist_ok=True)
        index = d / "index.md"
        content = INDEX_TEMPLATE.format(
            title=meta["title"],
            desc=meta["desc"],
            updated="2026-08-28",
            sources=fmt_list(meta["sources"]),
            truth_routes=fmt_list(meta.get("truth_routes", ["(none — see 00_OWNER_TRUTH)"])),
        )
        if index.exists() and index.read_text(encoding="utf-8") == content:
            created.append(("unchanged", str(index.relative_to(ROOT))))
        else:
            index.write_text(content, encoding="utf-8")
            created.append(("written", str(index.relative_to(ROOT))))
    # Top-level knowledge index refresh
    top = KB / "index.md"
    if top.exists():
        created.append(("existing", "knowledge/index.md (OKF bundle — left intact)"))
    print(f"DOMAINS: {len(DOMAINS)}")
    for kind, p in created:
        print(f"  [{kind}] {p}")


if __name__ == "__main__":
    main()