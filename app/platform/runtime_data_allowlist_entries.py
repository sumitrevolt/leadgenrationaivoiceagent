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

VERSION = "2026-08-06.1"

ENTRIES: list[dict[str, Any]] = [
    {
        "allowlist_id": "billing.invoices.store",
        "file": "app/billing/gst_invoice.py",
        # `_STORE` until wave A5 retired the module constant. The declaration must
        # name the symbol the SCANNER emits, which is now the resolver function.
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
        "line_or_symbol": "_lock_path",
        "path_pattern": "data/invoices.jsonl.lock",
        "store_id": "billing.invoices",
        "access_modes": ["LOCK", "CREATE", "REWRITE"],
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
        # `path + ".tmp_dpdp"` and then `os.replace(tmp, path)` â€” the durable
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
        "line_or_symbol": "_CLIENTS_FILE",
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
        "access_modes": ["REWRITE", "REPLACE", "CREATE"],
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
            "or cutover via app/platform/runtime_data_authority (A8 wires the default "
            "through resolve_store_path; bytes still live in-checkout until cutover)."
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
            "Must move with devcontrol.external_missions.store â€” a read that "
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
        "allowlist_id": "platform.workforce_memory.entries",
        "file": "app/platform/workforce_memory.py",
        "line_or_symbol": "entries_path",
        "path_pattern": "entries.jsonl",
        "store_id": "platform.workforce_memory",
        "access_modes": ["APPEND", "READ", "CREATE", "REWRITE"],
        "reason": (
            "Per-STAFF agent entries.jsonl (L0–L3 layered memory). Append on remember; "
            "soft trim may rewrite; inspect/recall read."
        ),
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": (
            "Must stay agent-scoped (STAFF id sanitised). Never write customer lead PII "
            "by default; DPDP erase uses purge_agent. Chat/L0 visibility forced private."
        ),
    },
    {
        "allowlist_id": "platform.workforce_memory.entries_helper_read",
        "file": "app/platform/workforce_memory.py",
        "line_or_symbol": "_entries_path",
        "path_pattern": "entries.jsonl",
        "store_id": "platform.workforce_memory",
        "access_modes": ["READ"],
        "reason": (
            "Tenant-aware _read_entries delegates to _read_entries_path using the same "
            "per-agent entries.jsonl authority."
        ),
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": (
            "The resolved path must remain under the validated agent and tenant scope; "
            "never fall back across tenants."
        ),
    },
    {
        "allowlist_id": "platform.workforce_memory.tenant_scope_directory_read",
        "file": "app/platform/workforce_memory.py",
        "line_or_symbol": "scope_path",
        "path_pattern": "entries.jsonl",
        "store_id": "platform.workforce_memory",
        "access_modes": ["READ"],
        "reason": (
            "Status traversal (hub_snapshot) reads tenant-scope entries.jsonl inside "
            "each STAFF memory root, gated by _contained_under."
        ),
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": (
            "Directory names stay hashed/validated scope identifiers; traversal must not "
            "read another agent root or expose tenant identifiers."
        ),
    },
    {
        "allowlist_id": "platform.workforce_memory.prune",
        "file": "app/platform/workforce_memory.py",
        "line_or_symbol": "prune_path",
        "path_pattern": "entries.jsonl",
        "store_id": "platform.workforce_memory",
        "access_modes": ["REWRITE", "READ"],
        "reason": "TTL prune rewrite of L0/L1 rows in per-agent entries.jsonl.",
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Default dry_run=true on admin API; never prune L2/L3.",
    },
    {
        "allowlist_id": "platform.workforce_memory.root_fn",
        "file": "app/platform/workforce_memory.py",
        "line_or_symbol": "_root",
        "path_pattern": "workforce_memory",
        "store_id": "platform.workforce_memory",
        "access_modes": ["CREATE", "READ"],
        "reason": "Store root resolver used by makedirs / equipments / shared.",
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Returns _ROOT_DEFAULT unless WORKFORCE_MEMORY_DIR override.",
    },
    {
        "allowlist_id": "platform.workforce_memory.equipments",
        "file": "app/platform/workforce_memory.py",
        "line_or_symbol": "equip_path",
        "path_pattern": "equipments.json",
        "store_id": "platform.workforce_memory",
        "access_modes": ["REWRITE", "READ", "CREATE"],
        "reason": "Admin equip/loadout map (agent_id → shared entry ids).",
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Equip is admin-only; target agent must pass asset bindings ACL.",
    },
    {
        "allowlist_id": "platform.workforce_memory.persona",
        "file": "app/platform/workforce_memory.py",
        "line_or_symbol": "persona_path",
        "path_pattern": "persona.md",
        "store_id": "platform.workforce_memory",
        "access_modes": ["READ", "CREATE", "REWRITE"],
        "reason": "Human-readable L3 persona.md upper layer (progressive disclosure).",
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Persona is structure-only; evidence stays in L0/refs.",
    },
    {
        "allowlist_id": "platform.workforce_memory.agent_dir",
        "file": "app/platform/workforce_memory.py",
        "line_or_symbol": "agent_dir",
        "path_pattern": "agent_id",
        "store_id": "platform.workforce_memory",
        "access_modes": ["DELETE", "CREATE"],
        "reason": (
            "Per-agent directory create (remember) and purge_agent rmtree (DPDP/ops erase)."
        ),
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": (
            "DELETE is admin-gated via /api/workforce-memory/purge and irreversible for "
            "that agent tree. Agent id must pass _safe_agent."
        ),
    },
    {
        "allowlist_id": "platform.workforce_memory.refs_dir",
        "file": "app/platform/workforce_memory.py",
        "line_or_symbol": "rd",
        "path_pattern": "refs",
        "store_id": "platform.workforce_memory",
        "access_modes": ["CREATE"],
        "reason": "Create refs/ directory before writing offloaded evidence markdown.",
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Directory only; evidence files use ref_path symbol.",
    },
    {
        "allowlist_id": "platform.workforce_memory.shared_dir",
        "file": "app/platform/workforce_memory.py",
        "line_or_symbol": "_shared_dir",
        "path_pattern": "_shared",
        "store_id": "platform.workforce_memory",
        "access_modes": ["CREATE"],
        "reason": "Create _shared/ directory for team-visible skill/wiki mirror.",
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "No customer tenant data; STAFF team loadout only.",
    },
    {
        "allowlist_id": "platform.workforce_memory.shared",
        "file": "app/platform/workforce_memory.py",
        "line_or_symbol": "shared_path",
        "path_pattern": "entries.jsonl",
        "store_id": "platform.workforce_memory",
        "access_modes": ["APPEND", "READ", "CREATE"],
        "reason": "Team-visible skill/wiki mirror for admin equip/loadout.",
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Only skill/wiki with visibility=team may mirror here; chat/L0 never.",
    },
    {
        "allowlist_id": "platform.workforce_memory.refs",
        "file": "app/platform/workforce_memory.py",
        "line_or_symbol": "ref_path",
        "path_pattern": "node_id",
        "store_id": "platform.workforce_memory",
        "access_modes": ["CREATE", "REWRITE", "READ"],
        "reason": "Offloaded evidence refs/{node_id}.md for drill-down (TencentDB pattern).",
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "node_id is hex-generated; drilldown sanitises input.",
    },
    {
        "allowlist_id": "marketing.brand_kits.path",
        "file": "app/marketing/brand_kit.py",
        # The scanner's symbol table is per-FILE, so the generic name `path`
        # resolves from get_brand's assignment and the DELETE would inherit an
        # opaque expression. The destructive path carries its own symbol.
        "line_or_symbol": "brand_path",
        # Must match what the SCANNER emits for this symbol, not the human-readable
        # shape: the path is computed, so the detected expression is the call itself.
        # It resolves to data/brand_kits/<_safe_id(client_id)>.json.
        # The gate matches the declared basename against the RESOLVED expression,
        # which is os.path.join(_BRAND_DIR, ...). _BRAND_DIR is the store root
        # constant (= os.path.join("data", "brand_kits")); tests monkeypatch it, so
        # inlining the literal here would break per-test isolation and point a real
        # DELETE at the shared data dir. Naming the constant is the honest match.
        "path_pattern": "_BRAND_DIR",
        "store_id": "marketing.brand_kits",
        "access_modes": ["READ", "CREATE", "REWRITE", "DELETE"],
        "reason": (
            "Per-tenant brand profile (colours, logo, handles) used to auto-brand "
            "posters and content packs. save_brand() creates/rewrites it; "
            "delete_brand() removes it during admin customer removal so a removed "
            "customer leaves no brand assets behind (DPDP purge)."
        ),
        "migration_tier": 2,
        "target_change_set": "runtime-data-cutover-wave-2",
        "owner": "marketing",
        "production_relevance": "LIVE",
        "review_condition": (
            "DELETE is irreversible and admin-gated: it must stay behind the "
            "confirm-required remove-customer path and must never be reachable "
            "from a customer-facing or unauthenticated route. The client_id is "
            "sanitised by _safe_id() before it reaches the filesystem - any change "
            "there is a path-traversal review, since the id arrives from a URL."
        ),
    },
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
            "being atomic and an interrupted flip leaves truncated JSON â€” which "
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
            "recording-path health probe. Retention-governed evidence. A9 wires "
            "the default through resolve_store_path; bytes still live in-checkout "
            "until host cutover."
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
    {
        "allowlist_id": "ops.owner_email_canary.dir",
        "file": "app/platform/owner_email_canary.py",
        "line_or_symbol": "path",
        "path_pattern": "data/owner_email_canary",
        "store_id": "ops.owner_email_canary",
        "access_modes": ["CREATE", "READ"],
        "reason": (
            "Directory for append-only owner-inbox email canary attempts. "
            "Created on demand before the first canary write. Recipient is "
            "masked; losing the ledger only forces a fresh one-shot canary."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "ops",
        "production_relevance": "LIVE",
        "review_condition": (
            "Must remain append-only with masked recipient + idempotency key; "
            "never enable AUTO_EMAIL_OUTREACH from this store."
        ),
    },
    {
        "allowlist_id": "ops.office_briefing.owner_notified_claim",
        "file": "app/platform/office_briefing.py",
        "line_or_symbol": "_notification_path",
        "path_pattern": "owner-notified",
        "store_id": "ops.office_briefing",
        "access_modes": ["READ", "DELETE"],
        "reason": (
            "At-most-once daily owner ntfy claim for the Hot Queue brief "
            "(data/office_briefing/<date>.owner-notified). O_EXCL create is "
            "scanned as READ; DELETE releases the claim only after notify "
            "retries fail so the next worker can retry the same day."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "ops",
        "production_relevance": "LIVE",
        "review_condition": (
            "Claim only — never auto-send prospect contact; losing the marker "
            "may re-push the same-day /app/inbox reminder and nothing else."
        ),
    },
    {
        "allowlist_id": "ops.hot_queue_owner_pack.csv",
        "file": "app/platform/hot_queue_owner_pack.py",
        "line_or_symbol": "csv_path",
        "path_pattern": "f\"data/hot_queue_for_owner_{today}.csv\"",
        "store_id": "ops.hot_queue_owner_pack_csv",
        "access_modes": ["REWRITE"],
        "reason": (
            "ADR-OWNER-1: daily CSV of /api/ops/hotqueue rows for the owner "
            "to import into a phone/CRM and click wa.me links directly. "
            "Re-written each morning by the 09:00 IST scheduled job; only "
            "the latest copy is kept. No prospect PII leaves this file."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "ops",
        "production_relevance": "LIVE",
        "review_condition": (
            "Must remain owner-local (no email/ntfy auto-attach); losing "
            "the file just means the next-day job regenerates it."
        ),
    },
    {
        "allowlist_id": "ops.hot_queue_owner_pack.md",
        "file": "app/platform/hot_queue_owner_pack.py",
        "line_or_symbol": "md_path",
        "path_pattern": "f\"data/hot_queue_for_owner_{today}.md\"",
        "store_id": "ops.hot_queue_owner_pack_md",
        "access_modes": ["REWRITE"],
        "reason": (
            "ADR-OWNER-1: daily markdown of the same top-15 hot leads as "
            "the CSV, with clickable wa.me links. Same lifecycle as the "
            "CSV (one day, owner-local, re-written each morning)."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "ops",
        "production_relevance": "LIVE",
        "review_condition": (
            "Same as the CSV entry — must stay owner-local; only the "
            "top-15 subset is exposed to reduce PII surface if shared."
        ),
    },
    {
        "allowlist_id": "governance.mission_control.ledger",
        "file": "app/platform/mission_control.py",
        "line_or_symbol": "_LEDGER",
        "path_pattern": "data/mission_control/ledger.jsonl",
        "store_id": "governance.mission_control",
        "access_modes": ["APPEND", "CREATE", "READ"],
        "reason": (
            "Append-only mission/decision ledger for chat-first Owner OS control plane. "
            "Chat history alone is not system state."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "governance",
        "production_relevance": "LIVE",
        "review_condition": (
            "Keep append-only + file_lock; never unlock RED outbound from this ledger; "
            "idempotency_key required on create."
        ),
    },
    {
        "allowlist_id": "governance.mission_control.missions_dir",
        "file": "app/platform/mission_control.py",
        "line_or_symbol": "_MISSIONS",
        "path_pattern": "data/mission_control/missions",
        "store_id": "governance.mission_control",
        "access_modes": ["CREATE", "READ"],
        "reason": "Per-mission JSON packet directory under Owner OS mission control.",
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "governance",
        "production_relevance": "LIVE",
        "review_condition": "Mission files stay tenant/owner scoped; no fake executor session IDs.",
    },
    {
        "allowlist_id": "governance.mission_control.idempotency",
        "file": "app/platform/mission_control.py",
        "line_or_symbol": "_IDEM_INDEX",
        "path_pattern": "data/mission_control/idempotency_index.json",
        "store_id": "governance.mission_control",
        "access_modes": ["REWRITE", "CREATE", "READ"],
        "reason": (
            "Durable full-key idempotency index (not a scan-cap). Written under the "
            "same ledger file_lock as mission create."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "governance",
        "production_relevance": "LIVE",
        "review_condition": "Index updates must stay inside ledger lock; no correlation_id auto-keys.",
    },
    {
        "allowlist_id": "governance.mission_control.mission_file",
        "file": "app/platform/mission_control.py",
        "line_or_symbol": "path",
        "path_pattern": '_MISSIONS / f"{mid}.json"',
        "store_id": "governance.mission_control",
        "access_modes": ["REWRITE", "CREATE", "READ"],
        "reason": "Individual mission JSON rewrite/read via _write_mission / _read_mission.",
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "governance",
        "production_relevance": "LIVE",
        "review_condition": "AMBER mutations require confirm=true; chat path must park AMBER.",
    },
    {
        "allowlist_id": "sales.prospects.backfill.source",
        "file": "scripts/backfill_score_v2.py",
        "line_or_symbol": "_SOURCE",
        "path_pattern": "data/prospects.jsonl",
        "store_id": "sales.prospects",
        "access_modes": ["READ"],
        "reason": (
            "Prospect Score V2 backfill reads the prospect store READ-ONLY for scoring; "
            "source is NEVER mutated (sidecar audit store only)."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "sales",
        "production_relevance": "LIVE",
        "review_condition": (
            "Backfill must stay read-only on prospects.jsonl; any write to the source "
            "store from this script is a regression."
        ),
    },
    {
        "allowlist_id": "sales.prospects.backfill.sidecar",
        "file": "scripts/backfill_score_v2.py",
        "line_or_symbol": "_SIDECAR",
        "path_pattern": "data/prospect_scores_v2.jsonl",
        "store_id": "sales.prospects",
        "access_modes": ["READ", "APPEND", "REWRITE"],
        "reason": (
            "Append-only sidecar audit store for Prospect Score V2 (keyed by prospect id). "
            "Derived from the prospect store; rollback restores from data/backups."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "sales",
        "production_relevance": "LIVE",
        "review_condition": (
            "Sidecar stays append-only + idempotent (score_version re-score skipped); "
            "source prospects.jsonl untouched."
        ),
    },
    {
        "allowlist_id": "sales.prospects.backfill.backup_dir",
        "file": "scripts/backfill_score_v2.py",
        "line_or_symbol": "_BACKUP_DIR",
        "path_pattern": "data/backups",
        "store_id": "sales.prospects",
        "access_modes": ["CREATE", "READ"],
        "reason": "Backup directory for the sidecar audit store (prospect_scores_v2.bak-<ts>.jsonl).",
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "sales",
        "production_relevance": "LIVE",
        "review_condition": "Backups are checkpoint-only; restoring must target the sidecar, never the source store.",
    },
    {
        "allowlist_id": "sales.prospects.backfill.backup_write",
        "file": "scripts/backfill_score_v2.py",
        "line_or_symbol": "dest",
        "path_pattern": "data/backups/prospect_scores_v2.bak",
        "store_id": "sales.prospects",
        "access_modes": ["REWRITE"],
        "reason": "Checkpoint write of the sidecar before a bounded backfill batch.",
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "sales",
        "production_relevance": "LIVE",
        "review_condition": "Backup path derives from _BACKUP_DIR; never writes to the prospect source store.",
    },
    {
        "allowlist_id": "sales.prospects.backfill.backup_read",
        "file": "scripts/backfill_score_v2.py",
        "line_or_symbol": "src",
        "path_pattern": "data/backups/prospect_scores_v2.bak",
        "store_id": "sales.prospects",
        "access_modes": ["READ"],
        "reason": "Rollback reads the sidecar checkpoint to restore the audit store.",
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "sales",
        "production_relevance": "LIVE",
        "review_condition": "Rollback restores the sidecar store only; source prospects.jsonl must stay untouched.",
    },
    {
        "allowlist_id": "owner_os.coordination_hub.root",
        "file": "app/platform/coordination_hub_events.py",
        "line_or_symbol": "_ROOT",
        "path_pattern": "data/coordination_hub",
        "store_id": "owner_os.coordination_hub",
        "access_modes": ["CREATE"],
        "reason": (
            "Root for Coordination Hub presence/events/nonce projection files. "
            "Not a mission ledger or STAFF registry."
        ),
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "owner-os",
        "production_relevance": "CANARY",
        "review_condition": (
            "Flag COORDINATION_HUB_ENABLED default OFF; directory may be empty until canary."
        ),
    },
    {
        "allowlist_id": "owner_os.coordination_hub.events",
        "file": "app/platform/coordination_hub_events.py",
        "line_or_symbol": "_EVENTS",
        "path_pattern": "data/coordination_hub/events.jsonl",
        "store_id": "owner_os.coordination_hub",
        "access_modes": ["CREATE", "APPEND", "READ"],
        "reason": "Append-only Hub event log with provenance fields; never stores secrets.",
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "owner-os",
        "production_relevance": "CANARY",
        "review_condition": "Append-only; cutover with presence/nonce siblings.",
    },
    {
        "allowlist_id": "owner_os.coordination_hub.presence",
        "file": "app/platform/coordination_hub_events.py",
        "line_or_symbol": "_PRESENCE",
        "path_pattern": "data/coordination_hub/presence.json",
        "store_id": "owner_os.coordination_hub",
        "access_modes": ["REPLACE", "READ", "CREATE"],
        "reason": "Tool presence projection for Hub dashboard (not STAFF registry).",
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "owner-os",
        "production_relevance": "CANARY",
        "review_condition": "Atomic replace; tool ids only (cursor/claude/buzz).",
    },
    {
        "allowlist_id": "owner_os.coordination_hub.nonces",
        "file": "app/platform/coordination_hub_auth.py",
        "line_or_symbol": "_NONCE_FILE",
        "path_pattern": "data/coordination_hub/nonce_fps.jsonl",
        "store_id": "owner_os.coordination_hub",
        "access_modes": ["CREATE", "APPEND", "READ", "REWRITE"],
        "reason": "One-way nonce fingerprints for HMAC replay protection.",
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "owner-os",
        "production_relevance": "CANARY",
        "review_condition": "Fingerprints only — never store raw nonces or secrets.",
    },
    {
        "allowlist_id": "owner_os.coordination_hub.auth_root",
        "file": "app/platform/coordination_hub_auth.py",
        "line_or_symbol": "_HUB_ROOT",
        "path_pattern": "data/coordination_hub",
        "store_id": "owner_os.coordination_hub",
        "access_modes": ["CREATE"],
        "reason": "Auth module mkdir for nonce fingerprint sibling under Hub root.",
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "owner-os",
        "production_relevance": "CANARY",
        "review_condition": "Same family as events root; CREATE only.",
    },
    {
        "allowlist_id": "owner_os.coordination_hub.presence_tmp",
        "file": "app/platform/coordination_hub_events.py",
        "line_or_symbol": "_PRESENCE_TMP",
        "path_pattern": "data/coordination_hub/presence.json.tmp",
        "store_id": "owner_os.coordination_hub",
        "access_modes": ["CREATE", "REWRITE", "REPLACE"],
        "reason": "Atomic temp for presence.json rewrite before os.replace.",
        "migration_tier": 1,
        "target_change_set": "runtime-data-cutover-wave-1",
        "owner": "owner-os",
        "production_relevance": "CANARY",
        "review_condition": "Temp must colocate with presence.json on one filesystem.",
    },
    {
        "allowlist_id": "billing.campaign_offer_policy.store",
        "file": "app/marketing/campaign_offer_policy.py",
        "line_or_symbol": "path",
        "path_pattern": "data/campaign_offer_policies.jsonl",
        # Same authority as the offers/payments family: this decides WHICH package
        # an offer may quote, so it is commercial policy feeding the same billing
        # truth, not a separate domain.
        "store_id": "billing.upi_payments",
        "access_modes": ["CREATE", "READ"],
        "reason": (
            "Immutable versioned Campaign Offer Policy (#240) — binds a live outbound "
            "campaign/variant to the packages it may quote. Append-only: editing writes a "
            "NEW version so a message already in flight is never re-priced. `path = _store()` "
            "inside _write_all; CREATE is the os.makedirs before the atomic replace."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "billing",
        "production_relevance": "LIVE",
        "review_condition": (
            "Policy versions are immutable — a revision must APPEND, never rewrite a prior "
            "version. Prices are never stored here; packages.py stays the single source. Any "
            "change allowing package inference (niche/LLM/intent) needs owner sign-off."
        ),
    },
    {
        "allowlist_id": "billing.campaign_offer_policy.store_tmp",
        "file": "app/marketing/campaign_offer_policy.py",
        "line_or_symbol": "tmp",
        "path_pattern": 'f"{path}.tmp.{os.getpid()}"',
        "store_id": "billing.upi_payments",
        "access_modes": ["CREATE", "REWRITE", "REPLACE", "DELETE"],
        "reason": (
            "Atomic temp for the policy-store rewrite (tmp + fsync + os.replace). DELETE is "
            "the cleanup path when the write fails partway."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "billing",
        "production_relevance": "LIVE",
        "review_condition": (
            "Temp must colocate with the policy store on one filesystem. Mutating callers hold "
            "file_lock around read-modify-write; the write must NOT re-enter locked_rewrite."
        ),
    },
    {
        "allowlist_id": "billing.offers.store",
        "file": "app/marketing/offers.py",
        "line_or_symbol": "path",
        "path_pattern": "data/offers.jsonl",
        # Same authority as upi_payments (commercial quoting feeding payment
        # reconciliation), so NOT a separate logical family — mirrors how
        # billing.upi_config.store also files under billing.upi_payments.
        "store_id": "billing.upi_payments",
        "access_modes": ["CREATE", "READ"],
        "reason": (
            "Immutable commercial offers (orders) bound to a sales deal (#240). Holds the "
            "order_ref a bank credit is reconciled against, plus the package/amount frozen "
            "at issuance. `path = _store()` inside _write_all; CREATE is the os.makedirs that "
            "ensures data/ exists before the atomic replace."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "billing",
        "production_relevance": "LIVE",
        "review_condition": (
            "An issued offer's package_code/quoted_amount/currency are immutable — a revision "
            "must append a new order with supersedes_order_ref, never rewrite the original. "
            "Any change that lets a catalogue price mutate an issued quote needs owner sign-off."
        ),
    },
    {
        "allowlist_id": "billing.offers.store_tmp",
        "file": "app/marketing/offers.py",
        "line_or_symbol": "tmp",
        # Dynamic (pid-suffixed) temp — the declaration must name the expression
        # the scanner actually detects, not a glob.
        "path_pattern": 'f"{path}.tmp.{os.getpid()}"',
        "store_id": "billing.upi_payments",
        "access_modes": ["CREATE", "REWRITE", "REPLACE", "DELETE"],
        "reason": (
            "Atomic temp for the offers.jsonl rewrite (tmp + fsync + os.replace). DELETE is the "
            "cleanup path when the write fails partway."
        ),
        "migration_tier": 0,
        "target_change_set": "runtime-data-cutover-wave-0",
        "owner": "billing",
        "production_relevance": "LIVE",
        "review_condition": (
            "Temp must colocate with offers.jsonl on one filesystem. Callers hold file_lock "
            "around read-modify-write; the write itself must NOT re-enter locked_rewrite."
        ),
    },
    {
        "allowlist_id": "platform.memory_governance.rules_fn",
        "file": "app/platform/memory_governance.py",
        "line_or_symbol": "_rules_path",
        "path_pattern": (
            '(os.getenv("MEMORY_SUPPRESSION_PATH") or "").strip() or _RULES_PATH_DEFAULT'
        ),
        "store_id": "platform.memory_governance",
        "access_modes": ["APPEND", "READ", "CREATE", "REWRITE"],
        "reason": (
            "Do-not-remember rules JSONL (ADR-161). Path may be overridden via "
            "MEMORY_SUPPRESSION_PATH; default data/memory_suppression.jsonl."
        ),
        "migration_tier": 2,
        "target_change_set": "memory-stack-adr-161",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": (
            "Fail-open on damaged file for suppression matching (must not wipe all "
            "memory); durable write gate stays fail-closed when authority unreadable."
        ),
    },
    {
        "allowlist_id": "platform.memory_governance.rules_path_var",
        "file": "app/platform/memory_governance.py",
        "line_or_symbol": "path",
        "path_pattern": (
            '(os.getenv("MEMORY_SUPPRESSION_PATH") or "").strip() or _RULES_PATH_DEFAULT'
        ),
        "store_id": "platform.memory_governance",
        "access_modes": ["APPEND", "READ", "CREATE", "REWRITE"],
        "reason": (
            "Local `path = _rules_path()` call sites — resolver walks to the "
            "env-or-default expression, so path_pattern must match that form."
        ),
        "migration_tier": 2,
        "target_change_set": "memory-stack-adr-161",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Same store as rules_fn.",
    },
    {
        "allowlist_id": "platform.memory_governance.audit_fn",
        "file": "app/platform/memory_governance.py",
        "line_or_symbol": "_audit_path",
        "path_pattern": (
            '(os.getenv("MEMORY_GOVERNANCE_AUDIT_PATH") or "").strip() or _AUDIT_PATH_DEFAULT'
        ),
        "store_id": "platform.memory_governance",
        "access_modes": ["APPEND", "READ", "CREATE"],
        "reason": (
            "Governance audit JSONL (hashed matches only). Default "
            "data/memory_governance_audit.jsonl; override MEMORY_GOVERNANCE_AUDIT_PATH."
        ),
        "migration_tier": 2,
        "target_change_set": "memory-stack-adr-161",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Append-only; never store raw matched text — hash only.",
    },
    # --- Search Console rank snapshot (ADR-177, GSC pSEO observability) ------
    # INERT until GSC_ENABLED=1 + creds (staff-gsc-rank-daily beat, 00:30 IST).
    # New code on this branch, so classified here rather than absorbed into the
    # debt baseline: baseline growth without a detector change is new debt.
    {
        "allowlist_id": "marketing.gsc_rankings.daily",
        "file": "app/integrations/gsc.py",
        "line_or_symbol": "DAILY_JSONL",
        "path_pattern": "data/gsc_daily.jsonl",
        "store_id": "marketing.gsc_rankings",
        "access_modes": ["CREATE", "APPEND", "READ"],
        "reason": (
            "Search Console daily snapshot (clicks/impressions/avg-position) for "
            "pSEO observability. One APPEND per day from staff-gsc-rank-daily; "
            "rebuildable from the Search Console API, so not authoritative."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "LIVE",
        "review_condition": "Snapshot must stay append-only; data range checkpoints must keep the run idempotent across restarts.",
    },
    {
        "allowlist_id": "marketing.gsc_rankings.state",
        "file": "app/integrations/gsc.py",
        "line_or_symbol": "STATE_JSON",
        "path_pattern": "data/gsc_state.json",
        "store_id": "marketing.gsc_rankings",
        "access_modes": ["CREATE", "READ"],
        "reason": (
            "Run-state checkpoint (last snapshot date, data range) for the GSC "
            "snapshotter. Rebuildable from the API; never customer data."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "LIVE",
        "review_condition": "Must move with marketing.gsc_rankings.state_tmp — the atomic rewrite pair is one family.",
    },
    {
        "allowlist_id": "marketing.gsc_rankings.state_tmp",
        "file": "app/integrations/gsc.py",
        "line_or_symbol": "tmp",
        "path_pattern": "data/gsc_state.json.tmp",
        "store_id": "marketing.gsc_rankings",
        "access_modes": ["REWRITE", "REPLACE", "CREATE"],
        "reason": (
            "Atomic-rewrite temp for the GSC run-state checkpoint. A temp file "
            "is not its own logical family."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "LIVE",
        "review_condition": "Temp and target must stay on ONE filesystem.",
    },
    # 2026-08-12 — platform.staff_bus (31 STAFF Buzz bus; STAFF_BUS_ENABLED OFF)
    {
        "allowlist_id": "platform.staff_bus.root",
        "file": "app/platform/staff_bus/runtime.py",
        "line_or_symbol": "_root",
        "path_pattern": "override or _DEFAULT_ROOT",
        "store_id": "platform.staff_bus",
        "access_modes": ["CREATE"],
        "reason": (
            "Root directory for staff_bus events/idempotency/audit/DLQ. "
            "_DEFAULT_ROOT is data/staff_bus; created lazily; STAFF_BUS_ENABLED defaults OFF."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Never arm STAFF_BUS_ENABLED in prod without owner go-ahead; no key material in these files.",
    },
    {
        "allowlist_id": "platform.staff_bus.events",
        "file": "app/platform/staff_bus/runtime.py",
        "line_or_symbol": "_events_path",
        "path_pattern": "data/staff_bus/events.jsonl",
        "store_id": "platform.staff_bus",
        "access_modes": ["APPEND", "CREATE", "READ"],
        "reason": "Append-only staff_bus event ledger (Boss→team envelopes).",
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Append-only; correlation_id required; no outbound side effects from this file alone.",
    },
    {
        "allowlist_id": "platform.staff_bus.idempotency",
        "file": "app/platform/staff_bus/runtime.py",
        "line_or_symbol": "_idemp_path",
        "path_pattern": "data/staff_bus/idempotency.jsonl",
        "store_id": "platform.staff_bus",
        "access_modes": ["APPEND", "CREATE", "READ"],
        "reason": "Idempotency key ledger for staff_bus publish/dispatch.",
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Dedup keys only; never store secrets or auth_tag material.",
    },
    {
        "allowlist_id": "platform.staff_bus.idempotency_open",
        "file": "app/platform/staff_bus/runtime.py",
        "line_or_symbol": "path",
        "path_pattern": "data/staff_bus/idempotency.jsonl",
        "store_id": "platform.staff_bus",
        "access_modes": ["APPEND", "READ"],
        "reason": (
            "open(_idemp_path()) sites bind the path variable as 'path'; "
            "same store as platform.staff_bus.idempotency."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Must stay paired with _idemp_path entry; same file.",
    },
    {
        "allowlist_id": "platform.staff_bus.audit",
        "file": "app/platform/staff_bus/runtime.py",
        "line_or_symbol": "_audit_path",
        "path_pattern": "data/staff_bus/audit.jsonl",
        "store_id": "platform.staff_bus",
        "access_modes": ["APPEND", "CREATE", "READ"],
        "reason": "Append-only staff_bus governance/audit trail.",
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Audit only; RED refusals stay system-enforced elsewhere.",
    },
    {
        "allowlist_id": "platform.staff_bus.dlq",
        "file": "app/platform/staff_bus/runtime.py",
        "line_or_symbol": "_dlq_path",
        "path_pattern": "data/staff_bus/dlq.jsonl",
        "store_id": "platform.staff_bus",
        "access_modes": ["APPEND", "CREATE", "READ"],
        "reason": "Dead-letter queue for failed staff_bus envelopes.",
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Bounded DLQ; no auto-replay to customer outbound channels.",
    },
    {
        "allowlist_id": "platform.staff_bus.agent_poll.events",
        "file": "app/platform/staff_bus/agent_poll.py",
        "line_or_symbol": "path",
        "path_pattern": "data/staff_bus/events.jsonl",
        "store_id": "platform.staff_bus",
        "access_modes": ["READ"],
        "reason": (
            "AgentPoller reads bus events.jsonl to discover task.assigned events "
            "targeting a specific agent. Same store as platform.staff_bus.events; "
            "read-only — never writes or mutates the event ledger."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "platform",
        "production_relevance": "LIVE",
        "review_condition": "Read-only; bounded scan (last 500 lines); no side effects.",
    },
    # --- Marketing feature JSONL (2026-08-16; INERT flags, classified not tolerated)
    {
        "allowlist_id": "marketing.appointment_reminders.store",
        "file": "app/marketing/appointment_reminders.py",
        "line_or_symbol": "_STORE",
        "path_pattern": "data/appointment_reminders.jsonl",
        "store_id": "marketing.appointment_reminders",
        "access_modes": ["CREATE", "APPEND", "READ"],
        "reason": (
            "Appointment reminder sequence JSONL. INERT until BOOKING_REMINDERS=1; "
            "rebuildable by re-scheduling."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "LIVE",
        "review_condition": "Must stay append-only; no TRAI/DND bypass; WhatsApp cold stays OFF.",
    },
    {
        "allowlist_id": "marketing.customer_health.store",
        "file": "app/marketing/customer_health.py",
        "line_or_symbol": "_STORE",
        "path_pattern": "data/customer_health.jsonl",
        "store_id": "marketing.customer_health",
        "access_modes": ["CREATE", "APPEND", "READ"],
        "reason": (
            "Customer health score snapshots. Rebuildable from live client/payment "
            "signals. INERT until CLIENT_HEALTH_ALERTS=1."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "LIVE",
        "review_condition": "Scores must not fabricate revenue or paid_today.",
    },
    {
        "allowlist_id": "marketing.email_drips.definitions",
        "file": "app/marketing/email_drips.py",
        "line_or_symbol": "_DRIPS_STORE",
        "path_pattern": "data/email_drips.jsonl",
        "store_id": "marketing.email_drips",
        "access_modes": ["CREATE", "APPEND", "READ"],
        "reason": (
            "Email drip template definitions. Operator-rebuildable. No cold/bulk "
            "WhatsApp from this file."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "LIVE",
        "review_condition": "Drip send path must keep email warmup + suppression gates.",
    },
    {
        "allowlist_id": "marketing.content_engine.script_voice_gen.output_dir",
        "file": "app/content_engine/script_voice_gen.py",
        "line_or_symbol": "OUTPUT_DIR",
        "path_pattern": "data/content_gen",
        "store_id": "marketing.content_gen",
        "access_modes": ["CREATE", "REWRITE"],
        "reason": (
            "Script voice generation output directory. Created by os.makedirs at module load; "
            "contains generated scripts and voiceover files. Rebuildable from source topic prompts."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Sidecar output only; no customer PII beyond public script text.",
    },
    {
        "allowlist_id": "marketing.content_pipeline.producer.output_dir",
        "file": "app/content_pipeline/producer.py",
        "line_or_symbol": "OUTPUT_DIR",
        "path_pattern": "data/content_pipeline",
        "store_id": "marketing.content_pipeline",
        "access_modes": ["CREATE"],
        "reason": (
            "Content pipeline output directory. Created by os.makedirs at module load; "
            "contains generated scripts and voiceover files. Rebuildable from source topic prompts."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Sidecar output only; no customer PII beyond public script text.",
    },
    {
        "allowlist_id": "marketing.content_pipeline.producer.script_txt",
        "file": "app/content_pipeline/producer.py",
        "line_or_symbol": "script_path",
        "path_pattern": "data/content_pipeline/script.txt",
        "store_id": "marketing.content_pipeline",
        "access_modes": ["REWRITE"],
        "reason": (
            "Generated script text file output. Written by write_text() in main(); "
            "deterministic rebuild from topic prompt."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Output only; no customer data.",
    },
    {
        "allowlist_id": "marketing.content_os.engine.idempotency_lock",
        "file": "app/marketing/content_os/engine.py",
        "line_or_symbol": "lock_file",
        "path_pattern": "/opt/leadgen/media/content_os/last_run_",
        "store_id": "marketing.content_os",
        "access_modes": ["LOCK", "CREATE", "REWRITE"],
        "reason": (
            "Day-scoped idempotency lock file. Written by _mark_ran_today() via Path.write_text; "
            "read by _led_already_ran_today(). Same DATA_DIR store as queue/ledger."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Lock file only; no customer data.",
    },
    {
        "allowlist_id": "marketing.content_os.engine.idempotency_key_read",
        "file": "app/marketing/content_os/engine.py",
        "line_or_symbol": "p",
        "path_pattern": "/opt/leadgen/media/content_os/last_run_",
        "store_id": "marketing.content_os",
        "access_modes": ["LOCK", "READ"],
        "reason": (
            "Read of idempotency lock file in _led_already_ran_today(). "
            "Same DATA_DIR store as queue/ledger."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Lock file read only; no customer data.",
    },
    # --- command_center pilot dispatch scripts (offline tooling) ---------------
    {
        "allowlist_id": "command_center.pilot.dispatch.tasks_json_patches",
        "file": "command_center/patches/pilot_dispatch_0830_1520.py",
        "line_or_symbol": "tasks_path",
        "path_pattern": "command_center/data/tasks.json",
        "store_id": "command_center.pilot_tasks",
        "access_modes": ["READ", "REWRITE"],
        "reason": (
            "Pilot dispatch patch script reads/writes tasks.json for evidence updates. "
            "Offline admin tooling."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "operations",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Local admin script; no production customer data.",
    },
    {
        "allowlist_id": "command_center.pilot.dispatch.ledger_messages_jsonl",
        "file": "command_center/patches/pilot_dispatch_0830_1520.py",
        "line_or_symbol": "ledger_path",
        "path_pattern": "command_center/data/messages.jsonl",
        "store_id": "command_center.pilot_tasks",
        "access_modes": ["APPEND", "READ"],
        "reason": (
            "Pilot dispatch patch script appends evidence to messages.jsonl. "
            "Offline admin tooling."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "operations",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Local admin script; no production customer data.",
    },
    {
        "allowlist_id": "marketing.email_drips.runs",
        "file": "app/marketing/email_drips.py",
        "line_or_symbol": "_RUNS_STORE",
        "path_pattern": "data/email_drip_runs.jsonl",
        "store_id": "marketing.email_drips",
        "access_modes": ["CREATE", "APPEND", "READ"],
        "reason": "Per-customer drip run ledger. Idempotent re-entry; rebuildable.",
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "LIVE",
        "review_condition": "Runs must stay append-only; no silent resend storms.",
    },
    {
        "allowlist_id": "marketing.form_builder.forms",
        "file": "app/marketing/form_builder.py",
        "line_or_symbol": "_FORMS_STORE",
        "path_pattern": "data/forms.jsonl",
        "store_id": "marketing.form_builder",
        "access_modes": ["CREATE", "APPEND", "READ"],
        "reason": ("Form/survey definitions. INERT until FORM_BUILDER=1; API 503 when off."),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "LIVE",
        "review_condition": "Tenant isolation by client_id; DPDP minimisation on stored answers.",
    },
    {
        "allowlist_id": "marketing.form_builder.responses",
        "file": "app/marketing/form_builder.py",
        "line_or_symbol": "_RESPONSES_STORE",
        "path_pattern": "data/form_responses.jsonl",
        "store_id": "marketing.form_builder",
        "access_modes": ["CREATE", "APPEND", "READ"],
        "reason": ("Form response JSONL. INERT until FORM_BUILDER=1; API 503 when off."),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "LIVE",
        "review_condition": "Must stay tenant-scoped; no cross-client read.",
    },
    {
        "allowlist_id": "marketing.proposal_builder.store",
        "file": "app/marketing/proposal_builder.py",
        "line_or_symbol": "_STORE",
        "path_pattern": "data/proposals.jsonl",
        "store_id": "marketing.proposal_builder",
        "access_modes": ["CREATE", "APPEND", "READ"],
        "reason": (
            "Proposal/quote drafts. INERT until PROPOSAL_BUILDER=1; API 503 when "
            "off. Not a billing ledger."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "LIVE",
        "review_condition": "Must not auto-confirm UPI or mutate invoices.jsonl.",
    },
    {
        "allowlist_id": "marketing.review_sequences.store",
        "file": "app/marketing/review_automation.py",
        "line_or_symbol": "_STORE",
        "path_pattern": "data/review_sequences.jsonl",
        "store_id": "marketing.review_sequences",
        "access_modes": ["CREATE", "APPEND", "READ"],
        "reason": (
            "Google-review request sequences. Rebuildable by restarting a request. "
            "Module daily cap is the ban-safety bound."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "marketing",
        "production_relevance": "LIVE",
        "review_condition": "No fabricated ratings/testimonials; daily cap must stay.",
    },
    # 2026-08-23 — billing.promo_codes (platform promo/launch-code engine)
    {
        "allowlist_id": "billing.promo_codes.store",
        "file": "app/billing/promo_codes.py",
        "line_or_symbol": "_STORE",
        "path_pattern": "data/promo_codes.jsonl",
        "store_id": "billing.promo_codes",
        "access_modes": ["CREATE", "READ"],
        "reason": (
            "Promo definitions + applied-redemption ledger (launch offers, "
            "discount codes). Definitions are re-enterable via admin re-create; "
            "never holds customer PII beyond a normalized contact hash-key. "
            "CREATE is the os.makedirs ensuring data/ exists before replace."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "billing",
        "production_relevance": "LIVE",
        "review_condition": (
            "Writes go through the atomic tmp+replace pair only — never a bare append on this path."
        ),
    },
    {
        "allowlist_id": "billing.promo_codes.tmp",
        "file": "app/billing/promo_codes.py",
        "line_or_symbol": "tmp",
        # Dynamic (pid-suffixed) temp — declaration names the expression the
        # scanner actually detects, not a glob (offers.py precedent).
        "path_pattern": 'f"{_STORE}.tmp.{os.getpid()}"',
        "store_id": "billing.promo_codes",
        "access_modes": ["CREATE", "REWRITE", "REPLACE", "DELETE"],
        "reason": (
            "Atomic temp for the promo-store rewrite under file_lock. DELETE "
            "is the cleanup path when the write fails partway."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "billing",
        "production_relevance": "LIVE",
        "review_condition": "Temp and target must stay on ONE filesystem.",
    },
    # 2026-08-23 — marketing.affiliates referral paid-flip (revenue sprint)
    {
        "allowlist_id": "marketing.affiliates.referrals",
        "file": "app/marketing/affiliate.py",
        "line_or_symbol": "_REFERRALS",
        "path_pattern": "data/affiliate_referrals.jsonl",
        "store_id": "marketing.affiliates",
        "access_modes": ["CREATE", "APPEND", "READ"],
        "reason": (
            "Referral conversion ledger (lead→paid flip on payment activation, "
            "revenue sprint 2026-08-23). Legacy append-only family; the new "
            "paid-flip adds a locked atomic rewrite via its own tmp row."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "growth",
        "production_relevance": "LIVE",
        "review_condition": ("Flip only moves status lead→paid; never fabricates conversions."),
    },
    {
        "allowlist_id": "marketing.affiliates.referrals_tmp",
        "file": "app/marketing/affiliate.py",
        "line_or_symbol": "tmp",
        "path_pattern": 'f"{_REFERRALS}.tmp.{os.getpid()}"',
        "store_id": "marketing.affiliates",
        "access_modes": ["REWRITE", "REPLACE"],
        "reason": (
            "Atomic temp for the referral paid-flip rewrite (tmp + os.replace) under file_lock."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "growth",
        "production_relevance": "LIVE",
        "review_condition": "Temp and target must stay on ONE filesystem.",
    },
    # 2026-08-23 — sales.prospects TASK_LI-001 enrichment batch (Board-run, offline)
    {
        "allowlist_id": "sales.prospects.enrich.source",
        "file": "scripts/batch_enrich.py",
        "line_or_symbol": "in_file",
        "path_pattern": "data/hunter_leads/TASK_LI-001_top10.csv",
        "store_id": "sales.prospects",
        "access_modes": ["READ"],
        "reason": (
            "TASK_LI-001 enrichment reads the hunter CSV source READ-ONLY; "
            "one-shot offline script, never mutates the source."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "sales",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Source CSV must stay read-only in this script.",
    },
    {
        "allowlist_id": "sales.prospects.enrich.sink_flat",
        "file": "scripts/batch_enrich.py",
        "line_or_symbol": "out_file",
        "path_pattern": "data/enriched_prospects.jsonl",
        "store_id": "sales.prospects",
        "access_modes": ["CREATE", "APPEND"],
        "reason": (
            "Enrichment output sidecar (append-only jsonl). Rebuildable from "
            "source CSV + deterministic mapping — REBUILDABLE_CACHE class data."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "sales",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Append-only sink; no customer PII beyond public contact fields.",
    },
    {
        "allowlist_id": "sales.prospects.enrich.board_source",
        "file": "scripts/board_enrich_task.py",
        "line_or_symbol": "in_csv",
        "path_pattern": "data/hunter_leads/TASK_LI-001_top10.csv",
        "store_id": "sales.prospects",
        "access_modes": ["READ"],
        "reason": (
            "Board enrichment variant reads the same hunter CSV READ-ONLY. One-shot offline script."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "sales",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Source CSV must stay read-only in this script.",
    },
    {
        "allowlist_id": "sales.prospects.enrich.board_sink_dir",
        "file": "scripts/board_enrich_task.py",
        "line_or_symbol": "out_dir",
        "path_pattern": "data/enriched_prospects",
        "store_id": "sales.prospects",
        "access_modes": ["CREATE"],
        "reason": (
            "Enrichment output directory (os.makedirs) for per-task jsonl "
            "sidecars. Rebuildable from source CSV."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "sales",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Sidecar outputs only; no source mutation.",
    },
    {
        "allowlist_id": "sales.prospects.enrich.board_sink_file",
        "file": "scripts/board_enrich_task.py",
        "line_or_symbol": "out_jsonl",
        "path_pattern": "data/enriched_prospects/TASK_LI-001_enriched.jsonl",
        "store_id": "sales.prospects",
        "access_modes": ["CREATE", "REWRITE"],
        "reason": (
            "Per-task enriched output file (deterministic rebuild from CSV). "
            "REBUILDABLE_CACHE class data."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "sales",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Sidecar output only.",
    },
    {
        "allowlist_id": "sales.prospects.enrich.li001_src",
        "file": "scripts/enrich_task_li001.py",
        "line_or_symbol": "SRC",
        "path_pattern": "data/hunter_leads/TASK_LI-001_top10.csv",
        "store_id": "sales.prospects",
        "access_modes": ["READ"],
        "reason": (
            "Deterministic enrichment script reads the hunter CSV READ-ONLY. "
            "No fabrication: every output field derives from the source row."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "sales",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Source CSV must stay read-only in this script.",
    },
    {
        "allowlist_id": "sales.prospects.enrich.li001_dst",
        "file": "scripts/enrich_task_li001.py",
        "line_or_symbol": "DST",
        "path_pattern": "data/enriched_prospects/TASK_LI-001_enriched.jsonl",
        "store_id": "sales.prospects",
        "access_modes": ["CREATE", "REWRITE"],
        "reason": (
            "Enriched output jsonl — deterministic rebuild from the CSV source. "
            "os.makedirs on DST_DIR is the CREATE."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "sales",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Sidecar output only; overwrite semantics are idempotent.",
    },
    {
        "allowlist_id": "sales.prospects.enrich.li001_dstdir",
        "file": "scripts/enrich_task_li001.py",
        "line_or_symbol": "DST_DIR",
        "path_pattern": "data/enriched_prospects",
        "store_id": "sales.prospects",
        "access_modes": ["CREATE"],
        "reason": (
            "Output directory (os.makedirs exist_ok) for the enriched sidecar — "
            "rebuildable from the source CSV; same offline tooling family."
        ),
        "migration_tier": 3,
        "target_change_set": "runtime-data-cutover-wave-3",
        "owner": "sales",
        "production_relevance": "OFFLINE_TOOLING",
        "review_condition": "Directory creation only; no file writes at this symbol.",
    },
]

__all__ = ["VERSION", "ENTRIES"]
