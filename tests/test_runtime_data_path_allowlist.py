"""The allowlist must stay tied to live code and to real store families.

An allowlist nobody re-checks becomes a record of what used to be true. Each
check here corresponds to a way that has already gone wrong somewhere in this
repo: a path moved and the note didn't, an id was typo'd, a writer was filed as
read-only.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

from app.platform import runtime_data_allowlist as al
from app.platform import runtime_data_manifest as manifest
from app.platform import runtime_data_scan as scan

_REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def findings():
    from tests._runtime_data_scan_subprocess import scan_repo_in_subprocess

    return scan_repo_in_subprocess(_REPO)


def _entry(**over):
    base = {
        "allowlist_id": "x.y",
        "file": "app/billing/gst_invoice.py",
        "line_or_symbol": "_STORE",
        "path_pattern": "data/invoices.jsonl",
        "store_id": "billing.invoices",
        "access_modes": ["APPEND"],
        "reason": "r",
        "migration_tier": 0,
        "target_change_set": "wave-0",
        "owner": "billing",
        "production_relevance": "LIVE",
        "review_condition": "c",
    }
    base.update(over)
    return base


# ------------------------------------------------------------------- shipped


def test_shipped_allowlist_is_coherent(findings) -> None:
    problems = al.validate(findings=findings)
    assert problems == [], "allowlist problems:\n  " + "\n  ".join(problems)


def test_dpdp_requests_entry_declares_the_atomic_replace(findings) -> None:
    """The DPDP requests store is rewritten atomically, and the entry says so.

    `_atomic_write_lines(path, lines)` writes `path + ".tmp_dpdp"` and then
    `os.replace(tmp, path)`. The entry declared only APPEND/READ/CREATE, so a
    destructive operation on a Tier-0 statutory store was undeclared until the
    path-role fix made the destination visible. This test fails if REPLACE is
    dropped, if the entry drifts onto the audit file, or if the temp companion
    is mistaken for the durable authority.

    A3 turned `_REQUESTS_FILE` into a per-call resolver function; the allowlist
    symbol name is unchanged, and REPLACE findings must still bind to the
    requests file (never the sibling audit log).
    """
    entry = next(e for e in al.load() if e["allowlist_id"] == "compliance.dpdp_requests.store")
    assert "REPLACE" in entry["access_modes"]
    assert entry["file"] == "app/platform/dpdp.py"
    assert entry["line_or_symbol"] == "_REQUESTS_FILE"
    # Must bind to the requests file, never the sibling audit file.
    assert entry["path_pattern"] == "data/dpdp_requests.jsonl"

    real = [
        f
        for f in findings
        if f.get("file") == "app/platform/dpdp.py"
        and f.get("operation") == scan.REPLACE
        and (
            f.get("symbol") == "_REQUESTS_FILE"
            or "dpdp_requests" in str(f.get("resolved_path") or "")
            or "dpdp_requests" in str(f.get("path_expression") or "")
        )
    ]
    assert real, "no real REPLACE finding binds this entry"
    # The durable authority, not the temporary companion.
    for f in real:
        assert ".tmp_dpdp" not in str(f.get("resolved_path") or "")
        assert "dpdp_audit" not in str(f.get("resolved_path") or "")


def test_store_family_count_is_derived_not_typed() -> None:
    """I reported "4 store families" while listing five names.

    The count must come from the data, and the names must reconcile with it â€”
    a summary that disagrees with its own list is how a wrong number survives
    a review.
    """
    entries = al.load()
    families = {e["store_id"] for e in entries}
    # Derived facts, re-pinned when a family is genuinely added:
    # 2026-07-27 +2 entries / +1 family for devcontrol.external_missions.
    # 2026-07-28 +5 entries / +2 families: the two external-mission call-site
    # entries (same family, previously undeclared modes) and the calling-safety
    # writers this branch authored â€” telephony.voice_kill_switch (authority +
    # atomic temp) and telephony.call_recordings.
    # 2026-07-30 +1 entry / +1 family: ops.owner_email_canary (one-shot canary ledger).
    # 2026-07-31 +4 entries / +1 family: governance.mission_control (Owner OS chat missions).
    # 2026-07-31 +5 entries / +1 family: sales.prospects (Prospect Score V2 backfill sidecar).
    # 2026-08-02 +1 entry / +1 family: marketing.brand_kits — admin remove-customer
    # added a DELETE against the brand profile, and it was CLASSIFIED rather than
    # tolerated (nothing was added to the baseline debt file).
    # 2026-08-03 +10 entries / +1 family: platform.workforce_memory (ADR-154 hub for
    # the 31 agents). Also CLASSIFIED, not tolerated — baseline unchanged.
    # 2026-08-04 +4 entries / +1 family: owner_os.coordination_hub (ADR-150 thin
    # Owner OS projection — presence/events/nonces; not a second control plane).
    # 2026-08-04 +2 entries / +0 families: data/offers.jsonl and its atomic temp
    # (#240 immutable offer/order store). Filed under the EXISTING
    # billing.upi_payments family — commercial quoting feeding payment
    # reconciliation is the same authority, exactly as billing.upi_config.store
    # already does. CLASSIFIED, not tolerated: baseline debt unchanged.
    # 2026-08-05 +2 entries / +0 families: data/campaign_offer_policies.jsonl and
    # its atomic temp (#240 Campaign Offer Policy — immutable versioned commercial
    # authority). Also filed under billing.upi_payments: it decides WHICH package an
    # offer may quote, so it is the same billing authority, not a new domain.
    # 2026-08-05 +3 entries / +1 family: platform.memory_governance (ADR-158/161
    # do-not-remember rules + governance audit). CLASSIFIED, not tolerated.
    # 2026-08-06 +2 entries / +0 families: tenant-aware workforce-memory reads
    # (_entries_path and tenants_dir) stay in platform.workforce_memory.
    # 2026-08-11 +3 entries / +1 family: marketing.gsc_rankings (ADR-177 Search
    # Console rank snapshot — daily jsonl + state json + atomic tmp). CLASSIFIED.
    # 2026-08-12 +6 entries / +1 family: platform.staff_bus (31 STAFF Buzz bus
    # events/idempotency/audit/DLQ under STAFF_BUS_ENABLED OFF). CLASSIFIED.
    # 2026-08-14 +1 entry / +1 family: ops.office_briefing (Hot Queue daily
    # owner-notified claim). CLASSIFIED, not tolerated — baseline unchanged.
    # 2026-08-16 +8 entries / +6 families: marketing appointment/health/drips/
    # forms/proposals/review JSONL (INERT flags; classified, not tolerated).
    # 2026-08-24 +12 entries / +2 families: revenue-sprint batch —
    # billing.promo_codes (platform coupon engine) + marketing.affiliates
    # (referral kit) plus sales.prospects TASK_LI-001 enrichment tooling
    # entries re-bound to real code symbols; scratch temp_enrich_write.py
    # deleted instead of classified. CLASSIFIED, not tolerated.
    assert len(entries) == 92
    assert len(families) == 32, sorted(families)
    # Every entry must name a family that the manifest actually knows.
    known = {s["store_id"] for s in manifest.STORES}
    assert families <= known, sorted(families - known)
    assert families == {
        "billing.invoices",
        "billing.promo_codes",
        "billing.upi_payments",
        "compliance.dpdp_audit",
        "compliance.email_suppression",
        "customers.identity",
        "marketing.affiliates",
        "marketing.appointment_reminders",
        "marketing.brand_kits",
        "marketing.content_gen",
        "marketing.content_os",
        "marketing.content_pipeline",
        "marketing.customer_health",
        "marketing.email_drips",
        "marketing.form_builder",
        "marketing.gsc_rankings",
        "marketing.proposal_builder",
        "marketing.review_sequences",
        "platform.memory_governance",
        "platform.staff_bus",
        "platform.workforce_memory",
        "command_center.pilot_tasks",
        "devcontrol.external_missions",
        "governance.mission_control",
        "owner_os.coordination_hub",
        "ops.office_briefing",
        "ops.hot_queue_owner_pack_csv",
        "ops.hot_queue_owner_pack_md",
        "ops.owner_email_canary",
        "sales.prospects",
        "telephony.call_recordings",
        "telephony.voice_kill_switch",
    }
    # No alias: distinct manifest authorities, not renames of one another.
    # 12 since 2026-08-24: command_center joined (Pilot dispatch tasks store).
    assert len({f.split(".")[0] for f in families}) == 12


def test_every_entry_maps_to_a_real_store_family() -> None:
    known = {s["store_id"] for s in manifest.STORES}
    for e in al.load():
        assert e["store_id"] in known, f"{e['allowlist_id']} -> {e['store_id']}"


def test_no_blanket_file_entries() -> None:
    """A whole-file exception would excuse writes nobody reviewed."""
    for e in al.load():
        assert e["line_or_symbol"] not in ("*", "", None)
        assert not str(e["line_or_symbol"]).startswith("*")


def test_locks_map_to_the_store_they_protect() -> None:
    """A lock is not its own logical store, and must not drift from its data."""
    by_id = {e["allowlist_id"]: e for e in al.load()}
    lock = by_id["billing.invoices.lock"]
    data = by_id["billing.invoices.store"]
    assert lock["store_id"] == data["store_id"]


# ------------------------------------------------------------ rejection cases


def test_unknown_store_id_rejected() -> None:
    problems = al.validate([_entry(store_id="does.not.exist")])
    assert any("unknown store_id" in p for p in problems)


def test_missing_owner_rejected() -> None:
    e = _entry()
    del e["owner"]
    assert any("missing required fields" in p for p in al.validate([e]))


def test_missing_migration_wave_rejected() -> None:
    e = _entry()
    del e["migration_tier"]
    assert any("missing required fields" in p for p in al.validate([e]))


def test_missing_review_condition_rejected() -> None:
    e = _entry()
    del e["review_condition"]
    assert any("missing required fields" in p for p in al.validate([e]))


def test_duplicate_entries_rejected() -> None:
    e = _entry()
    problems = al.validate([e, copy.deepcopy(e)])
    assert any("duplicate allowlist_id" in p for p in problems)


def test_writer_against_immutable_store_rejected() -> None:
    problems = al.validate([_entry(store_id="static.legal_documents", access_modes=["REWRITE"])])
    assert any("immutable store" in p for p in problems)


def test_production_writer_filed_as_fixture_rejected() -> None:
    problems = al.validate([_entry(production_relevance="FIXTURE")])
    assert any("filed as FIXTURE" in p for p in problems)


def test_stale_entry_rejected(findings) -> None:
    """The entry survives; the code it excused does not."""
    stale = _entry(
        allowlist_id="stale.one",
        file="app/billing/gst_invoice.py",
        line_or_symbol="_SYMBOL_THAT_DOES_NOT_EXIST",
    )
    problems = al.validate([stale], findings=findings)
    assert any("STALE" in p for p in problems)


def test_operation_mismatch_rejected(findings) -> None:
    """Declaring READ over code that appends must not pass.

    This check found real mismatches in the first draft of the shipped
    allowlist â€” parent-directory CREATE calls that the entries had not
    declared â€” which is precisely why it exists.
    """
    narrow = _entry(allowlist_id="narrow", access_modes=["READ"])
    problems = al.validate([narrow], findings=findings)
    assert any("operation mismatch" in p for p in problems)


def test_declared_path_must_match_the_code() -> None:
    """The .json / .jsonl discrepancy that an outside reader caught.

    I declared `data/marketing_clients.json` for a store whose code says
    `os.path.join("data", "marketing_clients.jsonl")`. Every other check passed
    because nothing compared the declared PATH to the source. A substring test
    would still have missed it -- `.json` is a prefix of `.jsonl` -- so the
    basename must be followed by a non-filename character.
    """
    problems = al.validate([_entry(path_pattern="data/marketing_clients.json")])
    assert any("does not match the code" in p for p in problems)

    ok = al.validate([_entry(path_pattern="data/invoices.jsonl")])
    assert not any("does not match the code" in p for p in ok)


def test_identity_store_is_jsonl_single_authority() -> None:
    """There is ONE customer registry file, and it is `.jsonl`.

    Resolved from code rather than from the name: clients_store.py binds
    `marketing_clients.jsonl`, the manifest's legacy_paths list the same file
    plus its `.lock`, and both dashboard modules document `.jsonl` as the read
    source. No `.json` store exists, so this was a reporting error, not a dual
    store or a drift.
    """
    entries = {e["allowlist_id"]: e for e in al.load()}
    assert entries["customers.identity.store"]["path_pattern"].endswith(".jsonl")
    assert entries["customers.identity.atomic_tmp"]["path_pattern"].endswith(".jsonl.tmp")

    src = (_REPO / "app" / "marketing" / "clients_store.py").read_text(encoding="utf-8")
    assert "marketing_clients.jsonl" in src
    # The bare `.json` form must not exist anywhere as a real path literal.
    assert '"marketing_clients.json"' not in src
    assert "'marketing_clients.json'" not in src


# ------------------------------------------- finding binding (PRIMARY proof)


def test_every_shipped_entry_binds_to_a_real_finding(findings) -> None:
    """The durable invariant: a declaration must describe detected code.

    Text search alone is not evidence â€” a comment, docstring, error message or
    dead constant satisfies it. That is exactly how `marketing_clients.json`
    survived: the module genuinely contains that substring, inside `.jsonl`.
    """
    problems = al._check_finding_binding(al.load(), findings)
    assert problems == [], "\n  ".join(problems)


def test_unbound_entry_is_rejected(findings) -> None:
    ghost = _entry(allowlist_id="ghost", line_or_symbol="_NO_SUCH_SYMBOL")
    problems = al._check_finding_binding([ghost], findings)
    assert any("declaration is unbound" in p for p in problems)


def test_path_mismatch_against_findings_is_rejected(findings) -> None:
    """`.json` must not bind to a `.jsonl` finding."""
    bad = _entry(
        allowlist_id="typo",
        file="app/marketing/clients_store.py",
        line_or_symbol="_CLIENTS_FILE",
        path_pattern="data/marketing_clients.json",
        store_id="customers.identity",
        access_modes=["REWRITE", "READ", "CREATE", "APPEND"],
    )
    problems = al._check_finding_binding([bad], findings)
    assert any(
        "does not match any detected path" in p or "declaration is unbound" in p for p in problems
    )


def test_conflicting_store_claims_are_rejected(findings) -> None:
    a = _entry(allowlist_id="a", store_id="billing.invoices")
    b = _entry(allowlist_id="b", store_id="compliance.dpdp_audit")
    problems = al._check_finding_binding([a, b], findings)
    assert any("conflicting store ids" in p for p in problems)


@pytest.mark.parametrize(
    "declared,detected,expected",
    [
        ("data/marketing_clients.jsonl", "os.path.join('data', 'marketing_clients.jsonl')", True),
        ("data/marketing_clients.json", "os.path.join('data', 'marketing_clients.jsonl')", False),
        (
            "data/marketing_clients.jsonl.tmp",
            "os.path.join('data', 'marketing_clients.jsonl')",
            True,
        ),
        (
            "data/marketing_clients.jsonl.lock",
            "os.path.join('data', 'marketing_clients.jsonl')",
            True,
        ),
        ("data/client", "data/client_secrets.jsonl", False),
        ("data/x.jsonl", "Path('data') / 'x.jsonl'", True),
        ("data//x.jsonl", "./data/x.jsonl", True),
    ],
)
def test_path_component_boundaries(declared: str, detected: str, expected: bool) -> None:
    """Prefix matching is unsafe, and not hypothetically so."""
    assert al.path_components_match(declared, detected) is expected


def test_text_only_occurrence_does_not_bind(findings) -> None:
    """A basename that exists ONLY in prose must not satisfy a declaration.

    The secondary source-text check would accept this; the finding binding is
    what refuses it.
    """
    prose_only = _entry(
        allowlist_id="prose",
        file="app/platform/runtime_data_allowlist.py",  # mentions paths in docstrings
        line_or_symbol="_NOT_A_REAL_SYMBOL",
        path_pattern="data/marketing_clients.jsonl",
    )
    problems = al._check_finding_binding([prose_only], findings)
    assert any("unbound" in p for p in problems)


def test_missing_file_rejected() -> None:
    problems = al.validate([_entry(file="app/gone/away.py")])
    assert any("no longer exists" in p for p in problems)


# --------------------------------------------------------------- gate shape


def test_coverage_counters_are_derived(findings) -> None:
    cov = al.coverage(findings)
    assert set(cov) >= {
        "undeclared_mutable_paths",
        "ambiguous_mutable_paths",
        "declared_legacy_writes",
        "declared_legacy_reads",
    }
    for v in cov.values():
        assert isinstance(v, int)


def test_declared_entries_actually_reclassify_findings(findings) -> None:
    """Anti-vacuity: the allowlist must CHANGE the outcome.

    Without this, every rejection test above could pass against an allowlist
    that the scanner ignores entirely.
    """
    with_list = al.coverage(findings)
    without = al.coverage(scan.scan_repo(_REPO, allowlist=[]))
    assert with_list["declared_legacy_writes"] > 0
    assert without["declared_legacy_writes"] == 0
    assert with_list["undeclared_mutable_paths"] < without["undeclared_mutable_paths"]


def test_store_manifest_still_validates() -> None:
    """Regression: the scanner batch must not disturb store accounting."""
    assert manifest.validate() == []
    counts = manifest.counts()
    # The scanner batch is discovery + declaration only. If either number moves
    # it means a store family was silently added or a blocker silently dropped,
    # which must happen through an evidence-backed manifest edit, not as a
    # side effect of building a scanner.
    # 2026-07-27: 22 -> 23 / 16 -> 17 via an evidence-backed manifest edit for
    # devcontrol.external_missions (PR #147). It is a blocker because its root,
    # EXTERNAL_MISSION_DIR, defaults to data/external_missions INSIDE the
    # checkout. A8 (2026-07-29) moved the row to DUAL_READ_PRE_CUTOVER (writers
    # follow the shared authority) but bytes have not moved â€” still a blocker.
    # 2026-07-27, second evidence-backed edit: +4 calling-safety families
    # (23 -> 27, 17 -> 21). Each defaults inside the checkout, so each blocks.
    # A7 (2026-07-29): sales.prospects -> DUAL_READ_PRE_CUTOVER (code-only;
    # ~20MB JSONL host cutover is a separate PR â€” blockers stay 21).
    # 2026-07-30: +1 ops.owner_email_canary (LEGACY_IN_CHECKOUT, non-blocker).
    # 2026-07-31: +1 governance.mission_control (LEGACY_IN_CHECKOUT, non-blocker).
    # 2026-08-04: +1 owner_os.coordination_hub (ADR-150 projection; rebuildable).
    # 2026-08-05: +1 platform.memory_governance (ADR-158/161; rebuildable cache).
    # 2026-08-11: +1 marketing.gsc_rankings (ADR-177; tier3 rebuildable, INERT).
    # 2026-08-14: +1 ops.office_briefing (Hot Queue owner-notified claim; resumable).
    # 2026-08-16: +6 marketing feature JSONL families (INERT; rebuildable cache).
    # 2026-08-24: +2 revenue-sprint families — billing.promo_codes (coupon
    # engine ledger) and marketing.affiliates (referral kit), both tier-3
    # rebuildable INERT-by-default stores via evidence-backed manifest edit.
    assert counts["unique_families"] == 50
    assert counts["deployment_blockers"] == 0
    by_id = {s["store_id"]: s for s in manifest.STORES}
    ext = by_id["devcontrol.external_missions"]
    assert ext["migration_tier"] == manifest.TIER_1
    assert ext["migration_state"] == manifest.CUTOVER_COMPLETE
    assert manifest.derived_blocker(ext) is False
    prospects = by_id["sales.prospects"]
    assert prospects["migration_tier"] == manifest.TIER_1
    assert prospects["migration_state"] == manifest.CUTOVER_COMPLETE
    assert manifest.derived_blocker(prospects) is False
    # Calling-safety controls are Tier 0; after host cutover they are complete.
    for sid in (
        "telephony.calling_safety_config",
        "telephony.dial_suppression",
        "telephony.voice_kill_switch",
    ):
        assert by_id[sid]["migration_tier"] == manifest.TIER_0, sid
        assert by_id[sid]["migration_state"] == manifest.CUTOVER_COMPLETE, sid
        assert manifest.derived_blocker(by_id[sid]) is False, sid
    rec = by_id["telephony.call_recordings"]
    assert rec["migration_tier"] == manifest.TIER_2
    assert rec["migration_state"] == manifest.CUTOVER_COMPLETE
    assert manifest.derived_blocker(rec) is False
    arts = by_id["artifacts.call_recordings"]
    assert arts["migration_tier"] == manifest.TIER_2
    assert arts["migration_state"] == manifest.CUTOVER_COMPLETE
    assert manifest.derived_blocker(arts) is False
    # The audit ledger stays OUT until it has its own reader/writer evidence.
    assert "telephony.dial_suppression_audit" not in by_id
