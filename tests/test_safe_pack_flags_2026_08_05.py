"""Contract: owner Safe Pack keys stay exact, disjoint from NEVER, sync with canary.sh."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from safe_pack_flags import NEVER_TOUCH, SAFE_PACK_KEYS, assert_safe_pack_disjoint  # noqa: E402


def test_safe_pack_disjoint_from_never():
    assert_safe_pack_disjoint()
    assert set(SAFE_PACK_KEYS) & NEVER_TOUCH == set()


def test_safe_pack_exact_owner_lock():
    assert SAFE_PACK_KEYS == (
        "FLOW_RUNNER",
        "FLOW_AUTO_TRIGGERS",
        "PROCESS_ENGINE",
        "PROCESS_AUTOSTART",
        "REVENUE_TRENDS",
        "CONTENT_APPROVAL_AUTO",
    )


def test_canary_sh_keys_match_python():
    text = (SCRIPTS / "safe_pack_flag_canary.sh").read_text(encoding="utf-8")
    # Extract KEYS=( ... ) block names
    m = re.search(r"^KEYS=\(\s*(.*?)^\s*\)", text, re.M | re.S)
    assert m, "KEYS=(...) block missing in safe_pack_flag_canary.sh"
    bash_keys = tuple(re.findall(r"^\s*([A-Z][A-Z0-9_]+)\s*$", m.group(1), re.M))
    assert bash_keys == SAFE_PACK_KEYS


def test_never_touch_blocks_cold_wa_and_reply_auto():
    assert "SALES_AUTOPILOT_WHATSAPP_ENABLED" in NEVER_TOUCH
    assert "REPLY_AUTO_SEND" in NEVER_TOUCH
    assert "ALLOW_TOS_SCRAPE" in NEVER_TOUCH
