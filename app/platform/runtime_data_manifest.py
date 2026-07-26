"""Deduplicated store-family manifest — one entry per logical AUTHORITY.

Not one entry per source literal. The raw scan found ~250 `data/` path literals
across ~150 modules, but a literal count is not a store count: several literals
name the same store, some name read-only fixtures, some name rebuildable caches,
and some name files that do not exist in production at all.

Every `current_authority` and `production_activity` value below is backed by
read-only production evidence (file `stat`, `wc -l`, and `pg_stat_user_tables`
row counts taken 2026-07-26). Where evidence is absent the entry says `UNKNOWN`
rather than guessing — an unknown authoritative store is a deployment blocker.

This module is DATA. It performs no I/O and moves no files.
"""

from __future__ import annotations

from typing import Any

MANIFEST_VERSION = "2026-07-26.1"

# --- migration lifecycle states ---------------------------------------------
LEGACY_IN_CHECKOUT = "LEGACY_IN_CHECKOUT"
DUAL_READ_PRE_CUTOVER = "DUAL_READ_PRE_CUTOVER"
COPIED_NOT_VERIFIED = "COPIED_NOT_VERIFIED"
EXTERNAL_VERIFIED = "EXTERNAL_VERIFIED"
CUTOVER_COMPLETE = "CUTOVER_COMPLETE"
DATABASE_AUTHORITY = "DATABASE_AUTHORITY"
FALLBACK_ONLY = "FALLBACK_ONLY"
FIXTURE_ONLY = "FIXTURE_ONLY"
STATIC_ASSET = "STATIC_ASSET"
GENERATED_ARTIFACT = "GENERATED_ARTIFACT"
REBUILDABLE_CACHE = "REBUILDABLE_CACHE"
UNKNOWN = "UNKNOWN"

VALID_STATES = frozenset(
    {
        LEGACY_IN_CHECKOUT,
        DUAL_READ_PRE_CUTOVER,
        COPIED_NOT_VERIFIED,
        EXTERNAL_VERIFIED,
        CUTOVER_COMPLETE,
        DATABASE_AUTHORITY,
        FALLBACK_ONLY,
        FIXTURE_ONLY,
        STATIC_ASSET,
        GENERATED_ARTIFACT,
        REBUILDABLE_CACHE,
        UNKNOWN,
    }
)

#: States that BLOCK a destructive production deployment. A store here still
#: holds live authority inside the Git checkout, so `git reset --hard` destroys
#: it. UNKNOWN blocks too: "we did not check" is not evidence of safety.
BLOCKING_STATES = frozenset({LEGACY_IN_CHECKOUT, COPIED_NOT_VERIFIED, UNKNOWN})

TIER_0 = "tier0"  # money, consent, suppression, audit, identity
TIER_1 = "tier1"  # operational business state
TIER_2 = "tier2"  # retention-sensitive artifacts
TIER_3 = "tier3"  # rebuildable
TIER_NONE = "none"  # not a file-cutover concern


def _e(**kw: Any) -> dict[str, Any]:
    return kw


STORES: list[dict[str, Any]] = [
    # ---------------------------------------------------------------- TIER 0
    _e(
        store_id="billing.invoices",
        display_name="GST invoice ledger (Rule-46 sequential)",
        legacy_paths=["data/invoices.jsonl"],
        writer_modules=["app/billing/gst_invoice.py:36"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=14144,
        last_write="2026-07-18",
        database_equivalent="invoices (table exists)",
        current_authority="FILE",
        business_category="billing",
        durability_class="authoritative",
        target_runtime_subpath="billing/invoices.jsonl",
        migration_tier=TIER_0,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
        evidence="25 lines; Rule-46 sequential numbering is a legal requirement",
    ),
    _e(
        store_id="billing.upi_payments",
        display_name="UPI payment records",
        legacy_paths=["data/upi_payments.json"],
        writer_modules=["app/platform/upi_payments.py:22"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=835,
        last_write="2026-07-18",
        database_equivalent="payments (table exists)",
        current_authority="FILE",
        business_category="billing",
        durability_class="authoritative",
        target_runtime_subpath="billing/upi_payments.json",
        migration_tier=TIER_0,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
        evidence="UPI is the primary payment path (Stripe intl-only)",
    ),
    _e(
        store_id="compliance.email_suppression",
        display_name="Unified suppression ledger (email + cross-channel)",
        legacy_paths=["data/email_suppression.jsonl", "data/email_suppression.jsonl.lock"],
        writer_modules=["app/platform/email_unsub.py:44"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=934,
        last_write="2026-07-24",
        database_equivalent=None,
        current_authority="FILE",
        business_category="compliance",
        durability_class="authoritative",
        concurrency_model="multi-process (filelock)",
        target_runtime_subpath="compliance/email_suppression.jsonl",
        migration_tier=TIER_0,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
        evidence="PR #144 canonical authority; lock MUST colocate with ledger",
    ),
    _e(
        store_id="compliance.wa_suppression",
        display_name="WhatsApp campaign suppression",
        legacy_paths=["data/wa_suppression.jsonl"],
        writer_modules=["app/marketing/wa_campaign_runner.py:37"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=95,
        last_write="2026-07-17",
        current_authority="FILE",
        business_category="compliance",
        durability_class="authoritative",
        target_runtime_subpath="compliance/wa_suppression.jsonl",
        migration_tier=TIER_0,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
        evidence="read by unified eligibility; caused a PR #144 CI pollution incident",
    ),
    _e(
        store_id="compliance.consent_ledger",
        display_name="TRAI/DPDP consent ledger",
        legacy_paths=["data/consent_ledger.jsonl"],
        writer_modules=["app/telephony/consent_ledger.py:176"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=482,
        last_write="2026-07-17",
        current_authority="FILE",
        business_category="compliance",
        durability_class="authoritative",
        retention_policy="regulatory",
        target_runtime_subpath="compliance/consent_ledger.jsonl",
        migration_tier=TIER_0,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
    ),
    _e(
        store_id="compliance.voice_suppression",
        display_name="Voice/DND suppression",
        legacy_paths=["data/voice_suppression.jsonl"],
        writer_modules=["app/telephony/consent_ledger.py:177"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        last_write="2026-07-17",
        current_authority="FILE",
        business_category="compliance",
        durability_class="authoritative",
        target_runtime_subpath="compliance/voice_suppression.jsonl",
        migration_tier=TIER_0,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
        evidence="currently EMPTY (0 bytes) — empty is not the same as absent; "
        "the file is the authority and must survive cutover",
    ),
    _e(
        store_id="compliance.dpdp_audit",
        display_name="DPDP audit log",
        legacy_paths=["data/dpdp_audit.jsonl", "data/dpdp_requests.jsonl"],
        writer_modules=["app/platform/dpdp.py:73", "app/platform/dpdp.py:74"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=196,
        last_write="2026-06-10",
        database_equivalent="compliance_audit_logs (MODEL DECLARED, TABLE ABSENT)",
        current_authority="FILE",
        business_category="compliance",
        durability_class="authoritative",
        target_runtime_subpath="compliance/dpdp_audit.jsonl",
        migration_tier=TIER_0,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
        evidence="app/models/compliance_audit.py declares compliance_audit_logs but "
        "the table does not exist in production — verified architecture gap",
    ),
    _e(
        store_id="customers.identity",
        display_name="Marketing client / customer registry",
        legacy_paths=["data/marketing_clients.jsonl", "data/marketing_clients.jsonl.lock"],
        writer_modules=["app/marketing/clients_store.py:38"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=4180,
        last_write="2026-07-26",
        database_equivalent="clients (1 row only)",
        current_authority="FILE",
        business_category="customers",
        durability_class="authoritative",
        concurrency_model="multi-process (best-effort filelock)",
        target_runtime_subpath="customers/marketing_clients.jsonl",
        migration_tier=TIER_0,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
        evidence="8 JSONL rows vs 1 DB row; written TODAY; known read-time-rewrite defect",
    ),
    # ---------------------------------------------------------------- TIER 1
    _e(
        store_id="sales.prospects",
        display_name="Prospect store",
        legacy_paths=["data/prospects.jsonl"],
        writer_modules=["app/platform/prospector.py:38"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=20332879,
        last_write="2026-07-25",
        current_authority="FILE",
        business_category="sales",
        durability_class="authoritative",
        target_runtime_subpath="sales/prospects.jsonl",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
        evidence="18,100 records; whole-file rewrite on update",
    ),
    _e(
        store_id="sales.autopilot_state",
        display_name="Sales-autopilot prospects + attempts",
        legacy_paths=["data/sales_autopilot/"],
        writer_modules=["app/platform/sales_autopilot/store.py:21"],
        production_activity="UNKNOWN",
        current_authority="FILE",
        business_category="sales",
        durability_class="authoritative",
        target_runtime_subpath="sales/autopilot/",
        migration_tier=TIER_1,
        migration_state=UNKNOWN,
        deployment_blocker=True,
        evidence="engine INERT in prod (SALES_AUTOPILOT_ENABLED unset); "
        "holds durable opt-out cancellation state from PR #144",
    ),
    _e(
        store_id="content.approvals",
        display_name="Content approvals",
        legacy_paths=["data/content_approvals.jsonl"],
        writer_modules=["app/marketing/content_approval.py:32"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=542973,
        last_write="2026-07-25",
        current_authority="FILE",
        business_category="content",
        durability_class="authoritative",
        target_runtime_subpath="content/content_approvals.jsonl",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
    ),
    _e(
        store_id="content.queue",
        display_name="Per-tenant content queue",
        legacy_paths=["data/content_queue/"],
        writer_modules=["app/marketing/auto_content.py:45", "app/agents/staff.py:570"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=315392,
        current_authority="FILE",
        business_category="content",
        durability_class="authoritative",
        concurrency_model="multi-process, NO LOCK (known lost-write risk)",
        tenant_scope="per-tenant filename",
        target_runtime_subpath="content/queue/",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
        evidence="concurrency redesign is a SEPARATE PR; this entry is path-only",
    ),
    _e(
        store_id="delivery.ledger",
        display_name="Per-tenant delivery ledger",
        legacy_paths=["data/delivery_ledger/"],
        writer_modules=["app/marketing/delivery_ledger.py:45"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=372736,
        current_authority="FILE",
        business_category="delivery",
        durability_class="authoritative",
        tenant_scope="per-tenant filename",
        target_runtime_subpath="delivery/ledger/",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
    ),
    _e(
        store_id="automation.job_runs",
        display_name="Scheduler job-run telemetry",
        legacy_paths=["data/job_runs.jsonl", "data/job_heartbeats.json"],
        writer_modules=["app/platform/automation_health.py:27"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=27919768,
        last_write="2026-07-26",
        current_authority="FILE",
        business_category="automation",
        durability_class="operational-telemetry",
        retention_policy="NONE DEFINED — unbounded growth",
        target_runtime_subpath="automation/job_runs.jsonl",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
        evidence="27.9 MB and growing daily; needs a retention decision, " "not just relocation",
    ),
    _e(
        store_id="automation.cadence_runs",
        display_name="Cadence run telemetry",
        legacy_paths=["data/cadence_runs.jsonl", "data/cadence_leads.jsonl"],
        writer_modules=["app/marketing/cadence.py:25", "app/marketing/cadence.py:26"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=11844399,
        last_write="2026-07-26",
        current_authority="FILE",
        business_category="automation",
        durability_class="operational-telemetry",
        retention_policy="NONE DEFINED",
        target_runtime_subpath="automation/cadence_runs.jsonl",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
    ),
    # ------------------------------------------------------- UNRESOLVED
    _e(
        store_id="communications.interactions",
        display_name="Omnichannel interaction log",
        legacy_paths=["data/interactions.jsonl"],
        writer_modules=["app/platform/interaction_log.py:21"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=1167941,
        last_write="2026-07-25",
        database_equivalent="interactions (2,611 rows)",
        current_authority="DUAL_WRITE_DRIFTED",
        business_category="communications",
        durability_class="authoritative",
        target_runtime_subpath="communications/interactions.jsonl",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
        evidence="NEITHER store is safe to delete. DB has resolved identity and drives "
        "lead_status_history; JSONL is the ONLY store with email/phone and the only one "
        "any live endpoint reads. Field sets are partially disjoint by schema, so neither "
        "can be rebuilt from the other. Non-transactional writes, both silently swallowed.",
    ),
    # ------------------------------------------------- DATABASE AUTHORITY
    _e(
        store_id="governance.owner_os",
        display_name="Owner OS commands / kill switches / audit",
        legacy_paths=[
            "data/owner_commands.jsonl",
            "data/owner_kill_switches.jsonl",
            "data/owner_os_audit.jsonl",
        ],
        writer_modules=["app/platform/owner_os_store.py:22-24"],
        production_activity="PRODUCTION_INACTIVE",
        database_equivalent="owner_commands / owner_kill_switches / owner_os_audit_events",
        current_authority="DATABASE",
        business_category="governance",
        durability_class="authoritative",
        target_storage="database",
        migration_tier=TIER_NONE,
        migration_state=FALLBACK_ONLY,
        deployment_blocker=False,
        evidence="422 owner_os_audit_events rows in production; all three JSONL files "
        "ABSENT on the VPS — the file paths are a fallback that production never uses",
    ),
    _e(
        store_id="sales.leads",
        display_name="Lead pipeline",
        legacy_paths=[],
        database_equivalent="leads (10,759 rows) + lead_status_history (1,363)",
        current_authority="DATABASE",
        production_activity="PRODUCTION_ACTIVE",
        business_category="sales",
        durability_class="authoritative",
        target_storage="database",
        migration_tier=TIER_NONE,
        migration_state=DATABASE_AUTHORITY,
        deployment_blocker=False,
    ),
    # ------------------------------------------------------- TIER 2 / 3
    _e(
        store_id="artifacts.call_recordings",
        display_name="Call recordings + transcripts",
        legacy_paths=["data/call_recordings/", "data/call_transcripts/"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=191102976,
        current_authority="FILE",
        business_category="compliance",
        durability_class="retention-sensitive-artifact",
        retention_policy="90 days (DPDP) — enforcement not verified",
        target_runtime_subpath="artifacts/call_recordings/",
        migration_tier=TIER_2,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=False,
        evidence="182 MB. Personal data. NOT an ordinary disposable artifact — "
        "large-binary migration needs its own capacity/retention analysis",
    ),
    _e(
        store_id="artifacts.generated_media",
        display_name="Reels, video ads, studio media, GIFs, stickers",
        legacy_paths=[
            "data/reels/",
            "data/video_ads/",
            "data/studio_media/",
            "data/gifs/",
            "data/stickers/",
        ],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=10485760,
        current_authority="FILE",
        business_category="delivery",
        durability_class="generated-artifact",
        target_runtime_subpath="artifacts/media/",
        migration_tier=TIER_2,
        migration_state=GENERATED_ARTIFACT,
        deployment_blocker=False,
    ),
    _e(
        store_id="cache.ml_models",
        display_name="Ollama models + U2Net weights",
        legacy_paths=["data/ollama/", "data/u2net/"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=2113929216,
        current_authority="FILE",
        business_category="automation",
        durability_class="rebuildable-cache",
        target_runtime_subpath="cache/",
        migration_tier=TIER_3,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence="1.97 GB — 82% of the whole data dir, and re-downloadable. "
        "Must NOT be dragged into a JSONL migration wave",
    ),
    _e(
        store_id="static.legal_documents",
        display_name="PTEC / Udyam registration certificates",
        legacy_paths=["data/compliance/", "data/legal/"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=893952,
        current_authority="FILE",
        business_category="compliance",
        durability_class="static-asset",
        target_runtime_subpath=None,
        migration_tier=TIER_NONE,
        migration_state=STATIC_ASSET,
        deployment_blocker=False,
        evidence="static PDFs unmodified since Jun 8 / Jun 25 — documents, not ledgers",
    ),
]


def by_state(state: str) -> list[dict[str, Any]]:
    return [s for s in STORES if s.get("migration_state") == state]


def blocking_stores() -> list[dict[str, Any]]:
    """Stores that must block a destructive production deployment."""
    return [
        s
        for s in STORES
        if s.get("deployment_blocker") and s.get("migration_state") in BLOCKING_STATES
    ]


def counts() -> dict[str, int]:
    """Verified counts — derived, never hand-written."""
    out: dict[str, int] = {
        "unique_families": len(STORES),
        "production_active": 0,
        "file_authoritative": 0,
        "database_authoritative": 0,
        "fallback_only": 0,
        "static_assets": 0,
        "generated_artifacts": 0,
        "rebuildable_caches": 0,
        "unknown": 0,
        "deployment_blockers": len(blocking_stores()),
        TIER_0: 0,
        TIER_1: 0,
        TIER_2: 0,
        TIER_3: 0,
        TIER_NONE: 0,
    }
    for s in STORES:
        if s.get("production_activity") == "PRODUCTION_ACTIVE":
            out["production_active"] += 1
        auth = s.get("current_authority")
        if auth == "FILE":
            out["file_authoritative"] += 1
        elif auth == "DATABASE":
            out["database_authoritative"] += 1
        state = s.get("migration_state")
        if state == FALLBACK_ONLY:
            out["fallback_only"] += 1
        elif state == STATIC_ASSET:
            out["static_assets"] += 1
        elif state == GENERATED_ARTIFACT:
            out["generated_artifacts"] += 1
        elif state == REBUILDABLE_CACHE:
            out["rebuildable_caches"] += 1
        elif state == UNKNOWN:
            out["unknown"] += 1
        out[str(s.get("migration_tier", TIER_NONE))] += 1
    return out


__all__ = [
    "MANIFEST_VERSION",
    "STORES",
    "VALID_STATES",
    "BLOCKING_STATES",
    "blocking_stores",
    "by_state",
    "counts",
]
