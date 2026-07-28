"""Controlled allowlist of checkout-backed mutable paths.

An entry DECLARES a known legacy access and links it to a store family in
`runtime_data_manifest.py`. It does not make the access safe -- it makes it
reviewed, owned and scheduled.

Matching is by exact line OR by SYMBOL, never by file: one module typically has
a single `_STORE` and many call sites, so a per-line entry would restate the
same fact repeatedly and drift on the first line move. An unrelated write in
the same file stays undeclared and still fails the gate.

`owner` is a DOMAIN, not a person. Inventing individual names would be
fabricated evidence, and the domain is what actually routes a review.

Python rather than JSON to match `runtime_data_manifest.py`, and because
`app/platform/*.json` is gitignored -- a tracked, importable declaration is the
point.
"""

from __future__ import annotations

from typing import Any

VERSION = "2026-07-26.1"

ENTRIES: list[dict[str, Any]] = [
    {
        "allowlist_id": "billing.invoices.store",
        "file": "app/billing/gst_invoice.py",
        "line_or_symbol": "_STORE",
        "path_pattern": "data/invoices.jsonl",
        "store_id": "billing.invoices",
        "access_modes": ["APPEND", "REWRITE", "READ", "CREATE"],
        "reason": (
            "Rule-46 sequential invoice ledger. Append-only JSONL inside the "
            "checkout; a git reset --hard would destroy issued invoice numbers."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "billing",
        "production_relevance": "LIVE",
        "review_condition": (
            "Any change to invoice numbering, VOID semantics or the ledger path "
            "must re-verify test_billing_truth_2026.py."
        ),
    },
    {
        "allowlist_id": "billing.invoices.lock",
        "file": "app/billing/gst_invoice.py",
        "line_or_symbol": "lock_path",
        "path_pattern": "data/invoices.jsonl.lock",
        "store_id": "billing.invoices",
        "access_modes": ["LOCK"],
        "reason": (
            "Cross-process lock for the invoice ledger. Mapped to the SAME store "
            "as the data it protects, not a separate family."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "billing",
        "production_relevance": "LIVE",
        "review_condition": (
            "Lock and ledger must not be split across filesystems during "
            "migration or os.replace stops being atomic."
        ),
    },
    {
        "allowlist_id": "billing.upi_payments.store",
        "file": "app/platform/upi_payments.py",
        "line_or_symbol": "_STORE",
        "path_pattern": "data/upi_payments.json",
        "store_id": "billing.upi_payments",
        "access_modes": ["REWRITE", "READ", "CREATE"],
        "reason": "Manual UPI is the primary payment path; this file records received payments.",
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "billing",
        "production_relevance": "LIVE",
        "review_condition": "UPI_AUTO_ACTIVATE stays 0; activation-policy change needs owner sign-off.",
    },
    {
        "allowlist_id": "billing.upi_config.store",
        "file": "app/platform/upi_config.py",
        "line_or_symbol": "_STORE",
        "path_pattern": "data/platform_upi.json",
        "store_id": "billing.upi_payments",
        "access_modes": ["REWRITE", "READ", "CREATE"],
        "reason": (
            "Platform UPI configuration. Same authority as upi_payments, so it is "
            "NOT a separate logical family."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "billing",
        "production_relevance": "LIVE",
        "review_condition": "Never store a secret here beyond the public payee identifier.",
    },
    {
        "allowlist_id": "compliance.email_suppression.store",
        "file": "app/platform/email_unsub.py",
        # `_STORE` until wave A3 retired the module constant. The declaration must
        # name the symbol the SCANNER emits, which is now the resolver function.
        "line_or_symbol": "_store_path",
        "path_pattern": "data/email_suppression.jsonl",
        "store_id": "compliance.email_suppression",
        "access_modes": ["APPEND", "READ", "CREATE"],
        "reason": (
            "Canonical suppression authority (ADR-144). Losing it re-enables "
            "outreach to opted-out recipients, which is a DPDP breach, not just "
            "data loss."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "compliance",
        "production_relevance": "LIVE",
        "review_condition": "Suppression stays fail-closed; no second suppression system.",
    },
    {
        "allowlist_id": "compliance.dpdp_audit.store",
        "file": "app/platform/dpdp.py",
        "line_or_symbol": "_AUDIT_FILE",
        "path_pattern": "data/dpdp_audit.jsonl",
        "store_id": "compliance.dpdp_audit",
        "access_modes": ["APPEND", "READ", "CREATE"],
        "reason": "DPDP Act 2023 audit trail. Statutory record.",
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "compliance",
        "production_relevance": "LIVE",
        "review_condition": (
            "Append-only; entries must never be rewritten or pruned outside the "
            "documented retention rule."
        ),
    },
    {
        "allowlist_id": "compliance.dpdp_requests.store",
        "file": "app/platform/dpdp.py",
        "line_or_symbol": "_REQUESTS_FILE",
        "path_pattern": "data/dpdp_requests.jsonl",
        "store_id": "compliance.dpdp_audit",
        # REPLACE added 2026-07-27 (owner-authorised operation correction, not a
        # new store): `_atomic_write_lines(path, lines)` writes
        # `path + ".tmp_dpdp"` and then `os.replace(tmp, path)` — the durable
        # authority is rewritten atomically. The entry always covered this file;
        # only the declared operation set was under-stated.
        "access_modes": ["APPEND", "READ", "CREATE", "REPLACE"],
        "reason": (
            "Data-subject access/erasure requests. Same statutory authority as the "
            "audit trail, so one logical family covers both files."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "compliance",
        "production_relevance": "LIVE",
        "review_condition": "Erasure requests must remain traceable after migration.",
    },
    {
        "allowlist_id": "customers.identity.store",
        "file": "app/marketing/clients_store.py",
        "line_or_symbol": "path",
        "path_pattern": "data/marketing_clients.jsonl",
        "store_id": "customers.identity",
        "access_modes": ["REWRITE", "READ", "CREATE", "APPEND"],
        "reason": (
            "Customer registry. The only paying customer's record lives here and "
            "cross-client isolation depends on it."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Customer-isolation invariant must be re-verified after any path change.",
    },
    {
        "allowlist_id": "customers.identity.atomic_tmp",
        "file": "app/marketing/clients_store.py",
        "line_or_symbol": "tmp",
        "path_pattern": "data/marketing_clients.jsonl.tmp",
        "store_id": "customers.identity",
        "access_modes": ["REWRITE", "REPLACE"],
        "reason": (
            "Atomic-rewrite temp file for the customer registry. A temp file is not "
            "its own logical family."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Temp and target must stay on ONE filesystem.",
    },
    # --- external agent missions (PR #147, dev-control) -----------------------
    # Arrived on main after this branch's baseline was frozen. The ratchet found
    # them the first time it actually executed in CI, so they are classified
    # here rather than absorbed into the debt baseline: they are NEW code, and
    # baseline growth without a detector change is new debt, not new sight.
    {
        "allowlist_id": "devcontrol.external_missions.root",
        "file": "app/dev_control/external_agents/cas.py",
        "line_or_symbol": "mission_root",
        "path_pattern": "data/external_missions",
        "store_id": "devcontrol.external_missions",
        "access_modes": ["CREATE"],
        "reason": (
            "Root directory for external-agent mission state. Created on demand by "
            "the file-lock CAS backend; overridable via EXTERNAL_MISSION_DIR."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "dev-control",
        "production_relevance": "LIVE",
        "review_condition": (
            "EXTERNAL_MISSION_DIR must resolve OUTSIDE the checkout in production, "
            "or move behind app/platform/runtime_data.py. The module's own docstring "
            "notes container replacement does not preserve ./data."
        ),
    },
    {
        "allowlist_id": "devcontrol.external_missions.store",
        "file": "app/dev_control/external_agents/store.py",
        "line_or_symbol": "_mission_path",
        "path_pattern": "data/external_missions",
        "store_id": "devcontrol.external_missions",
        "access_modes": ["REPLACE"],
        "reason": (
            "Per-mission JSON documents (<root>/<mission_id>.json), written via "
            "_atomic_write -> os.replace(tmp, path) from six call sites "
            "(save/claim/heartbeat/complete/fail/sweep)."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "dev-control",
        "production_relevance": "LIVE",
        "review_condition": (
            "Atomic temp and target must stay on one filesystem; a deploy that "
            "resets the checkout must not destroy in-flight mission state."
        ),
    },
    {
        "allowlist_id": "devcontrol.external_missions.mission_call_sites",
        "file": "app/dev_control/external_agents/store.py",
        "line_or_symbol": "path",
        "path_pattern": "data/external_missions",
        "store_id": "devcontrol.external_missions",
        "access_modes": ["CREATE", "READ"],
        "reason": (
            "The same per-mission documents as devcontrol.external_missions.store, "
            "reached through `path = _mission_path(mission_id)` at the create and "
            "load call sites. One store, not a second family: the REPLACE entry "
            "declared the writer and left the directory creation and the two reads "
            "undeclared."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "dev-control",
        "production_relevance": "LIVE",
        "review_condition": (
            "Must move with devcontrol.external_missions.store — a read that "
            "outlives its writer's root points at an empty directory and reports "
            "'no such mission' instead of failing."
        ),
    },
    {
        "allowlist_id": "devcontrol.external_missions.events",
        "file": "app/dev_control/external_agents/store.py",
        "line_or_symbol": "p",
        "path_pattern": "data/external_missions/events.jsonl",
        "store_id": "devcontrol.external_missions",
        "access_modes": ["CREATE"],
        "reason": (
            "Mission event log written beside the per-mission documents "
            "(`_events_path() -> _root() / 'events.jsonl'`). Same root, same "
            "cutover boundary, so it is not its own family."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "dev-control",
        "production_relevance": "LIVE",
        "review_condition": (
            "Append-only history; the events log must not be split from the "
            "mission documents it narrates."
        ),
    },
    # --- calling safety (this branch) ---------------------------------------
    # The manifest gained telephony.voice_kill_switch and telephony.call_recordings
    # in the same commit that rewrote the kill-switch reader and writer. Families
    # without entries left those writers UNDECLARED, so they are classified here
    # rather than absorbed into the debt baseline: writers authored by the change
    # under review are new debt, not newly visible debt.
    {
        "allowlist_id": "telephony.voice_kill_switch.authority",
        "file": "app/telephony/voice_launch.py",
        "line_or_symbol": "p",
        "path_pattern": "data/voice_launch_kill.json",
        "store_id": "telephony.voice_kill_switch",
        "access_modes": ["READ", "CREATE"],
        "reason": (
            "Emergency kill-switch authority file (VOICE_LAUNCH_KILL_FILE, "
            "defaulting INSIDE the checkout). Read by admin_kill_status() and "
            "created by the writer before the atomic flip."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "telephony",
        "production_relevance": "LIVE",
        "review_condition": (
            "The reader must stay FAIL-CLOSED: missing, unreadable, malformed or "
            "out-of-root all ENGAGE the kill. Any path change must keep the file "
            "outside a tree that a deploy resets, or losing it silently "
            "disengages an emergency control."
        ),
    },
    {
        "allowlist_id": "telephony.voice_kill_switch.atomic_tmp",
        "file": "app/telephony/voice_launch.py",
        "line_or_symbol": "tmp",
        "path_pattern": "data/voice_launch_kill.json.tmp",
        "store_id": "telephony.voice_kill_switch",
        "access_modes": ["REWRITE", "REPLACE", "DELETE"],
        "reason": (
            "Same-directory temp companion for the kill-switch flip "
            "(`p.with_name(p.name + '.tmp_kill')` -> fsync -> os.replace), plus "
            "the stale-temp cleanup. A temp file is not its own logical family."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "telephony",
        "production_relevance": "LIVE",
        "review_condition": (
            "Temp and target must stay on ONE filesystem or os.replace stops "
            "being atomic and an interrupted flip leaves truncated JSON — which "
            "the fail-closed reader treats as ENGAGED, so the failure mode is "
            "safe but must not become routine."
        ),
    },
    {
        "allowlist_id": "telephony.call_recordings.dir",
        "file": "app/telephony/voice_launch.py",
        "line_or_symbol": "d",
        "path_pattern": "data/recordings",
        "store_id": "telephony.call_recordings",
        "access_modes": ["CREATE"],
        "reason": (
            "Recording directory (RECORDINGS_DIR) created on demand by the "
            "recording-path health probe. Retention-governed evidence."
        ),
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "compliance",
        "production_relevance": "LIVE",
        "review_condition": (
            "90-day recording retention is governed by policy elsewhere; a path "
            "change must carry the retention sweep with it, and recordings must "
            "not live in a tree a deploy resets."
        ),
    },
]

__all__ = ["VERSION", "ENTRIES"]
