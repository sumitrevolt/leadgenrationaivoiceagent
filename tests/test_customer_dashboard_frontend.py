"""Static assertions on frontend/customer_dashboard.html (UX redesign pilot).

Mirrors tests/test_office_map_frontend.py:
 (1) node --check syntax gate on inline <script>,
 (2) no-removal guard: every pre-redesign id/gating token must still exist,
 (3) per-task markers added by
     docs/superpowers/plans/2026-07-05-customer-dashboard-ux-redesign.md.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

HTML_PATH = Path(__file__).resolve().parents[1] / "frontend" / "customer_dashboard.html"
SRC = HTML_PATH.read_text(encoding="utf-8")

PRE_EXISTING_IDS = [
    "aiCommand",
    "teamCard",
    "contentCard",
    "contentBody",
    "approvalCard",
    "approvalBody",
    "webToolsCard",
    "webToolsBody",
    "routingCard",
    "leadsCard",
    "summaryBox",
    "mktKpis",
    "callsCard",
    "billingCard",
    "webhookCard",
    "secCard",
]
# Product-gating class names that must never vanish (stable substrings).
GATING_TOKENS = ["prod-marketing", "prod-voice", "marketing-only", "voice-only"]
# Hero DOM blocks — checked via regex so later tasks may add classes (e.g. v-on)
# without tripping the guard.
HERO_CLASS_TOKENS = ["owner-hero", "status-strip", "hero-leads"]


def _inline_js() -> str:
    blocks = re.findall(r"<script>(.*?)</script>", SRC, re.S)
    assert blocks, "no inline <script> block found"
    return "\n;\n".join(blocks)


def test_inline_js_syntax_ok(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node not on PATH")
    f = tmp_path / "cust_inline.js"
    f.write_text(_inline_js(), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_no_pre_existing_id_removed():
    missing = [i for i in PRE_EXISTING_IDS if f'id="{i}"' not in SRC]
    assert not missing, f"pre-redesign IDs vanished: {missing}"


def test_gating_tokens_present():
    missing = [t for t in GATING_TOKENS if t not in SRC]
    assert not missing, f"gating tokens vanished: {missing}"


def test_hero_blocks_present():
    for c in HERO_CLASS_TOKENS:
        assert re.search(r'class="[^"]*' + re.escape(c), SRC), f"{c} DOM block missing"


def test_pending_approval_banner_is_wired_to_existing_approval_card():
    assert 'id="approvalBanner"' in SRC
    assert 'id="approvalBannerMsg"' in SRC
    assert "function renderApprovalBanner" in SRC
    assert "approval_banner" in SRC
    assert "scrollToId('approvalCard')" in SRC


# ---- Task 2: view engine ----
def test_view_engine_present():
    assert "function showView" in SRC
    assert "function viewForHash" in SRC
    # active-view scheme: #mainContent carries data-active-view; CSS hides the rest
    assert 'data-active-view="home"' in SRC
    assert "[data-active-view=" in SRC


def test_showview_resizes_charts():
    # charts render at 0x0 while their view is hidden; showView must resize them
    # (delegated to the shared resizeCharts() helper — see Task 6 test).
    m = re.search(r"function showView\([^)]*\)\s*\{(.*?)\n\}", SRC, re.S)
    assert m and "resizeCharts()" in m.group(1), "showView must resize now-visible charts"


def test_init_on_dom_ready_not_postfetch():
    # default view must paint on DOM ready, independent of the API fetch
    assert "DOMContentLoaded" in SRC or "readyState" in SRC


def test_scrolltoid_is_view_aware():
    # scrollToId must call showView so old anchor links land on the right view
    m = re.search(r"function scrollToId\([^)]*\)\s*\{(.*?)\}", SRC, re.S)
    assert m and "showView" in m.group(1), "scrollToId must route through showView"


# ---- Task 3: block tagging ----
def _tag_of(_id):
    m = re.search(r"<[^>]*id=\"" + re.escape(_id) + r"\"[^>]*>", SRC)
    assert m, f"no opening tag for {_id}"
    return m.group(0)


def test_all_blocks_tagged():
    # View taxonomy renamed 2026-07-07 (commit 8359d1c): content/approval cards
    # consolidated onto Home (no separate Content tab) and "account" renamed to
    # "billing"; "setup"/"calendar"/"reports" views added. See
    # tests/test_customer_dashboard_product_routing.py for the routing side of
    # that same commit's changes.
    for v in ("home", "leads", "billing"):
        assert f'data-view="{v}"' in SRC, f"no block tagged {v}"
    # every content-level block (incl. sec-title headers) must be tagged or it
    # leaks into all views; there are ~29 such blocks.
    assert SRC.count('data-view="') >= 27, "too few tagged blocks — some will leak"


def test_key_cards_in_expected_view():
    assert 'data-view="leads"' in _tag_of("leadsCard")
    assert 'data-view="leads"' in _tag_of("callsCard")
    assert 'data-view="leads"' in _tag_of("routingCard")
    # content/approval cards live on Home directly (no separate Content tab)
    assert 'data-view="home"' in _tag_of("contentCard")
    assert 'data-view="home"' in _tag_of("approvalCard")
    assert 'data-view="billing"' in _tag_of("billingCard")
    assert 'data-view="billing"' in _tag_of("secCard")
    # #mktKpis is a .kpis instance but belongs to Reports (not the leads charts)
    assert 'data-view="reports"' in _tag_of("mktKpis")
    assert 'data-view="home"' in _tag_of("aiCommand")
    assert 'data-view="home"' in _tag_of("teamCard")


# ---- Task 4: nav wiring ----
def test_sidebar_wired_to_views():
    # sidebar carries data-nav for each view (active-state) and calls showView
    for v in ("home", "leads", "billing"):
        assert f'data-nav="{v}"' in SRC, f"sidebar missing data-nav={v}"
    assert "showView('leads')" in SRC and "showView('billing')" in SRC


def test_mobile_nav_switches_views():
    # Mobile bottom nav uses the view engine directly; More routes through the
    # existing sheet and then showView().
    nav = re.search(r'<nav class="mobile-app-nav".*?</nav>', SRC, re.S)
    assert nav and "showView('home')" in nav.group(0)
    assert nav and "showView('leads')" in nav.group(0)
    assert nav and "openMoreSheet()" in nav.group(0)


# ---- Task 5: focused Home ----
def test_home_money_above_decoration():
    # the hot-leads money hero must sit above the AI-command decoration on Home
    assert SRC.index('class="hero-leads"') < SRC.index('id="aiCommand"'), (
        "hero-leads (money action) must precede #aiCommand on Home"
    )


# ---- Task 6: browser-verified fixes ----
def test_view_hide_rule_uses_important():
    # !important is required so the hide rule beats block styles like
    # .sec-title{display:flex}; without it, sec-titles leak across views.
    assert 'data-view="support"]){display:none !important}' in SRC


def test_charts_resized_on_show_and_details():
    # a shared resizeCharts() fixes 0x0 Chart.js canvases; both the view switch
    # and the "Pura hisaab" details toggle must call it.
    assert "function resizeCharts" in SRC
    sv = re.search(r"function showView\([^)]*\)\s*\{(.*?)\n\}", SRC, re.S)
    assert sv and "resizeCharts()" in sv.group(1), "showView must call resizeCharts"
    td = re.search(r"function toggleDetails\([^)]*\)\s*\{(.*?)\n\}", SRC, re.S)
    assert td and "resizeCharts()" in td.group(1), "toggleDetails must call resizeCharts"


def test_command_center_score_is_honest_count_not_fabricated_percent():
    assert "Math.max(42, Math.min(98" not in SRC
    assert "meta.score || 76" not in SRC
    assert 'id="aiScore">—</strong>' in SRC or 'id="aiScore">—' in SRC
    assert "Login ke baad" in SRC
    assert 'id="voiceMinsHint"' in SRC
    assert "Minutes bache:" in SRC
