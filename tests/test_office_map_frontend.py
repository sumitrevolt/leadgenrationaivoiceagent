"""Static assertions on frontend/office_map.html (office-enterprise-upgrade).

HTML is a single self-contained page (inline CSS+JS), so tests are
(1) a node --check syntax gate on the inline script,
(2) a no-removal guard: every pre-upgrade element ID must still exist,
(3) per-feature markers added task-by-task by the upgrade plan
    (docs/superpowers/plans/2026-07-05-office-enterprise-upgrade.md).
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

HTML_PATH = Path(__file__).resolve().parents[1] / "frontend" / "office_map.html"
SRC = HTML_PATH.read_text(encoding="utf-8")

# Every interactive/panel ID that existed BEFORE the upgrade — none may vanish.
PRE_EXISTING_IDS = [
    "banner",
    "bannerRetry",
    "page",
    "quickNav",
    "statusSummary",
    "warRoom",
    "bossCommandInput",
    "bossCommandBtn",
    "bossCommandResult",
    "trustStrip",
    "bossBriefBody",
    "priorityActionStack",
    "warKpiGrid",
    "pulseStrip",
    "councilPanel",
    "councilTopic",
    "councilRunBtn",
    "councilDeeper",
    "councilResult",
    "capabilitiesPanel",
    "kpiRow",
    "nbaCard",
    "nbaList",
    "enterpriseCard",
    "enterpriseScore",
    "enterpriseFeatureGrid",
    "mapToolbar",
    "agentSearch",
    "agentSearchResults",
    "zoomInBtn",
    "zoomOutBtn",
    "zoomResetBtn",
    "mapHint",
    "modeToggle",
    "stageWrap",
    "stage",
    "previewOverlay",
    "roomListCompact",
    "replayPanel",
    "replayList",
    "feedCard",
    "filterRow",
    "tickerList",
    "coordHistoryWrap",
    "coordHistoryList",
    "leaderboardPanel",
    "leaderboardList",
    "activityPanel",
    "activityChart",
    "activityHours",
    "activityMeta",
    "pipelineBoard",
    "boardRow",
    "schedulePanel",
    "scheduleList",
    "recurringStrip",
    "systemMapCard",
    "systemMapToggle",
    "systemMapBody",
    "systemMapFrame",
    "workflowRunsCard",
    "workflowRunsList",
    "activeCoordCard",
    "activeCoordList",
    "approvalsPanel",
    "bossReviewBtn",
    "bossReviewNote",
    "approvalsList",
    "decisionTrail",
    "systemHealthPanel",
    "healthList",
    "schedulerPanel",
    "schedBadge",
    "schedList",
    "failureConsoleCard",
    "dlqSweepBtn",
    "failureConsoleList",
    "dlqRepairCard",
    "dlqRepairBadge",
    "dlqRepairSummary",
    "hotQueueCard",
    "hotQueueBadge",
    "hotQueueSummary",
    "roomTooltip",
    "coordinatorTickerBox",
    "coordinatorTicker",
    "agentPanel",
    "panelClose",
    "panelBody",
    "legendToggle",
    "legendPopover",
    "legendClose",
    "briefingBtn",
    "briefingModal",
    "briefingClose",
    "briefingDate",
    "briefingBody",
    "briefingPlay",
    "briefingAudioNote",
    "briefingRefresh",
    "istClock",
    "freshnessBadge",
    "viewModeBtn",
    "manualRefreshBtn",
]


def _inline_js() -> str:
    blocks = re.findall(r"<script>(.*?)</script>", SRC, re.S)
    assert blocks, "no inline <script> block found"
    return "\n;\n".join(blocks)


def test_inline_js_syntax_ok(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node not on PATH")
    f = tmp_path / "office_inline.js"
    f.write_text(_inline_js(), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_no_pre_existing_id_removed():
    missing = [i for i in PRE_EXISTING_IDS if f'id="{i}"' not in SRC]
    assert not missing, f"pre-upgrade IDs vanished: {missing}"


def test_bugfix_unique_agent_colors():
    assert "OFFICE.colorForKey" in SRC
    assert "colorCssForKey" in SRC
    assert "setTint(OFFICE.colorForKey" in SRC  # sprite + desk tinted


def test_bugfix_room_overflow_shrink():
    assert "return { slots: slots, scale:" in SRC  # layoutSlots new shape
    assert "sizeScale" in SRC  # drawAvatar consumes it


def test_bugfix_offline_snapback():
    # setAvatarState must kill walk-tweens + reset position the moment an
    # agent goes offline (marker = the fix's own comment).
    assert "offline hote hi turant desk pe wapas" in SRC


def test_bugfix_unmapped_room_badge():
    assert "unmapped" in SRC
    assert "#f97316" in SRC  # orange ? badge


def test_bugfix_ticker_box_hidden_on_mobile_and_simple():
    assert "#coordinatorTickerBox{display:none!important}" in SRC.replace(" ", "")


def test_bugfix_lazy_phaser_boot():
    assert "OFFICE.bootGame" in SRC
    assert "OFFICE.GAME_CONFIG" in SRC
    # game creation must be guarded, not unconditional
    assert "OFFICE.game = new Phaser.Game(OFFICE.GAME_CONFIG)" in SRC


def test_dark_mode():
    assert "data-theme" in SRC
    assert 'id="themeBtn"' in SRC
    assert "prefers-color-scheme" in SRC
    assert "OFFICE.cycleTheme" in SRC


def test_six_labelled_sections():
    for sec in (
        "secCommand",
        "secMap",
        "secActivity",
        "secPipeline",
        "secApprovals",
        "secReliability",
    ):
        assert f'id="{sec}"' in SRC, sec
    assert "hq-sec-label" in SRC


def test_scrollspy():
    assert "IntersectionObserver" in SRC
    assert "qn-active" in SRC


def test_command_palette():
    assert 'id="cmdPalette"' in SRC
    assert "OFFICE.openPalette" in SRC
    assert '(e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")' in SRC


def test_toast_alerts():
    assert 'id="toastStack"' in SRC
    assert "OFFICE.checkAlerts" in SRC


def test_session_expiry_honesty():
    assert "OFFICE.markSessionExpired" in SRC
    # scheduler 401 must not silently freeze anymore
    assert SRC.count("Session expire") >= 3


def test_battery_friendly_polling():
    assert SRC.count("document.hidden") >= 4
    assert "visibilitychange" in SRC
