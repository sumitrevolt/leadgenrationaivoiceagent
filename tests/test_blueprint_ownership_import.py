"""Ownership-registry + verified-detail-import gates.

Two things are locked here:

1. The domain ownership registry is a *reviewed* artifact, not a package-prefix
   heuristic. Shared packages stay rejected, exclusions hold, and ownership can
   never by itself promote a node to HIGH.
2. Nodes actually imported into the canonical registry are evidence-backed,
   collapsed by default, correctly parented, and do not disturb the L0 map.
"""

from __future__ import annotations

from app.platform import blueprint_detail_nodes as bdn
from app.platform import blueprint_graph as bg
from app.platform import blueprint_ownership as own


# --------------------------- ownership registry ---------------------------
def test_ownership_rules_are_structurally_valid():
    problems = own.validate_rules({d["key"] for d in bg.DOMAINS})
    assert not problems, problems


def test_shared_packages_are_rejected_wholesale():
    """The packages that produced the original false mappings stay unowned."""
    for path in (
        "app/api/growth.py",
        "app/platform/team_scheduler.py",
        "app/models/lead.py",
        "app/utils/logger.py",
        "app/integrations/whatsapp.py",
        "app/tasks/calling.py",
        "app/agents/coordinator.py",
    ):
        dom, why = own.owning_domain(path)
        assert dom is None, f"{path} must not be owned wholesale (got {dom}: {why})"
        assert "rejected" in why or "no reviewed ownership" in why


def test_every_rejected_root_states_a_reason():
    for root, why in own.REJECTED_ROOTS.items():
        assert root.endswith("/"), root
        assert len(why) > 20, root


def test_reviewed_package_ownership_resolves():
    assert own.owning_domain("app/telephony/call_transfer.py")[0] == "voice_telephony"
    assert own.owning_domain("app/billing/subscription.py")[0] == "billing_payments"
    assert own.owning_domain("app/lead_scraper/google_maps.py")[0] == "lead_pipeline"
    assert own.owning_domain("app/social_engine/engine.py")[0] == "social_publish"


def test_exclusions_carve_out_mixed_modules():
    """Modules that merely *live* in a package but belong elsewhere."""
    # KB/RAG nested under the voice package
    assert own.owning_domain("app/voice_agent/knowledge_base.py")[0] == "kb_rag"
    assert own.owning_domain("app/voice_agent/graph_rag.py")[0] == "kb_rag"
    # compliance/consent nested under the telephony package
    assert own.owning_domain("app/telephony/consent_ledger.py")[0] == "security_compliance"
    assert own.owning_domain("app/telephony/compliance.py")[0] == "security_compliance"
    # generic helper inside billing is NOT billing
    assert own.owning_domain("app/billing/idempotency.py")[0] is None


def test_exact_files_win_over_prefixes():
    dom, why = own.owning_domain("app/voice_agent/knowledge_base.py")
    assert dom == "kb_rag" and "exact-file" in why


def test_no_file_is_claimed_by_two_domains():
    seen: dict[str, str] = {}
    for d, rule in own.DOMAIN_OWNERSHIP_RULES.items():
        for f in rule["exact_files"]:
            assert f not in seen, (f, seen.get(f), d)
            seen[f] = d


def test_ownership_always_requires_corroboration():
    for d, rule in own.DOMAIN_OWNERSHIP_RULES.items():
        assert rule["requires_corroboration"] is True, d
        assert rule["evidence"], d


def test_critical_domains_are_flagged_critical():
    for d in ("voice_telephony", "billing_payments", "security_compliance", "owner_os_copilot"):
        assert own.DOMAIN_OWNERSHIP_RULES[d]["critical"] is True


# --------------------------- imported detail nodes ------------------------
def _imported():
    return [n for n in bg.NODES if n.get("source_provenance") == "legacy-migrated"]


def test_detail_nodes_are_in_the_one_registry():
    ids = {n["id"] for n in bg.NODES}
    for spec in bdn.DETAIL_NODE_SPECS:
        assert spec[0] in ids, spec[0]


def test_graph_stays_valid_with_detail_nodes():
    r = bg.validate_graph(strict_files=True)
    assert r["ok"], r["errors"]


def test_l0_projection_unchanged():
    c = bg.build_graph()["counts"]
    assert c["l0"] == 50
    assert c["edges"] == 56 and c["flows"] == 11
    assert c["domains"] == 18 and c["layers"] == 9


def test_imported_nodes_are_collapsed_by_default():
    for n in _imported():
        assert n["default_visibility"] == "collapsed", n["id"]
        assert n["depth_level"] >= 1, n["id"]


def test_imported_nodes_carry_legacy_mapping_and_evidence():
    for n in _imported():
        assert n["legacy_node_id"], n["id"]
        assert n["files"], n["id"]
        assert n["source_provenance"] == "legacy-migrated"


def test_imported_l2_has_same_domain_l1_group_parent():
    """L2 needs an L1 group parent in the same domain.

    Two failure modes are pinned here: the cross-domain parent
    (`s_telecore -> customer_dashboard`) and the depth skip
    (`s_stttts -> voice_agent`, where voice_agent is an L0 aggregate).
    """
    by_id = {n["id"]: n for n in bg.NODES}
    for n in _imported():
        if n["depth_level"] >= 2:
            p = n.get("parent_node_id")
            assert p or n.get("parent_flow_id"), n["id"]
            if p:
                assert by_id[p]["domain"] == n["domain"], (n["id"], p)
                assert by_id[p]["depth_level"] == 1, (n["id"], p)


# --------------------------- fail-closed detail import --------------------
def test_detail_import_is_not_silently_optional():
    """A broken detail module must crash, not quietly drop back to 48 nodes."""
    src = (bg._ROOT / "app" / "platform" / "blueprint_graph.py").read_text(
        encoding="utf-8", errors="replace"
    )
    head = src.split("EDGES: list", 1)[0]
    assert "build_detail_nodes" in head
    assert "except Exception" not in head.split("blueprint_detail_nodes", 1)[1]


def test_registry_contains_every_declared_detail_node():
    ids = {n["id"] for n in bg.NODES}
    declared = {spec[0] for spec in bdn.DETAIL_NODE_SPECS}
    assert declared and declared <= ids
    legacy_declared = {
        spec[0]
        for spec in bdn.DETAIL_NODE_SPECS
        if (spec[8] or {}).get("source_provenance") == "legacy-migrated"
    }
    assert len(_imported()) == len(legacy_declared)


def test_exact_expected_counts_for_this_pr():
    c = bg.build_graph()["counts"]
    assert c["l0"] == 50, c
    # L0 curated map locked; L1 grows as verified CODE-PRESENT detail lands
    # (sales_autopilot / creative_os / owner_email_canary added 2026-07-30;
    #  coordinator / omniroute added 2026-08-03).
    assert c["l1"] == 8 and c["l2"] == 1, c
    assert c["nodes"] == 59, c
    assert c["nodes"] == c["l0"] + c["l1"] + c["l2"]


def test_malformed_detail_spec_is_rejected_not_swallowed():
    """The factory must raise on a malformed spec rather than skip it."""
    import pytest

    bad = [("only", "three", "fields")]
    orig = bdn.DETAIL_NODE_SPECS
    try:
        bdn.DETAIL_NODE_SPECS = bad  # type: ignore[assignment]
        with pytest.raises((TypeError, ValueError)):
            bdn.build_detail_nodes(bg._n)
    finally:
        bdn.DETAIL_NODE_SPECS = orig  # type: ignore[assignment]


def test_depth_ordering_is_enforced_globally(monkeypatch):
    """Any L2 parented on an L0 node must fail validation, not just ours."""
    l0 = next(n for n in bg.NODES if n["depth_level"] == 0)
    bad = bg._n(
        "tmp_depth_probe",
        "Probe",
        l0["layer"],
        l0["domain"],
        "engine",
        "CODE-PRESENT",
        ["app/platform/blueprint_graph.py"],
        "probe",
        depth_level=2,
        parent_node_id=l0["id"],
    )
    monkeypatch.setattr(bg, "NODES", [l0, bad])
    monkeypatch.setattr(bg, "EDGES", [])
    monkeypatch.setattr(bg, "FLOWS", [])
    errs = bg.validate_graph(strict_files=False)["errors"]
    assert any("needs an L1 group parent" in e for e in errs), errs


def test_cross_domain_parent_rejected_globally(monkeypatch):
    a = next(n for n in bg.NODES if n["depth_level"] == 0)
    b = next(n for n in bg.NODES if n["depth_level"] == 0 and n["domain"] != a["domain"])
    child = bg._n(
        "tmp_xdomain",
        "Probe",
        a["layer"],
        a["domain"],
        "engine",
        "CODE-PRESENT",
        ["app/platform/blueprint_graph.py"],
        "probe",
        depth_level=1,
        parent_node_id=b["id"],
    )
    monkeypatch.setattr(bg, "NODES", [a, b, child])
    monkeypatch.setattr(bg, "EDGES", [])
    monkeypatch.setattr(bg, "FLOWS", [])
    errs = bg.validate_graph(strict_files=False)["errors"]
    assert any("cross-domain parent" in e for e in errs), errs


def test_imported_l1_is_domain_rooted_without_fabricated_parent():
    domains = {d["key"] for d in bg.DOMAINS}
    for n in _imported():
        if n["depth_level"] == 1:
            assert n["parent_domain_id"] in domains, n["id"]


def test_imported_nodes_are_not_marked_live():
    """Source existing proves CODE-PRESENT, never production activation."""
    for n in _imported():
        assert n["status"] != "PRODUCTION-PROVEN", n["id"]


def test_imported_harness_controls_are_not_fabricated():
    for n in _imported():
        for f in bg.HARNESS_CONTROL_FIELDS:
            assert n[f] is None or isinstance(n[f], str | int | list | dict), (n["id"], f)
            assert n[f] is not True, f"{n['id']}.{f} fabricates a control"


def test_no_duplicate_legacy_mapping_after_import():
    seen: dict[str, str] = {}
    for n in bg.NODES:
        lg = n.get("legacy_node_id")
        if lg:
            assert lg not in seen, (lg, seen[lg], n["id"])
            seen[lg] = n["id"]


def test_public_graph_still_sanitized_after_import():
    pub = bg.build_public_graph()
    forbidden = set(bg.HARNESS_CONTROL_FIELDS) | {
        "files",
        "flags",
        "legacy_node_id",
        "source_provenance",
        "parent_node_id",
    }
    for n in pub["nodes"]:
        assert not (set(n) & forbidden), set(n) & forbidden


def test_calling_full_campaign_live_after_import():
    """§5 compliance spine stays ACTIVE; cold outbound is FULL CAMPAIGN LIVE
    (owner go-ahead 2026-08-02), not a disabled/deprecated node."""
    pd = next(n for n in bg.NODES if n["id"] == "platform_dial")
    assert pd["disabled"] is False
    assert pd["status"] == "PRODUCTION-PROVEN"
