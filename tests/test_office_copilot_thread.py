"""Static regression guard for the Office HQ copilot CONVERSATION THREAD.

Context: the Boss copilot used to render only the LAST reply in a single box
(#bossCommandResult), overwriting the previous answer each time — so admin<->agent
back-and-forth was invisible ("agent proper reply nahi de raha" complaint). The
fix turns it into an attributed, persistent thread (#bossThread) with per-turn
WHO / kind / time and localStorage history.

These are pure string-presence assertions on frontend/office_map.html (a single
self-contained inline-JS page). Syntax of the inline script is already gated by
tests/test_office_map_frontend.py's node --check; here we only guard that the
thread feature + its pre-existing anchors stay present. Hermetic (no network,
no app import) but frontend-static — CI runs it; it can also be eyeballed.
"""

from pathlib import Path

HTML_PATH = Path(__file__).resolve().parents[1] / "frontend" / "office_map.html"
SRC = HTML_PATH.read_text(encoding="utf-8")


def test_preexisting_copilot_anchors_survive():
    # No-removal guard: the copilot input/button/status line must still exist.
    for token in ('id="bossCommandInput"', 'id="bossCommandBtn"', 'id="bossCommandResult"'):
        assert token in SRC, f"copilot anchor removed: {token}"


def test_conversation_thread_markup_present():
    for token in ('id="bossThread"', 'id="bossThreadClear"', 'class="boss-thread-foot"'):
        assert token in SRC, f"thread markup missing: {token}"


def test_thread_js_wiring_present():
    for token in (
        "OFFICE.BOSS_THREAD_KEY",
        "OFFICE.loadBossThread",
        "OFFICE.saveBossThread",
        "OFFICE.renderBossThread",
        "OFFICE.clearBossThread",
        "OFFICE.bossWho",
    ):
        assert token in SRC, f"thread JS wiring missing: {token}"


def test_thread_persists_and_attributes():
    # localStorage persistence + a bounded window + WHO attribution helper.
    assert '"officeBossThread"' in SRC
    assert "localStorage.setItem(OFFICE.BOSS_THREAD_KEY" in SRC
    assert "slice(-20)" in SRC  # bounded history
    # attribution branches (task -> agent, broadcast -> team, else Boss)
    assert "Puri Team" in SRC


def test_thread_bubble_styles_present():
    for token in (".bt-ask{", ".bt-reply{", ".bt-who{", ".bt-kind{"):
        assert token in SRC, f"thread bubble CSS missing: {token}"
