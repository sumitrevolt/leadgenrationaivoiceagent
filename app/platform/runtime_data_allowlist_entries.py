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
        "line_or_symbol": "_STORE",
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
]

__all__ = ["VERSION", "ENTRIES"]
