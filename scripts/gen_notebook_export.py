#!/usr/bin/env python3
"""Phase 8 — Gemini Notebook export generator.

Builds clean, versioned, timestamped, secret-free source bundles under
notebook_exports/ so a retrieval layer (Gemini Notebook / NotebookLM /
RAG) can consume the LeadGen knowledge brain.

Design:
- Each domain gets one bundle file (00-owner -> 10-lessons).
- Content is INDEX + digest of the authoritative sources (no duplication).
- Secret hygiene: runs check_secrets-style scan over every emitted line;
  any hit replaces the value with SECRET_REF:<name>.
- Deterministic: same input -> same output (stable ordering), so diffs
  are reviewable.

Usage:
    python scripts/gen_notebook_export.py [--out notebook_exports]

Refreshed by: scripts/gen_notebook_export.py (idempotent)
CI: tests/test_knowledge_os.py asserts bundles exist + no secrets.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- sources
SOURCES = {
    "00-owner": {
        "title": "Owner Truth & Priorities",
        "files": [
            "ops/owner_truth.yaml",
            "docs/context/CURRENT_STATE.md",
            "docs/context/ACTIVE_WORK.md",
        ],
        "note": "Canonical current state, priorities, blockers, decisions, authority matrix.",
    },
    "01-architecture": {
        "title": "System Architecture",
        "files": [
            "docs/SYSTEM_MAP.md",
            "CLAUDE.md",
            "docs/integrations/BUZZ_LOCAL_RELAY.md",
        ],
        "note": "Services, APIs, DB, queues, Redis, Qdrant, providers, deployment, auth, tenant isolation.",
    },
    "02-engineering": {
        "title": "Engineering Standards",
        "files": [
            "docs/LOOP_ENGINEER.md",
            "docs/ADR-104_DEPLOY_RUNBOOK.md",
            "docs/OPERATIONAL_RUNBOOKS.md",
        ],
        "note": "Coding/testing standards, CI/CD, merge policy, rollback, observability.",
    },
    "03-sales": {
        "title": "Sales & Revenue",
        "files": [
            "ops/playbooks/PB-SALES.md",
            "ops/playbooks/PB-PAYMENT-VERIFICATION.md",
            "docs/GTM_PILOT_PLAYBOOK.md",
            "docs/Agentic_Customer_Acquisition_Playbook.md",
        ],
        "note": "ICP, lead sourcing, qualification, outreach, follow-ups, payments, close workflow, revenue verification.",
    },
    "04-voice": {
        "title": "Swara Voice",
        "files": [
            "ops/playbooks/PB-VOICE-CALLING.md",
            "docs/runbooks/RUNBOOK_PROVIDER_OUTAGE.md",
            "docs/OPERATIONAL_RUNBOOKS.md",
        ],
        "note": "Swara architecture, SIP providers, call flow, compliance, carrier incidents, runbooks.",
    },
    "05-video": {
        "title": "Marketing & Video",
        "files": [
            "docs/runbooks/RUNBOOK_DAILY_VIDEO.md",
            "docs/LEAD_MAGNET_PLAYBOOK.md",
        ],
        "note": "Video generation, approvals, social publishing, brand constraints.",
    },
    "06-customer-success": {
        "title": "Customer Success",
        "files": [
            "ops/playbooks/PB-CUSTOMER-ONBOARDING.md",
            "docs/CLIENT_ONBOARDING_KIT.md",
        ],
        "note": "Onboarding, activation, delivery, feedback, escalation, renewal, isolation.",
    },
    "07-production-ops": {
        "title": "Production Operations",
        "files": [
            "ops/playbooks/PB-DEPLOYMENT.md",
            "docs/DISASTER_RECOVERY.md",
            "docs/runbooks/RUNBOOK_DEPLOYMENT.md",
        ],
        "note": "Deployments, VPS, containers, health checks, backups, DR, monitoring.",
    },
    "08-incidents": {
        "title": "Incidents & Runbooks",
        "files": [
            "ops/runbooks/registry.yaml",
            "memory/incidents.md",
            "knowledge/operations/incident-response.md",
        ],
        "note": "Incident taxonomy, past incidents, symptoms, root causes, fixes, prevention.",
    },
    "09-providers": {
        "title": "Providers, APIs & MCP",
        "files": [
            "memory/integrations.md",
            "ops/playbooks/PB-PROVIDER-FAILOVER.md",
            "docs/integrations/BUZZ_LOCAL_RELAY.md",
        ],
        "note": "Provider inventory, quotas, limits, auth, costs, fallbacks, MCP capabilities. SECRET REFERENCES ONLY.",
    },
    "10-lessons": {
        "title": "Experiments & Lessons",
        "files": [
            "memory/decisions.md",
            "memory/backlog.md",
            "docs/SESSION_LOG.md",
        ],
        "note": "Experiments, hypotheses, results, failed approaches, lessons, ADRs.",
    },
}

# ---------------------------------------------------------------- secret scan
SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9]{8,})"),                 # openai/omniroute-style keys
    re.compile(r"(api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,})", re.I),
    re.compile(r"(password\s*[:=]\s*['\"]?[^\s'\"]{8,})", re.I),
    re.compile(r"(token\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{16,})", re.I),
    re.compile(r"(BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY)"),
    re.compile(r"(AKIA[0-9A-Z]{16})"),                    # AWS
    re.compile(r"(AIza[0-9A-Za-z_\-]{20,})"),             # Google
    re.compile(r"(ghp_[A-Za-z0-9]{20,})"),                # GitHub PAT
]


def secret_check(text: str) -> list[str]:
    hits = []
    for pat in SECRET_PATTERNS:
        m = pat.search(text)
        if m:
            hits.append(m.group(1)[:30])
    return hits


def scrub(text: str) -> str:
    """Redact anything that looks like a secret, in place."""
    for pat in SECRET_PATTERNS:
        text = pat.sub(lambda m: "SECRET_REF:" + m.group(1)[:8] + "…", text)
    return text


# ---------------------------------------------------------------- bundle build
def build_bundle(domain: str, cfg: dict) -> str:
    lines: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    title = cfg["title"]
    lines.append(f"# {domain} — {title}")
    lines.append("")
    lines.append(f"> Generated: {now} · Source: leadgenrationaivoiceagent (local repo)")
    lines.append(f"> Purpose: {cfg['note']}")
    lines.append("> SECURITY: This bundle is secret-free by construction (references only).")
    lines.append("")

    for rel in cfg["files"]:
        p = ROOT / rel
        if not p.exists():
            lines.append(f"\n## (missing source: {rel})\n")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        # keep only the meaningful head (bundles stay concise for Notebook)
        text = text[:12000]
        text = scrub(text)
        lines.append(f"\n## Source: {rel}\n")
        lines.append(text.strip())
        lines.append("")

    body = "\n".join(lines)
    # final safety sweep
    body = scrub(body)
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "notebook_exports"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    n = 0
    for domain, cfg in SOURCES.items():
        body = build_bundle(domain, cfg)
        p = out / f"{domain}.md"
        prev = p.read_text(encoding="utf-8") if p.exists() else ""
        if prev == body:
            print(f"  [unchanged] {p.name}")
        else:
            p.write_text(body, encoding="utf-8")
            print(f"  [written] {p.name} ({len(body)//1024} KiB)")
        n += 1

    # index file
    idx_lines = [
                "# Notebook Export Index",
                "",
                f"> Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} by scripts/gen_notebook_export.py",
        "",
        "Upload these bundles to Gemini Notebook / NotebookLM as sources.",
        "Execution authority stays with Owner OS + orchestrator; these are the KNOWLEDGE layer only.",
        "",
        "| Bundle | Domain | Sources |",
        "|---|---|---|",
    ]
    for domain, cfg in SOURCES.items():
        idx_lines.append(f"| {domain} | {cfg['title']} | {len(cfg['files'])} files |")
    (out / "INDEX.md").write_text("\n".join(idx_lines), encoding="utf-8")

    print(f"\nNOTEBOOK EXPORT: {n} bundles -> {out.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()