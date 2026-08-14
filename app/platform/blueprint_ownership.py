"""blueprint_ownership.py — reviewed, evidence-backed domain ownership rules.

This is NOT a "package prefix equals domain" heuristic. Every prefix below was
opened and read file-by-file; packages that turned out to mix domains are
either carved up with explicit ``exclude_prefixes`` / ``exclude_stems`` or
REJECTED outright (see ``REJECTED_ROOTS``).

Ownership is only ONE signal. It can never produce HIGH confidence on its own —
``scripts/blueprint_derive.py`` still requires independent corroboration, and
critical domains require two non-AST signals. A directory or file name is never
sufficient evidence.
"""

from __future__ import annotations

from typing import Any

# Packages deliberately NOT owned by any single domain. Assigning these
# wholesale is what produced the false mappings we now regression-test
# (admin_ui -> public_landing, celery -> app_fastapi, brand_frames ->
# public_landing).
REJECTED_ROOTS: dict[str, str] = {
    "app/api/": "113 modules spanning every domain (routers for billing, voice, "
    "growth, admin, customer, marketing) — shared HTTP surface.",
    "app/platform/": "160 modules: scheduler, team, owner_os, delivery, tenancy, "
    "agent runtime — the widest shared package in the repo.",
    "app/models/": "shared SQLAlchemy models used by every domain.",
    "app/utils/": "logging/helpers used everywhere.",
    "app/middleware/": "cross-cutting request middleware.",
    "app/integrations/": "mixed: third-party connectors AND a nested Owner-OS "
    "subtree (owner_os_adapter, harness_commands, policies, "
    "auth, audit) — carve out by exact file instead.",
    "app/tasks/": "Celery task modules whose business domains differ per file "
    "(calling, video_jobs, scraping, reporting).",
    "app/agents/": "agent runtime plus growth/sales optimisers — needs per-file "
    "review before any wholesale claim.",
    "app/ml/": "shared model training/serving utilities.",
    "app/llm/": "shared provider plumbing.",
}


DOMAIN_OWNERSHIP_RULES: dict[str, dict[str, Any]] = {
    "voice_telephony": {
        "include_prefixes": ["app/voice_agent/", "app/telephony/"],
        # KB/RAG lives inside voice_agent but is its own domain; compliance and
        # consent inside telephony belong to security_compliance.
        "exclude_prefixes": [],
        "exclude_stems": [
            "graph_rag",
            "knowledge_base",
            "kb_loader",
            "kb_readiness",
            "consent_ledger",
            "compliance",
            "campaign_compliance",
            "compliance_audit_logger",
            "observability",
        ],
        "exact_files": [],
        "evidence": [
            "app/voice_agent/ read: 63 modules, all STT/TTS/dialogue/call-flow "
            "except the KB/RAG and observability modules excluded above.",
            "app/telephony/ read: 23 modules, all SIP/provider/call-state except "
            "the compliance/consent modules excluded above.",
        ],
        "critical": True,
        "requires_corroboration": True,
    },
    "security_compliance": {
        "include_prefixes": ["app/security/"],
        "exclude_prefixes": [],
        "exclude_stems": [],
        # carved out of app/telephony/ by review, not by prefix
        "exact_files": [
            "app/telephony/consent_ledger.py",
            "app/telephony/compliance.py",
            "app/telephony/campaign_compliance.py",
            "app/telephony/compliance_audit_logger.py",
            "app/telephony/dial_gate.py",
        ],
        "evidence": [
            "DND/consent/compliance gates are §5 invariants and are audited "
            "independently of the voice runtime that calls them.",
        ],
        "critical": True,
        "requires_corroboration": True,
    },
    "kb_rag": {
        "include_prefixes": [],
        "exclude_prefixes": [],
        "exclude_stems": [],
        "exact_files": [
            "app/voice_agent/graph_rag.py",
            "app/voice_agent/knowledge_base.py",
            "app/voice_agent/kb_loader.py",
            "app/voice_agent/kb_readiness.py",
        ],
        "evidence": [
            "Qdrant-backed retrieval modules physically nested under "
            "app/voice_agent/ but owned by the RAG domain."
        ],
        "critical": False,
        "requires_corroboration": True,
    },
    "billing_payments": {
        "include_prefixes": ["app/billing/"],
        "exclude_prefixes": [],
        # idempotency.py is a generic dedupe helper reused outside billing
        "exclude_stems": ["idempotency"],
        "exact_files": [],
        "evidence": [
            "app/billing/ read: 10 modules — subscription, invoice, "
            "usage, dunning, entitlement. Only idempotency.py is shared."
        ],
        "critical": True,
        "requires_corroboration": True,
    },
    "social_publish": {
        "include_prefixes": ["app/social_engine/"],
        "exclude_prefixes": [],
        "exclude_stems": [],
        "exact_files": [],
        "evidence": [
            "app/social_engine/ read: 13 modules, all publish "
            "scheduling/providers/validation for social channels."
        ],
        "critical": False,
        "requires_corroboration": True,
    },
    "lead_pipeline": {
        "include_prefixes": ["app/lead_scraper/"],
        "exclude_prefixes": [],
        "exclude_stems": [],
        "exact_files": [],
        "evidence": [
            "app/lead_scraper/ read: 13 modules, all discovery, "
            "extraction, verification and enrichment of leads."
        ],
        "critical": False,
        "requires_corroboration": True,
    },
    "owner_os_copilot": {
        "include_prefixes": [],
        "exclude_prefixes": [],
        "exclude_stems": [],
        # carved out of the rejected app/integrations/ package by review
        "exact_files": [
            "app/integrations/openclaw/owner_os_adapter.py",
            "app/integrations/openclaw/harness_commands.py",
            "app/integrations/openclaw/harness_agent.py",
            "app/integrations/openclaw/policies.py",
            "app/integrations/openclaw/commands.py",
            "app/integrations/openclaw/context_builder.py",
        ],
        "evidence": [
            "OpenClaw Owner-Copilot subtree nested under "
            "app/integrations/ — ADR-OPENCLAW-OWNER-COPILOT."
        ],
        "critical": True,
        "requires_corroboration": True,
    },
}


def _stem(path: str) -> str:
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def owning_domain(path: str) -> tuple[str | None, str | None]:
    """Return (domain, reason) for a repo-relative file path, else (None, reason).

    Exact-file mappings win over prefixes. A path under a REJECTED root that is
    not exactly mapped is deliberately unowned.
    """
    if not path:
        return None, "empty path"

    for dom, rule in sorted(DOMAIN_OWNERSHIP_RULES.items()):
        if path in rule["exact_files"]:
            return dom, f"exact-file ownership ({dom})"

    for root, why in sorted(REJECTED_ROOTS.items()):
        if path.startswith(root):
            return None, f"shared/mixed package {root} rejected: {why}"

    for dom, rule in sorted(DOMAIN_OWNERSHIP_RULES.items()):
        for pref in rule["include_prefixes"]:
            if not path.startswith(pref):
                continue
            if any(path.startswith(x) for x in rule["exclude_prefixes"]):
                return None, f"excluded prefix under {pref}"
            if _stem(path) in rule["exclude_stems"]:
                return None, f"{_stem(path)} explicitly excluded from {dom}"
            return dom, f"reviewed package ownership {pref} -> {dom}"

    return None, "no reviewed ownership rule covers this path"


def validate_rules(domain_keys: set[str]) -> list[str]:
    """Structural self-check (used by tests)."""
    problems: list[str] = []
    seen_exact: dict[str, str] = {}
    for dom, rule in DOMAIN_OWNERSHIP_RULES.items():
        if dom not in domain_keys:
            problems.append(f"{dom}: not a canonical domain key")
        if not rule.get("evidence"):
            problems.append(f"{dom}: ownership rule without evidence")
        if not rule.get("requires_corroboration"):
            problems.append(f"{dom}: ownership must always require corroboration")
        for f in rule["exact_files"]:
            if f in seen_exact:
                problems.append(f"{f}: claimed by {seen_exact[f]} and {dom}")
            seen_exact[f] = dom
        for pref in rule["include_prefixes"]:
            for root in REJECTED_ROOTS:
                if pref.startswith(root):
                    problems.append(
                        f"{dom}: include_prefix {pref} sits inside rejected root {root}"
                    )
    return problems
