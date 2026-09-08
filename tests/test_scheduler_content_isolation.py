"""W1.3 — `content` mega-job must isolate each engine.

Bug: the `content` job in `_run_job_inner` chained its first ~12 engines with NO
per-engine try/except. So if engine #1 (`auto_content.run_daily_content`) threw, the
exception unwound to the job's single outer except and engines #2..#12 were silently
skipped that run — content, video, schedule, autopost, cadence, dunning, etc. all
gone because one engine hiccuped.

Fix: each of those engines now runs through `_run_content_engine(name, coro)`, which
logs + contains a single engine's failure so the rest of the cycle still runs.
"""

from __future__ import annotations

import asyncio
import importlib


def _run(coro):
    return asyncio.run(coro)


# Every engine invoked by the `content` branch (module, attr). Patched to no-ops so
# the test stays fast/offline; #1 is overridden to raise and #12 to a spy.
_CONTENT_ENGINES = [
    ("app.marketing.auto_content", "run_daily_content"),  # 1
    ("app.marketing.video_ad_cycle", "run_cycle"),  # 2
    ("app.marketing.content_schedule", "run_due"),  # 3
    ("app.tasks.reporting", "run_social_autopost"),  # 4
    ("app.marketing.wa_campaign_runner", "run_due"),  # 5
    ("app.marketing.cadence", "run_due"),  # 6
    ("app.marketing.sales_pipeline", "run_pipeline"),  # 7
    ("app.billing.dunning", "run_due"),  # 8
    ("app.marketing.lifecycle_nurture", "run_due"),  # 9
    ("app.marketing.channel_experiments", "run_daily"),  # 10
    ("app.platform.booking_reminders", "run_due"),  # 11
    ("app.marketing.review_monitor", "run_check"),  # 12  (spy target)
    # already-try-wrapped tail — no-op'd so nothing heavy/networked runs:
    ("app.marketing.customer_crm", "run_wishes_if_enabled"),
    ("app.platform.service_reminders", "run_due_if_enabled"),
    ("app.marketing.newsletter", "run_due_if_enabled"),
    ("app.platform.winback", "run_due_if_enabled"),
    ("app.platform.rank_tracker", "run_if_enabled"),
    ("app.platform.customer_autopilot", "run_all"),
    ("app.platform.memory_vault", "sync_if_enabled"),
    ("app.platform.live_notes", "refresh_if_enabled"),
    ("app.agents.sales_team", "run_auto"),
    ("app.marketing.client_report", "run_monthly"),
]


def test_content_engine_failure_does_not_skip_later_engines(monkeypatch):
    import app.platform.team_scheduler as ts

    async def _noop(*a, **k):
        return None

    for mod_path, attr in _CONTENT_ENGINES:
        mod = importlib.import_module(mod_path)
        monkeypatch.setattr(mod, attr, _noop)

    calls = {"review_monitor": False}

    async def _boom(*a, **k):
        raise RuntimeError("auto_content exploded")

    async def _spy(*a, **k):
        calls["review_monitor"] = True

    import app.marketing.auto_content as ac
    import app.marketing.review_monitor as rm

    monkeypatch.setattr(ac, "run_daily_content", _boom)  # engine #1 blows up
    monkeypatch.setattr(rm, "run_check", _spy)  # engine #12 must still run

    _run(ts._run_job_inner("content"))

    assert calls["review_monitor"] is True, (
        "a later content engine must still run after an earlier one raises (W1.3 isolation)"
    )
