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
        # Bytes have not moved — DUAL_READ_PRE_CUTOVER stays a blocker.
        migration_state=DUAL_READ_PRE_CUTOVER,
        deployment_blocker=True,
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
        # Bytes have not moved — DUAL_READ_PRE_CUTOVER stays a blocker.
        migration_state=DUAL_READ_PRE_CUTOVER,
        deployment_blocker=True,
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
        # Bytes have not moved — DUAL_READ_PRE_CUTOVER stays a blocker.
        migration_state=DUAL_READ_PRE_CUTOVER,
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
        migration_state=DUAL_READ_PRE_CUTOVER,
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
        migration_state=DUAL_READ_PRE_CUTOVER,
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
        migration_state=DUAL_READ_PRE_CUTOVER,
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
        # A3 (2026-07-28): writers resolve through runtime_data_authority.
        # Bytes have not moved — DUAL_READ_PRE_CUTOVER stays a blocker.
        migration_state=DUAL_READ_PRE_CUTOVER,
        deployment_blocker=True,
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
        # Bytes have not moved — DUAL_READ_PRE_CUTOVER stays a blocker.
        migration_state=DUAL_READ_PRE_CUTOVER,
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
        migration_state=DUAL_READ_PRE_CUTOVER,
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
        migration_state=DUAL_READ_PRE_CUTOVER,
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
        migration_state=DUAL_READ_PRE_CUTOVER,
        deployment_blocker=True,
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
        # Bytes have not moved — DUAL_READ_PRE_CUTOVER stays a blocker.
        migration_state=DUAL_READ_PRE_CUTOVER,
        deployment_blocker=True,
        evidence="27.9 MB and growing daily; needs a retention decision, " "not just relocation",
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
        # Bytes have not moved — DUAL_READ_PRE_CUTOVER stays a blocker.
        migration_state=DUAL_READ_PRE_CUTOVER,
        deployment_blocker=True,
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
        migration_state=DUAL_READ_PRE_CUTOVER,
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
        production_active=True,
        mutable=True,
        authoritative_or_required=True,
        inside_checkout=True,
        externally_protected=False,
        target_runtime_subpath="artifacts/call_recordings/",
        migration_tier=TIER_2,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
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
        migration_state=DUAL_READ_PRE_CUTOVER,
        deployment_blocker=True,
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
        migration_state=DUAL_READ_PRE_CUTOVER,
        deployment_blocker=True,
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
        migration_state=DUAL_READ_PRE_CUTOVER,
        deployment_blocker=True,
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
        migration_state=DUAL_READ_PRE_CUTOVER,
        deployment_blocker=True,
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
        writer_modules=["app/telephony/voice_launch.py:_recordings_dir"],
        production_activity="PRODUCTION_ACTIVE",
        current_authority="FILE",
        business_category="compliance",
        durability_class="authoritative",
        target_runtime_subpath="telephony/recordings/",
        migration_tier=TIER_2,
        migration_state=LEGACY_IN_CHECKOUT,
        deployment_blocker=True,
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
    if state in (FALLBACK_ONLY, DATABASE_AUTHORITY, STATIC_ASSET, REBUILDABLE_CACHE):
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
