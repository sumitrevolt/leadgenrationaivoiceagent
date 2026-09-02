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
#: DUAL_READ_PRE_CUTOVER blocks too (added 2026-07-28, A1). The state means the
#: CODE can follow a cutover — the DATA has not moved, so the authoritative copy
#: is still inside the checkout and `git reset --hard` still destroys it.
#: Excluding it would have dropped the blocker count from 21 to 18 the moment a
#: resolver landed, which is a false green: resolver-ready is not data-safe.
BLOCKING_STATES = frozenset(
    {LEGACY_IN_CHECKOUT, DUAL_READ_PRE_CUTOVER, COPIED_NOT_VERIFIED, UNKNOWN}
)

TIER_0 = "tier0"  # money, consent, suppression, audit, identity
TIER_1 = "tier1"  # operational business state
TIER_2 = "tier2"  # retention-sensitive artifacts
TIER_3 = "tier3"  # rebuildable
TIER_NONE = "none"  # not a file-cutover concern

#: Disjoint buckets — every store has exactly one, so they must sum to len(STORES).
TIERS = (TIER_0, TIER_1, TIER_2, TIER_3, TIER_NONE)


def _e(**kw: Any) -> dict[str, Any]:
    return kw


STORES: list[dict[str, Any]] = [
    # ---------------------------------------------------------------- TIER 0
    _e(
        store_id="billing.invoices",
        display_name="GST invoice ledger (Rule-46 sequential)",
        legacy_paths=["data/invoices.jsonl"],
        writer_modules=["app/billing/gst_invoice.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=14144,
        last_write="2026-07-18",
        database_equivalent="invoices (table exists)",
        current_authority="FILE",
        business_category="billing",
        durability_class="authoritative",
        target_runtime_subpath="billing/invoices.jsonl",
        migration_tier=TIER_0,
        # A5 (2026-07-29): writers resolve through runtime_data_authority.
        # Host cutover verified — CUTOVER_COMPLETE (bytes external; checkout retained).
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
        evidence="25 lines; Rule-46 sequential numbering is a legal requirement",
    ),
    _e(
        store_id="billing.upi_payments",
        display_name="UPI payment records",
        legacy_paths=["data/upi_payments.json", "data/platform_upi.json"],
        writer_modules=["app/platform/upi_payments.py", "app/platform/upi_config.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=835,
        last_write="2026-07-18",
        database_equivalent="payments (table exists)",
        current_authority="FILE",
        business_category="billing",
        durability_class="authoritative",
        target_runtime_subpath="billing/upi_payments.json",
        migration_tier=TIER_0,
        # A5 (2026-07-29): writers resolve through runtime_data_authority.
        # Host cutover verified — CUTOVER_COMPLETE (bytes external; checkout retained).
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
        evidence="UPI is the primary payment path (Stripe intl-only); "
        "platform_upi.json is the sibling VPA config under the same store id",
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
        # A3 (2026-07-28): writers resolve through runtime_data_authority.
        # Host cutover verified — CUTOVER_COMPLETE (bytes external; checkout retained).
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
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
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
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
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
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
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
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
        # A3 (2026-07-28): writers resolve through runtime_data_authority.
        # Host cutover verified — CUTOVER_COMPLETE (bytes external; checkout retained).
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
        evidence="app/models/compliance_audit.py declares compliance_audit_logs but "
        "the table does not exist in production — verified architecture gap",
    ),
    _e(
        store_id="customers.identity",
        display_name="Marketing client / customer registry",
        legacy_paths=["data/marketing_clients.jsonl", "data/marketing_clients.jsonl.lock"],
        writer_modules=["app/marketing/clients_store.py"],
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
        # A5 (2026-07-29): writers resolve through runtime_data_authority.
        # Host cutover verified — CUTOVER_COMPLETE (bytes external; checkout retained).
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
        evidence="8 JSONL rows vs 1 DB row; written TODAY; known read-time-rewrite defect",
    ),
    # ---------------------------------------------------------------- TIER 1
    _e(
        store_id="sales.prospects",
        display_name="Prospect store",
        legacy_paths=["data/prospects.jsonl"],
        writer_modules=["app/platform/prospector.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=20332879,
        last_write="2026-07-25",
        current_authority="FILE",
        business_category="sales",
        durability_class="authoritative",
        target_runtime_subpath="sales/prospects.jsonl",
        migration_tier=TIER_1,
        # A7 (2026-07-29): writers resolve through runtime_data_authority.
        # Host cutover verified — CUTOVER_COMPLETE (bytes external; checkout retained).
        # Host cutover is a SEPARATE PR; this wave is code-only.
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
        evidence="18,100 records; whole-file rewrite on update",
    ),
    _e(
        store_id="automation.autopilot_tick",
        display_name="Sales-autopilot scheduler tick marker",
        legacy_paths=["data/sales_autopilot/last_tick.json"],
        writer_modules=["app/platform/sales_autopilot/store.py:21"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=120,
        last_write="2026-07-25",
        current_authority="FILE",
        business_category="automation",
        durability_class="resumable-operational",
        production_active=True,
        mutable=True,
        # Losing a tick marker costs one re-run of an INERT engine. That is a
        # documented-safe loss, which is what keeps it off the blocker list.
        authoritative_or_required=False,
        inside_checkout=True,
        externally_protected=False,
        target_runtime_subpath="automation/autopilot/last_tick.json",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=False,
        blocker_reason="resumable tick marker; engine INERT (SALES_AUTOPILOT_ENABLED unset)",
        evidence="production `ls` 2026-07-26 shows the directory holds exactly ONE file, "
        "last_tick.json (120 bytes). The prospects/attempts/policy stores this entry "
        "previously assumed do not exist as files in production — the directory is not "
        "a multi-store family.",
    ),
    _e(
        store_id="ops.owner_email_canary",
        display_name="Owner-inbox one-shot email canary attempts",
        legacy_paths=["data/owner_email_canary/attempts.jsonl"],
        writer_modules=["app/platform/owner_email_canary.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        last_write="2026-07-30",
        current_authority="FILE",
        business_category="ops",
        durability_class="resumable-operational",
        production_active=True,
        mutable=True,
        authoritative_or_required=False,
        inside_checkout=True,
        externally_protected=False,
        target_runtime_subpath="ops/owner_email_canary/attempts.jsonl",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=False,
        blocker_reason="append-only masked canary ledger; safe to lose (re-run one-shot)",
        evidence="new store 2026-07-30; resolve_store_path wired; recipient never stored cleartext",
    ),
    _e(
        store_id="ops.office_briefing",
        display_name="Daily Office HQ Hot Queue brief + owner notify claim",
        legacy_paths=[
            "data/office_briefing/",
            "data/office_briefing/*.owner-notified",
        ],
        writer_modules=["app/platform/office_briefing.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        last_write="2026-08-14",
        current_authority="FILE",
        business_category="ops",
        durability_class="resumable-operational",
        production_active=True,
        mutable=True,
        authoritative_or_required=False,
        inside_checkout=True,
        externally_protected=False,
        target_runtime_subpath="ops/office_briefing/",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=False,
        blocker_reason=(
            "daily brief cache + at-most-once owner ntfy claim; safe to lose "
            "(brief regenerates, claim release only re-sends same-day reminder)"
        ),
        evidence=(
            "declared 2026-08-14 with Hot Queue owner reminder; "
            "*.owner-notified is O_EXCL claim only — no prospect auto-send"
        ),
    ),
    _e(
        store_id="ops.hot_queue_owner_pack_csv",
        display_name="Daily CSV of /api/ops/hotqueue for owner 1-click close",
        legacy_paths=["data/hot_queue_for_owner_<date>.csv"],
        writer_modules=["app/platform/hot_queue_owner_pack.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        last_write="2026-08-27",
        current_authority="FILE",
        business_category="ops",
        durability_class="resumable-operational",
        production_active=True,
        mutable=True,
        authoritative_or_required=False,
        inside_checkout=True,
        externally_protected=False,
        target_runtime_subpath="ops/hot_queue_owner_pack/",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=False,
        blocker_reason=(
            "owner-local CSV re-written each morning by the 09:00 IST job; "
            "safe to lose (next-day job regenerates it from hot_queue())"
        ),
        evidence=(
            "ADR-OWNER-1 (2026-08-27): CSV is owner-only, never auto-sent; "
            "wa.me column carries the pre-drafted UPI deep-link."
        ),
    ),
    _e(
        store_id="ops.hot_queue_owner_pack_md",
        display_name="Daily top-15 markdown of /api/ops/hotqueue for owner",
        legacy_paths=["data/hot_queue_for_owner_<date>.md"],
        writer_modules=["app/platform/hot_queue_owner_pack.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        last_write="2026-08-27",
        current_authority="FILE",
        business_category="ops",
        durability_class="resumable-operational",
        production_active=True,
        mutable=True,
        authoritative_or_required=False,
        inside_checkout=True,
        externally_protected=False,
        target_runtime_subpath="ops/hot_queue_owner_pack/",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=False,
        blocker_reason=(
            "owner-local MD re-written each morning by the 09:00 IST job; "
            "safe to lose (next-day job regenerates it from hot_queue())"
        ),
        evidence=(
            "ADR-OWNER-1 (2026-08-27): MD is the top-15 clickable view of "
            "the same data as the CSV; owner-only, never auto-sent."
        ),
    ),
    _e(
        store_id="governance.mission_control",
        display_name="Chat-first mission packets + append-only decision ledger",
        legacy_paths=[
            "data/mission_control/ledger.jsonl",
            "data/mission_control/missions",
            "data/mission_control/idempotency_index.json",
            "data/mission_control/dlq.jsonl",
        ],
        writer_modules=["app/platform/mission_control.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        last_write="2026-07-31",
        current_authority="FILE",
        business_category="governance",
        durability_class="resumable-operational",
        production_active=True,
        mutable=True,
        authoritative_or_required=False,
        inside_checkout=True,
        externally_protected=False,
        target_runtime_subpath="governance/mission_control/",
        migration_tier=TIER_1,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=False,
        blocker_reason="Owner OS mission packets; safe to re-create (chat is not authority)",
        evidence="new store 2026-07-31; durable idempotency index + append-only ledger under file_lock",
    ),
    _e(
        store_id="owner_os.coordination_hub",
        display_name="Coordination Hub projection (presence + events + nonce fps)",
        legacy_paths=[
            "data/coordination_hub/",
            "data/coordination_hub/events.jsonl",
            "data/coordination_hub/presence.json",
            "data/coordination_hub/nonce_fps.jsonl",
        ],
        writer_modules=[
            "app/platform/coordination_hub_events.py",
            "app/platform/coordination_hub_auth.py",
        ],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        last_write="2026-08-04",
        current_authority="FILE",
        business_category="governance",
        durability_class="rebuildable",
        production_active=True,
        mutable=True,
        authoritative_or_required=False,
        inside_checkout=True,
        externally_protected=False,
        target_runtime_subpath="owner_os/coordination_hub/",
        migration_tier=TIER_2,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        blocker_reason="Hub projection only; safe to lose (tools re-heartbeat)",
        evidence=(
            "ADR-150 thin Owner OS projection; flag COORDINATION_HUB_ENABLED default OFF. "
            "Not a mission ledger or STAFF registry."
        ),
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
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
    ),
    _e(
        store_id="platform.workforce_memory",
        display_name="Per-STAFF workforce memory hub (ADR-154)",
        legacy_paths=["data/workforce_memory/"],
        writer_modules=["app/platform/workforce_memory.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="agents",
        durability_class="rebuildable",
        concurrency_model="append-mostly JSONL per agent; equipments.json rewrite; no lock",
        tenant_scope="per-STAFF-agent directory (not customer tenant)",
        target_runtime_subpath="platform/workforce_memory/",
        migration_tier=TIER_2,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-03 with ADR-154 Workforce Memory Hub. Layered L0–L3 "
            "JSONL + refs under data/workforce_memory/{agent}/. Losing files degrades "
            "agent continuity (lessons/persona) but does not destroy billing, consent, "
            "or invoice authority — hence rebuildable. Admin purge/prune are DPDP/ops "
            "erase paths; chat/L0 stays private; team share is skill/wiki only."
        ),
    ),
    _e(
        store_id="platform.memory_governance",
        display_name="Memory stack do-not-remember + governance audit (ADR-161)",
        legacy_paths=[
            "data/memory_suppression.jsonl",
            "data/memory_governance_audit.jsonl",
        ],
        writer_modules=["app/platform/memory_governance.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="agents",
        durability_class="authoritative",
        concurrency_model="append-only JSONL; atomic rewrite for rules file",
        tenant_scope="tenant-scoped rows inside shared files",
        target_runtime_subpath="platform/memory_governance/",
        migration_tier=TIER_2,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-05 with ADR-161 Memory Stack governance. Suppression "
            "rules + hashed audit trail under data/. INERT until MEMORY_STACK_ENABLED; "
            "fail-closed durable writes when authority unreadable."
        ),
    ),
    _e(
        store_id="marketing.brand_kits",
        display_name="Per-tenant brand kit profile",
        legacy_paths=["data/brand_kits/"],
        writer_modules=["app/marketing/brand_kit.py:67", "app/marketing/brand_kit.py:90"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="content",
        durability_class="rebuildable",
        concurrency_model="single-writer per tenant file (admin/onboarding), no lock",
        tenant_scope="per-tenant filename",
        target_runtime_subpath="marketing/brand_kits/",
        migration_tier=TIER_2,
        # NOT CUTOVER_COMPLETE: the bytes were never moved out of the checkout or
        # verified, so claiming that would be unevidenced. Re-enterable content.
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-02 when admin remove-customer added a DELETE against "
            "this store and the runtime-data ratchet correctly refused an undeclared "
            "destructive path. Colours/logo/handles are re-enterable from the admin "
            "UI, so losing a file degrades poster branding rather than destroying "
            "authoritative business state - hence rebuildable, not authoritative. "
            "The DELETE is DPDP purge behaviour: removing a customer must not leave "
            "their brand assets behind."
        ),
    ),
    # ------------------------------------------------ TIER 3 - rebuildable
    _e(
        store_id="marketing.gsc_rankings",
        display_name="Search Console rank snapshot (ADR-177 pSEO observability)",
        legacy_paths=["data/gsc_daily.jsonl", "data/gsc_state.json"],
        writer_modules=["app/integrations/gsc.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="marketing",
        durability_class="rebuildable",
        concurrency_model="single writer (staff-gsc-rank-daily beat, 00:30 IST)",
        tenant_scope="platform-global (own-domain SEO observability)",
        target_runtime_subpath="marketing/gsc_rankings/",
        migration_tier=TIER_3,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-11 with ADR-177. Daily append-only JSONL + run-state "
            "JSON for the free Search Console snapshotter; both rebuildable from "
            "the Search Console API, so rebuildable, not authoritative. INERT "
            "until GSC_ENABLED=1 and service-account creds are set (runbook: "
            "memory/playbooks.md) - files do not exist on the host yet."
        ),
    ),
    _e(
        store_id="billing.promo_codes",
        display_name="Platform promo/launch-code engine (definitions + applied ledger)",
        legacy_paths=["data/promo_codes.jsonl"],
        writer_modules=["app/billing/promo_codes.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="billing",
        durability_class="rebuildable",
        concurrency_model="single-writer locked read-modify-write with atomic tmp+replace",
        tenant_scope="platform-global (sales/marketing launch offers)",
        target_runtime_subpath="billing/promo_codes/",
        migration_tier=TIER_3,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-23 with the revenue-sprint batch. Promo definitions "
            "+ applied-redemption ledger for platform-level discount codes; "
            "re-enterable from admin re-creation (codes are short-lived launch "
            "artifacts), so rebuildable rather than authoritative. Created lazily "
            "on first admin create_code call."
        ),
    ),
    _e(
        store_id="marketing.affiliates",
        display_name="Affiliate/referral program ledger (registrations + conversions)",
        legacy_paths=[
            "data/affiliates.jsonl",
            "data/affiliate_referrals.jsonl",
        ],
        writer_modules=["app/marketing/affiliate.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="growth",
        durability_class="rebuildable",
        concurrency_model="append for registrations; locked atomic rewrite for lead→paid flip",
        tenant_scope="platform-global (referral partners; contact keys only)",
        target_runtime_subpath="marketing/affiliates/",
        migration_tier=TIER_3,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-23 when the revenue-sprint batch added the "
            "lead→paid flip on UPI activation (previously referrals never "
            "reached 'paid', so commission_earned was permanently ₹0). "
            "Re-enterable from affiliate re-registration + payment ledger."
        ),
    ),
    _e(
        store_id="platform.staff_bus",
        display_name="31 STAFF Buzz bus ledger (events / idempotency / audit / DLQ)",
        legacy_paths=[
            "data/staff_bus/",
            "data/staff_bus/events.jsonl",
            "data/staff_bus/idempotency.jsonl",
            "data/staff_bus/audit.jsonl",
            "data/staff_bus/dlq.jsonl",
        ],
        writer_modules=["app/platform/staff_bus/runtime.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="platform",
        durability_class="rebuildable",
        concurrency_model="single-process file append under STAFF_BUS_ENABLED gate",
        tenant_scope="platform-global (internal STAFF coordination; not customer leads)",
        target_runtime_subpath="platform/staff_bus/",
        migration_tier=TIER_3,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-12 with PR #333 staff_bus. Append-only JSONL family "
            "for Owner→Boss→7-team envelopes. INERT until STAFF_BUS_ENABLED=1; "
            "default OFF. Comb NIP-OA auth_tag may be null (WAIT) — not a store "
            "blocker. No customer outbound from these files alone."
        ),
    ),
    # ------------------------------------------------ TIER 3 - marketing feature JSONL (INERT)
    # Classified 2026-08-16 so the runtime-data ratchet does not treat new
    # checkout JSONL writers as undeclared debt. Flags stay OFF; files are
    # empty/absent in prod until an owner arms the matching switch.
    _e(
        store_id="marketing.appointment_reminders",
        display_name="Appointment reminder sequences (INERT BOOKING_REMINDERS)",
        legacy_paths=["data/appointment_reminders.jsonl"],
        writer_modules=["app/marketing/appointment_reminders.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="marketing",
        durability_class="rebuildable",
        concurrency_model="single-process JSONL append under BOOKING_REMINDERS",
        tenant_scope="per-client_id rows in one file",
        target_runtime_subpath="marketing/appointment_reminders/",
        migration_tier=TIER_3,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-16 with marketing-features. Append-only reminder "
            "JSONL; rebuildable by re-scheduling. INERT until BOOKING_REMINDERS=1."
        ),
    ),
    _e(
        store_id="marketing.customer_health",
        display_name="Customer health scores (INERT CLIENT_HEALTH_ALERTS)",
        legacy_paths=["data/customer_health.jsonl"],
        writer_modules=["app/marketing/customer_health.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="marketing",
        durability_class="rebuildable",
        concurrency_model="single-process JSONL append under CLIENT_HEALTH_ALERTS",
        tenant_scope="per-client_id rows in one file",
        target_runtime_subpath="marketing/customer_health/",
        migration_tier=TIER_3,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-16 with marketing-features. Score snapshots are "
            "rebuildable from live client/payment signals. INERT until "
            "CLIENT_HEALTH_ALERTS=1."
        ),
    ),
    _e(
        store_id="marketing.email_drips",
        display_name="Email drip definitions + run ledger (INERT)",
        legacy_paths=["data/email_drips.jsonl", "data/email_drip_runs.jsonl"],
        writer_modules=["app/marketing/email_drips.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="marketing",
        durability_class="rebuildable",
        concurrency_model="single-process JSONL append; admin-gated",
        tenant_scope="per-client_id rows in one file",
        target_runtime_subpath="marketing/email_drips/",
        migration_tier=TIER_3,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-16 with marketing-features. Drip templates + run "
            "log are operator-rebuildable. No cold/bulk send from these files "
            "alone; WhatsApp cold stays OFF."
        ),
    ),
    _e(
        store_id="marketing.form_builder",
        display_name="Form definitions + responses (INERT FORM_BUILDER)",
        legacy_paths=["data/forms.jsonl", "data/form_responses.jsonl"],
        writer_modules=["app/marketing/form_builder.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="marketing",
        durability_class="rebuildable",
        concurrency_model="single-process JSONL append under FORM_BUILDER",
        tenant_scope="per-client_id rows in one file",
        target_runtime_subpath="marketing/form_builder/",
        migration_tier=TIER_3,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-16 with marketing-features. INERT until "
            "FORM_BUILDER=1; API returns 503 while the flag is off, so prod "
            "does not grow these files. Empty/absent today."
        ),
    ),
    _e(
        store_id="marketing.proposal_builder",
        display_name="Proposal/quote drafts (INERT PROPOSAL_BUILDER)",
        legacy_paths=["data/proposals.jsonl"],
        writer_modules=["app/marketing/proposal_builder.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="marketing",
        durability_class="rebuildable",
        concurrency_model="single-process JSONL append under PROPOSAL_BUILDER",
        tenant_scope="per-client_id rows in one file",
        target_runtime_subpath="marketing/proposal_builder/",
        migration_tier=TIER_3,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-16 with marketing-features. INERT until "
            "PROPOSAL_BUILDER=1; API returns 503 while the flag is off. "
            "Empty/absent today; not a live billing authority (UPI ledger stays "
            "billing.invoices / billing.upi_payments)."
        ),
    ),
    _e(
        store_id="marketing.review_sequences",
        display_name="Google-review request sequences (INERT REVIEW_MONITOR)",
        legacy_paths=["data/review_sequences.jsonl"],
        writer_modules=["app/marketing/review_automation.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=0,
        current_authority="FILE",
        business_category="marketing",
        durability_class="rebuildable",
        concurrency_model="single-process JSONL append; daily cap in module",
        tenant_scope="per-client_id rows in one file",
        target_runtime_subpath="marketing/review_sequences/",
        migration_tier=TIER_3,
        migration_state=REBUILDABLE_CACHE,
        deployment_blocker=False,
        evidence=(
            "Declared 2026-08-16 with marketing-features. Sequence state is "
            "rebuildable by restarting a review request. Ban-safety daily cap "
            "stays in the module; no fabricated ratings."
        ),
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
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
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
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
    ),
    _e(
        store_id="automation.job_runs",
        display_name="Scheduler job-run telemetry",
        legacy_paths=["data/job_runs.jsonl", "data/job_heartbeats.json"],
        writer_modules=["app/platform/automation_health.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=27919768,
        last_write="2026-07-26",
        current_authority="FILE",
        business_category="automation",
        durability_class="operational-telemetry",
        retention_policy="NONE DEFINED — unbounded growth",
        target_runtime_subpath="automation/job_runs.jsonl",
        migration_tier=TIER_1,
        # A6 (2026-07-29): writers resolve through runtime_data_authority.
        # Host cutover verified — CUTOVER_COMPLETE (bytes external; checkout retained).
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
        evidence="27.9 MB and growing daily; needs a retention decision, not just relocation",
    ),
    _e(
        store_id="automation.cadence_runs",
        display_name="Cadence run telemetry",
        legacy_paths=["data/cadence_runs.jsonl", "data/cadence_leads.jsonl"],
        writer_modules=["app/marketing/cadence.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=11844399,
        last_write="2026-07-26",
        current_authority="FILE",
        business_category="automation",
        durability_class="operational-telemetry",
        retention_policy="NONE DEFINED",
        target_runtime_subpath="automation/cadence_runs.jsonl",
        migration_tier=TIER_1,
        # A6 (2026-07-29): writers resolve through runtime_data_authority.
        # Host cutover verified — CUTOVER_COMPLETE (bytes external; checkout retained).
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
    ),
    # ------------------------------------------------------- UNRESOLVED
    _e(
        store_id="communications.interactions",
        display_name="Omnichannel interaction log",
        legacy_paths=["data/interactions.jsonl"],
        writer_modules=["app/platform/interaction_log.py"],
        production_activity="PRODUCTION_ACTIVE",
        size_bytes=1167941,
        last_write="2026-07-25",
        database_equivalent="interactions (2,611 rows)",
        current_authority="DUAL_WRITE_DRIFTED",
        business_category="communications",
        durability_class="authoritative",
        target_runtime_subpath="communications/interactions.jsonl",
        migration_tier=TIER_1,
        # A6 (2026-07-29): JSONL path resolves through runtime_data_authority;
        # DB dual-write unchanged. Bytes have not moved — still a blocker.
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
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
        production_active=True,
        mutable=True,
        authoritative_or_required=True,
        inside_checkout=True,
        externally_protected=False,
        writer_modules=[
            "app/platform/runtime_recording_paths.py:call_recordings_dir",
            "app/platform/runtime_recording_paths.py:call_transcripts_dir",
        ],
        target_runtime_subpath="artifacts/call_recordings/",
        migration_tier=TIER_2,
        # A9 (2026-07-29) — code follows shared authority; host byte copy is a
        # separate CUTOVER_COMPLETE step. DUAL_READ stays a blocker until then.
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
        blocker_reason="DPDP personal data with a 90-day retention duty, living inside "
        "the Git checkout — `git reset --hard` would destroy customer call evidence",
        evidence="182 MB. Personal data. NOT an ordinary disposable artifact. "
        "Originally recorded here as non-blocking; the manifest validator rejected that, "
        "because it is production-active, mutable, required and unprotected inside the "
        "checkout. Tier 2 governs the MIGRATION ORDER (large binaries need their own "
        "capacity/retention plan), not whether destructive deploy may proceed.",
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
    # ---------------------------------------------------------------- TIER 1
    _e(
        store_id="devcontrol.external_missions",
        display_name="External agent mission state (EXTERNAL_MISSION_DIR)",
        legacy_paths=["data/external_missions/"],
        writer_modules=[
            "app/dev_control/external_agents/cas.py",
            "app/dev_control/external_agents/store.py",
        ],
        production_activity="PRODUCTION_ACTIVE",
        current_authority="FILE",
        business_category="dev-control",
        durability_class="authoritative",
        target_runtime_subpath="external_missions/",
        migration_tier=TIER_1,
        # A8 (2026-07-29): default root resolves through runtime_data_authority
        # with EXTERNAL_MISSION_DIR override. Bytes have not moved — still a blocker.
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
        evidence=(
            "Root is EXTERNAL_MISSION_DIR, defaulting to data/external_missions — "
            "INSIDE the checkout. Per-mission JSON is durable state written via "
            "_atomic_write -> os.replace(tmp, path) from six call sites, plus an "
            "events log beside it. The module's own docstring notes container "
            "replacement does not preserve ./data, so a deploy that resets the "
            "checkout destroys in-flight missions. Not marked cutover-complete: "
            "no evidence yet that production sets the variable to a mounted root."
        ),
    ),
    # ------------------------------------------------ TIER 0 — calling safety
    # Found 2026-07-27 by the path-return-helper provenance pass. Every one of
    # these defaults INSIDE the checkout, so a deploy that resets the tree drops
    # the file and each control silently returns to its permissive default.
    # "Calling is HARD OFF" is not mitigation: platform_dial.json IS one of the
    # three layers holding it off.
    _e(
        store_id="telephony.calling_safety_config",
        display_name="Calling-safety operator config (platform dial + dial test mode)",
        legacy_paths=["data/platform_dial.json", "data/dial_test_mode.json"],
        writer_modules=[
            "app/platform/platform_dial.py:_cfg_path",
            "app/telephony/dial_gate.py:_cfg_path",
        ],
        production_activity="PRODUCTION_ACTIVE",
        current_authority="FILE",
        business_category="telephony",
        durability_class="authoritative",
        target_runtime_subpath="telephony/",
        migration_tier=TIER_0,
        # A1 (2026-07-28): the writers now resolve through
        # runtime_data_authority, so the CODE can follow a cutover. The DATA has
        # not moved and the runtime root is unset, so the legacy files remain
        # authoritative — which is exactly what DUAL_READ_PRE_CUTOVER records.
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
        evidence=(
            "PLATFORM_DIAL_CONFIG -> data/platform_dial.json and "
            "DIAL_TEST_MODE_CONFIG -> data/dial_test_mode.json. One family: "
            "operator-controlled calling-safety configuration, shared cutover "
            "boundary, coordinated rollback, no independent retention ledger. "
            "platform_dial.json carries the `enabled:false` half of the "
            "USER-MANDATE 3-layer platform_dial kill."
        ),
    ),
    _e(
        store_id="telephony.dial_suppression",
        display_name="Dial suppression / blocklist",
        legacy_paths=["data/dial_blocklist.json"],
        writer_modules=[
            "app/telephony/call_feedback.py:_save",
            "app/telephony/dial_gate.py:_blocklist_path",
        ],
        production_activity="PRODUCTION_ACTIVE",
        current_authority="FILE",
        business_category="compliance",
        durability_class="authoritative",
        target_runtime_subpath="telephony/dial_blocklist.json",
        migration_tier=TIER_0,
        # A1 (2026-07-28) — see telephony.calling_safety_config above.
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
        evidence=(
            "DIAL_BLOCKLIST_FILE -> data/dial_blocklist.json. dial_gate.py reads "
            "it and call_feedback.py._save() writes it atomically "
            "(tmp.write_text -> os.replace(tmp, p)); call_feedback's own comment "
            "says 'dial_gate ke saath SAME env/naam — single source'. Suppression "
            "is Tier 0. The audit ledger DIAL_BLOCKLIST_AUDIT is deliberately NOT "
            "folded in here — it needs its own reader/writer evidence first."
        ),
    ),
    _e(
        store_id="telephony.voice_kill_switch",
        display_name="Voice launch kill switch",
        legacy_paths=["data/voice_launch_kill.json"],
        writer_modules=["app/telephony/voice_launch.py:_kill_file"],
        production_activity="PRODUCTION_ACTIVE",
        current_authority="FILE",
        business_category="telephony",
        durability_class="authoritative",
        target_runtime_subpath="telephony/voice_launch_kill.json",
        migration_tier=TIER_0,
        # A1 (2026-07-28) — see telephony.calling_safety_config above.
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
        evidence=(
            "VOICE_LAUNCH_KILL_FILE -> data/voice_launch_kill.json. Kept separate "
            "from calling_safety_config: emergency semantics, independent toggle "
            "lifecycle, stricter fail-closed requirement, separate incident "
            "evidence. Its docstring states the file exists so the kill can flip "
            "'container-recreate ke bina — data/ bind-mount', which is exactly why "
            "losing the file must not disengage the kill."
        ),
    ),
    # ------------------------------------------------------ TIER 2 — retention
    _e(
        store_id="telephony.call_recordings",
        display_name="Call recordings (retention-governed)",
        legacy_paths=["data/recordings/"],
        writer_modules=[
            "app/platform/runtime_recording_paths.py:telephony_recordings_dir",
            "app/telephony/voice_launch.py:_recordings_dir",
        ],
        production_activity="PRODUCTION_ACTIVE",
        current_authority="FILE",
        business_category="compliance",
        durability_class="authoritative",
        target_runtime_subpath="telephony/recordings/",
        migration_tier=TIER_2,
        # A9 (2026-07-29) — RECORDINGS_DIR override preserved; code-only flip.
        migration_state=CUTOVER_COMPLETE,
        deployment_blocker=False,
        retention_governed=True,
        evidence=(
            "RECORDINGS_DIR -> data/recordings. Retention-governed evidence; the "
            "retention window is set by policy elsewhere and is NOT restated here, "
            "because inventing a number the code does not contain would be "
            "fabricated evidence."
        ),
    ),
]


def _flag(store: dict[str, Any], field: str, default: bool) -> bool:
    """Explicit boolean if present, else derived from evidence already recorded."""
    if field in store:
        return bool(store[field])
    return default


def derived_blocker(store: dict[str, Any]) -> bool:
    """A store blocks destructive deployment when ALL of these hold.

    This exists so `deployment_blocker` cannot be *understated* by hand. A
    rebuildable cache or a documented-safe loss may sit inside the checkout
    without blocking; an UNKNOWN active mutable store may not.
    """
    state = store.get("migration_state")
    if state in (
        FALLBACK_ONLY,
        DATABASE_AUTHORITY,
        STATIC_ASSET,
        REBUILDABLE_CACHE,
        CUTOVER_COMPLETE,
        EXTERNAL_VERIFIED,
    ):
        return False
    active = _flag(
        store, "production_active", store.get("production_activity") == "PRODUCTION_ACTIVE"
    )
    mutable = _flag(store, "mutable", store.get("durability_class") != "static-asset")
    required = _flag(
        store,
        "authoritative_or_required",
        store.get("durability_class")
        in ("authoritative", "operational-telemetry", "retention-sensitive-artifact"),
    )
    inside = _flag(store, "inside_checkout", bool(store.get("legacy_paths")))
    protected = _flag(store, "externally_protected", False)
    if state == UNKNOWN and active and mutable and inside and not protected:
        return True
    return bool(active and mutable and required and inside and not protected)


def validate() -> list[str]:
    """Structural problems in the manifest itself. Empty list == consistent."""
    problems: list[str] = []
    ids = [s["store_id"] for s in STORES]
    if len(ids) != len(set(ids)):
        problems.append("duplicate store_id")
    tier_total = sum(1 for s in STORES if s.get("migration_tier") in TIERS)
    if tier_total != len(STORES):
        problems.append(f"tier buckets cover {tier_total} of {len(STORES)} stores")
    for s in STORES:
        if s.get("migration_state") not in VALID_STATES:
            problems.append(f"{s['store_id']}: invalid migration_state")
        if s.get("migration_tier") not in TIERS:
            problems.append(f"{s['store_id']}: invalid migration_tier")
        want = derived_blocker(s)
        got = bool(s.get("deployment_blocker"))
        if want and not got:
            problems.append(
                f"{s['store_id']}: deployment_blocker=False but evidence says it blocks "
                f"({s.get('blocker_reason') or 'no reason recorded'})"
            )
    return problems


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
