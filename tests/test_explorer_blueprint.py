"""Project Blueprint contract for /app/explorer (2026-07-20 redesign).

The Explorer's default landing is now a Make.com-inspired "map of maps"
(Blueprint Home -> Section -> Focused Flow -> Node Details) that a normal
business owner can read block-by-block, instead of the old 83-node / ~13%-zoom
spaghetti canvas. The legacy detailed graph/builder/flags/schedule/export is
NOT removed -- it is preserved as the "Technical Graph" advanced view and stays
reachable at ?view=technical.

These are static-analysis guards (like the sibling explorer tests) so they run
without a live server. They lock the IA + truth rules the redesign brief asked
for, and re-use scripts/explorer_sync for the "no dangling / files resolve"
gates so the additive Blueprint data can never silently drift the graph.
"""

from __future__ import annotations

from pathlib import Path

from scripts import deep_wiring_audit as dwa
from scripts import explorer_sync as es

REPO = Path(__file__).resolve().parent.parent
EXPLORER = REPO / "frontend" / "explorer.html"


def _html() -> str:
    return EXPLORER.read_text(encoding="utf-8")


# --- required top-level IA ------------------------------------------------
REQUIRED_MODES = ["Project Blueprint", "Automations", "Products", "Technical Graph"]

REQUIRED_SECTIONS = [
    "Products & Customer Journey",
    "Lead Generation & CRM",
    "Content & Social Publishing",
    "AI Staff & Owner OS",
    "Automations & Scheduler",
    "Voice & Telephony",
    "Billing & Customer Delivery",
    "Data & Integrations",
    "Infrastructure, Security & Observability",
]

REQUIRED_WORKFLOWS = [
    "Lead discovery → scoring → outreach",
    "Inquiry → Hot Queue → human follow-up",
    "Content generation → approval → social publish",
    "Reply agent → classification → guarded response",
    "Customer signup → onboarding → delivery assurance",
    "UPI/payment → subscription → invoice",
    "AI agents → scheduler → execution → audit",
    "Self-improve → evaluation → approval/requeue",
    "Runtime health → alert → recovery/DLQ",
    "Inbound/missed-call → consent gate → callback",
]

EVIDENCE_LABELS = [
    "PRODUCTION-PROVEN",
    "TEST-PROVEN",
    "CODE-PRESENT",
    "LOCAL-ONLY",
    "EXTERNAL-BLOCKED",
    "UNKNOWN",
]


def test_blueprint_is_default_landing():
    html = _html()
    # body boots into blueprint mode; technical graph is opt-in.
    assert 'class="mode-blueprint"' in html
    assert 'id="bp-root"' in html
    assert "window.BP = BP" in html and "BP.boot()" in html


def test_all_four_top_modes_present():
    html = _html()
    for m in REQUIRED_MODES:
        assert m in html, f"top mode missing: {m}"
    # exactly the 4 mode buttons wired
    for dm in ("blueprint", "automations", "products", "technical"):
        assert f'data-mode="{dm}"' in html, f"mode button missing: {dm}"


def test_all_nine_blueprint_sections_present():
    html = _html()
    for s in REQUIRED_SECTIONS:
        assert s in html, f"blueprint section missing: {s}"


def test_ten_automation_workflows_selectable():
    html = _html()
    for w in REQUIRED_WORKFLOWS:
        assert w in html, f"automation workflow missing: {w}"
    # each is opened individually (not one spaghetti canvas)
    assert "openWorkflow(" in html
    assert "BP_AUTOMATIONS" in html


def test_platform_dial_shown_hard_off_not_modified():
    html = _html()
    # blueprint must DISPLAY cold outbound as disabled, never re-enable it.
    assert "platform_dial" in html
    assert "HARD OFF" in html
    assert "disabled:true" in html


def test_icon_registry_has_deterministic_fallback():
    html = _html()
    assert "const BPIC" in html
    assert "function bpIcon" in html
    # category fallback + final deterministic fallback
    assert "cat_platform" in html
    assert "return BPIC.cat_platform" in html
    # real provider marks present (local inline svg, no CDN)
    for prov in (
        "fastapi",
        "docker",
        "postgres",
        "redis",
        "qdrant",
        "celery",
        "whatsapp",
        "stripe",
        "sentry",
        "grafana",
        "mistral",
        "gemini",
        "vobiz",
    ):
        assert f"{prov}:" in html, f"provider icon missing: {prov}"


def test_no_external_cdn_in_blueprint_assets():
    html = _html()
    bp = html[html.index('id="bp-style"') :]
    for bad in ("cdnjs", "unpkg", "jsdelivr", "googleapis.com/ajax", "cdn.jsdelivr"):
        assert bad not in bp, f"blueprint pulled external asset: {bad}"


def test_technical_graph_and_old_explorer_still_reachable():
    html = _html()
    # legacy dark canvas + builder preserved
    assert "const VIEWS" in html
    assert 'data-view="custom"' in html  # Flow Runner / builder tab intact
    # deep-link + fallback into the technical graph
    assert "view==='technical'" in html
    assert "enterMode('technical')" in html or 'enterMode("technical")' in html
    assert 'id="bp-back"' in html  # visible "← Blueprint" back control
    # explicit error-state fallback button (never a blank canvas)
    assert 'id="bp-error"' in html
    assert "Old Explorer" in html


def test_public_health_independent_from_admin_overlays_preserved():
    """The redesign must not regress the health-independence contract."""
    html = _html()
    assert "const [healthR, summaryR] = await Promise.all([" in html
    assert "const adminRes = await Promise.allSettled([" in html
    assert "try { renderNodes(); } catch(e) {}" in html


def test_status_defaults_to_unknown_without_live_data():
    """No fabricated 'healthy/live' status when there is no live data."""
    html = _html()
    assert "function stStatus" in html
    # public-health status resolves to 'unknown' (not healthy) when snapshot absent
    assert (
        "if(L&&L.health&&L.health.status==='healthy') return 'healthy'; return 'unknown';" in html
    )
    # unknown is a first-class truthful state
    assert "unknown:'Unknown'" in html


def test_all_evidence_labels_available():
    html = _html()
    for lbl in EVIDENCE_LABELS:
        assert lbl in html, f"evidence label missing: {lbl}"


def test_live_state_only_from_approved_endpoints():
    html = _html()
    # blueprint reuses the same endpoints init() already polls
    for ep in (
        "/health",
        "/api/activation/summary",
        "/api/growth/infra/flags",
        "/api/growth/infra/automation-health",
    ):
        assert ep in html, f"approved endpoint missing: {ep}"


def test_live_pricing_mapper_matches_public_api_contract():
    """Products mode must consume package truth, not silently keep stale prices."""
    html = _html()
    for band in ("A", "B", "C"):
        assert f"/api/voice/packages?band={band}" in html
    assert "price_inr_month" in html
    assert "Array.isArray(payload.tiers)" in html
    assert "data-live-price" in html
    pricing_fetch = html[html.index("  _fetchLivePricing(){") :]
    pricing_fetch = pricing_fetch[: pricing_fetch.index("\n  _applyPricing(payload){")]
    assert "if(liveCount){" not in pricing_fetch


def test_mobile_stepper_and_touch_target_contract():
    html = _html()
    assert "@media(max-width:640px)" in html
    assert "stepper" in html  # vertical stepper on narrow screens
    assert "min-height:44px" in html  # 44px touch targets on mobile
    # mode bar wraps / scrolls instead of overflowing the canvas
    assert "flex-wrap:wrap" in html


def test_blueprint_files_refs_all_resolve():
    """Every files:'x.py' the Blueprint adds must be a real repo file."""
    html = _html()
    missing = es.files_ref_audit(html)
    assert not missing, f"blueprint files: refs not on disk: {missing}"


def test_no_dangling_or_orphans_after_blueprint():
    """Additive Blueprint data must not create dangling edges / orphan nodes
    in the curated Technical-Graph views."""
    html = _html()
    ea = es.edge_audit(html)
    for view, r in ea.items():
        assert not r["dangling"], f"{view} dangling: {r['dangling']}"
        assert not r["orphans"], f"{view} orphans: {r['orphans']}"


def test_single_explorer_route_no_duplicate():
    """Query-mode redesign must not add a second /app/explorer route."""
    main = (REPO / "app" / "main.py").read_text(encoding="utf-8")
    assert main.count('@app.get("/app/explorer"') == 1


def test_blueprint_controller_handlers_are_wired():
    """Inline BP.* actions must resolve to real exported controller methods."""
    result = dwa.audit_file(EXPLORER, set())
    assert not [handler for handler in result["missing_handlers"] if handler.startswith("BP.")]


def test_mode_switch_closes_blueprint_detail_drawer():
    """The Blueprint drawer must not cover the preserved Technical Graph."""
    html = _html()
    enter_mode = html[html.index("  enterMode(mode, legacyView){") :]
    enter_mode = enter_mode[: enter_mode.index("\n  _safe(fn){")]
    assert enter_mode.index("this.closeDrawer();") < enter_mode.index("if(mode==='technical'){")
