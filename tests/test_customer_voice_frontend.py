"""Static assertions on frontend/customer_voice.html (UX redesign — voice fork).

Same view engine as the combo pilot, 3 visible views (Home / Leads & Calls /
Account) — content cards are gated off under prod-voice so there is no content nav.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HTML_PATH = Path(__file__).resolve().parents[1] / "frontend" / "customer_voice.html"
SRC = HTML_PATH.read_text(encoding="utf-8")

PRE_EXISTING_IDS = [
    "teamCard", "contentCard", "approvalCard", "webToolsCard", "routingCard",
    "leadsCard", "mktKpis", "callsCard", "billingCard", "webhookCard", "secCard",
]
GATING_TOKENS = ["prod-marketing", "prod-voice", "voice-only", "details-hidden"]
HERO_CLASS_TOKENS = ["owner-hero", "status-strip", "hero-leads"]


def _inline_js() -> str:
    blocks = re.findall(r"<script>(.*?)</script>", SRC, re.S)
    assert blocks, "no inline <script> block found"
    return "\n;\n".join(blocks)


def _tag_of(_id):
    m = re.search(r"<[^>]*id=\"" + re.escape(_id) + r"\"[^>]*>", SRC)
    assert m, f"no opening tag for {_id}"
    return m.group(0)


def test_inline_js_syntax_ok(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node not on PATH")
    f = tmp_path / "voice_inline.js"
    f.write_text(_inline_js(), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_no_pre_existing_id_removed():
    missing = [i for i in PRE_EXISTING_IDS if f'id="{i}"' not in SRC]
    assert not missing, f"pre-redesign IDs vanished: {missing}"


def test_gating_and_hero_present():
    assert not [t for t in GATING_TOKENS if t not in SRC]
    for c in HERO_CLASS_TOKENS:
        assert re.search(r'class="[^"]*' + re.escape(c), SRC), f"{c} DOM block missing"


def test_view_engine_present():
    assert "function showView" in SRC and "function viewForHash" in SRC
    assert 'data-active-view="home"' in SRC
    assert 'data-view="account"]){display:none !important}' in SRC


def test_charts_resized():
    assert "function resizeCharts" in SRC
    for fn in ("showView", "toggleDetails"):
        m = re.search(r"function " + fn + r"\([^)]*\)\s*\{(.*?)\n\}", SRC, re.S)
        assert m and "resizeCharts()" in m.group(1), f"{fn} must call resizeCharts"


def test_all_blocks_tagged():
    for v in ("home", "leads", "account"):
        assert f'data-view="{v}"' in SRC
    assert SRC.count('data-view="') >= 25


def test_key_cards_in_expected_view():
    assert 'data-view="leads"' in _tag_of("leadsCard")
    assert 'data-view="leads"' in _tag_of("callsCard")
    assert 'data-view="leads"' in _tag_of("routingCard")
    assert 'data-view="account"' in _tag_of("billingCard")
    assert 'data-view="account"' in _tag_of("secCard")
    assert 'data-view="home"' in _tag_of("teamCard")


def test_sidebar_wired_to_views():
    for v in ("home", "leads", "account"):
        assert f'data-nav="{v}"' in SRC
    assert "showView('leads')" in SRC and "showView('account')" in SRC


def test_home_money_above_decoration():
    # voice has no #aiCommand — money hero sits above the team-office card
    assert SRC.index('class="hero-leads"') < SRC.index('id="teamCard"')
