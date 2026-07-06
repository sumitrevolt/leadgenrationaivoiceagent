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
    "aiCommand", "teamCard", "contentCard", "contentBody", "approvalCard",
    "approvalBody", "webToolsCard", "webToolsBody", "routingCard", "leadsCard",
    "summaryBox", "mktKpis", "callsCard", "billingCard", "webhookCard", "secCard",
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
