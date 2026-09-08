"""today_overview — plain-Hinglish '🏠 Aaj' admin snapshot.

Guards the admin-friendly contract: build() never raises, returns the expected
shape, and every scheduled job has a human Hinglish label (no raw job-keys leak
to the non-technical admin's home tab).
"""

from datetime import datetime as real_datetime

from app.platform import today_overview


def test_build_shape_never_raises():
    d = today_overview.build()
    for k in ("headline", "problems", "staff", "jobs", "flags_off", "totals", "at"):
        assert k in d
    assert isinstance(d["headline"], str) and d["headline"]
    assert isinstance(d["problems"], list)
    assert isinstance(d["jobs"], list)


# --------------------------------------------------------------------------- #
# 2026-07-24: admin ne '841 Aaj ke kaam' ko PENDING boss-work samjha, jabki wo
# aaj auto ho-CHUKA kaam (events_today) hai. Fix: needs_decision = asli pending
# approvals backlog (approvals_bridge), taaki boss ko sirf sach dikhe.
# --------------------------------------------------------------------------- #
def test_totals_has_needs_decision_field():
    """events_today = auto-done; needs_decision = asli boss-decision backlog."""
    d = today_overview.build()
    assert "needs_decision" in d["totals"]
    assert isinstance(d["totals"]["needs_decision"], int)
    assert d["totals"]["needs_decision"] >= 0


def test_needs_decision_pulls_from_approvals_bridge(monkeypatch):
    import app.platform.approvals_bridge as approvals_bridge

    def _drafts(include_decided=False):
        return {"drafts": [], "counts": {"by_source": {"sales": 3}, "pending": 3}}

    monkeypatch.setattr(approvals_bridge, "list_drafts", _drafts)
    d = today_overview.build()
    assert d["totals"]["needs_decision"] == 3


def test_needs_decision_fail_open_zero(monkeypatch):
    """Bridge toote/creds na ho to 0 (fail-open) — kabhi false 'pending' alarm nahi."""
    import app.platform.approvals_bridge as approvals_bridge

    def _boom(include_decided=False):
        raise RuntimeError("store down")

    monkeypatch.setattr(approvals_bridge, "list_drafts", _boom)
    d = today_overview.build()
    assert d["totals"]["needs_decision"] == 0


def test_headline_says_auto_done_not_pending(monkeypatch):
    """Jab kaam auto ho-chuka ho aur koi approval pending na ho, headline 'KIYE'
    (past, done) bole + 'kuch atka nahi' — NOT 'pending boss work'."""
    import app.platform.approvals_bridge as approvals_bridge
    import app.platform.team as team

    monkeypatch.setattr(
        approvals_bridge, "list_drafts", lambda include_decided=False: {"counts": {"pending": 0}}
    )
    monkeypatch.setattr(
        team,
        "team_status",
        lambda: {
            "members": [{"key": "rohan", "name": "Rohan", "state": "active", "today_actions": 841}]
        },
    )
    d = today_overview.build()
    if not d["problems"]:
        assert "KIYE" in d["headline"]
        assert "atka nahi" in d["headline"]


def test_problems_are_actionable():
    """Every surfaced problem must carry an actionable 'fix' (pattern rule)."""
    for p in today_overview.build().get("problems", []):
        assert p.get("kya"), "problem needs a 'kya'"
        assert p.get("fix"), "problem needs an actionable 'fix'"


def test_job_info_covers_every_scheduled_job():
    """Parity guard: each scheduler job has a Hinglish label so the 'Aaj' tab
    never shows a raw job-key. Add a new scheduler job -> add JOB_INFO too."""
    from app.platform.team_scheduler import _last_ran

    missing = sorted(set(_last_ran) - set(today_overview.JOB_INFO))
    assert not missing, f"JOB_INFO missing Hinglish labels for: {missing}"


def test_prospect_label_matches_job_meta_owner():
    """JOB_META prospect.owner=rohan — UI must not blame Dev (KNOWN_DRIFT class)."""
    info = today_overview.JOB_INFO["prospect"]
    assert "Rohan" in info["label"]
    assert "Dev" not in info["label"]
    assert "Rohan" in today_overview.JOB_INFO["evening_prospect"]["label"]


def test_new_jobs_labelled():
    for key in (
        "revenue_snapshot",
        "meter_watch",
        "process_autostart",
        "engineer_dbre",
        "engineer_dataquality",
        "engineer_deps",
        "obsidian_push",
    ):
        info = today_overview.JOB_INFO.get(key)
        assert info and info.get("label") and info.get("kya")


# --------------------------------------------------------------------------- #
# ADR-104 Phase F (2026-07-15): build()'s problems[] only ever checked
# queue_backlogged (live celery/heavy depth) -- dead_tasks_present and
# retryable_failed_present (Phase B authoritative fields off the SAME
# automation_health.health() call already made a few lines above) were never
# read. Live discovery: /app/control-center's Problems panel and
# /app/automation's "Aaj" tab (both fed by this exact function) said "Koi
# problem nahi mili" while 4 tasks sat dead/exhausted.
# --------------------------------------------------------------------------- #
def test_dead_tasks_present_surfaces_as_an_actionable_problem(monkeypatch):
    import app.platform.automation_health as automation_health

    def _health():
        return {
            "jobs": [],
            "overdue": [],
            "never_ran": [],
            "queue": {"celery": 0, "heavy": 0, "dlq": 0, "dead": 4},
            "queue_backlogged": False,
            "dead_tasks_present": True,
            "retryable_failed_present": False,
        }

    monkeypatch.setattr(automation_health, "health", _health)
    d = today_overview.build()
    dead_problems = [
        p
        for p in d["problems"]
        if "stuck" in p["kya"].lower() or "dead" in p["kya"] or "exhausted" in p["kya"]
    ]
    assert dead_problems, f"expected a dead/exhausted problem, got: {d['problems']}"
    assert dead_problems[0]["fix"]
    assert dead_problems[0].get("href") == "/app/office#reliability"


def test_retryable_failed_present_surfaces_when_not_already_backlogged(monkeypatch):
    """Avoid a duplicate/redundant entry when queue_backlogged already covers it --
    only add the dedicated retry-failed problem when backlog isn't already flagged."""
    import app.platform.automation_health as automation_health

    def _health():
        return {
            "jobs": [],
            "overdue": [],
            "never_ran": [],
            "queue": {"celery": 0, "heavy": 0, "dlq": 7, "dead": 0},
            "queue_backlogged": False,
            "dead_tasks_present": False,
            "retryable_failed_present": True,
        }

    monkeypatch.setattr(automation_health, "health", _health)
    d = today_overview.build()
    retry_problems = [
        p
        for p in d["problems"]
        if ("DLQ" in p["kya"] or "dubara try" in p["kya"]) and "retry-able" in p["kya"]
    ]
    assert retry_problems, f"expected a retry-able DLQ problem, got: {d['problems']}"
    assert retry_problems[0].get("href") == "/app/office#reliability"


def test_future_scheduled_jobs_are_not_due_yet(monkeypatch):
    class FakeDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 6, 26, 0, 58, tzinfo=tz)

    monkeypatch.setattr(today_overview, "datetime", FakeDateTime)

    assert today_overview._job_due_yet("obsidian_push") is False
    assert today_overview._job_due_yet("engineer_dbre") is False
    assert today_overview._job_due_yet("engineer_dataquality") is False
    assert today_overview._job_due_today("engineer_deps") is False
    assert today_overview._job_due_yet("revenue_snapshot") is True


def test_hot_queue_pending_surfaces_as_first_problem(monkeypatch):
    from app.platform import reply_agent

    monkeypatch.setattr(
        reply_agent,
        "hot_queue",
        lambda **_kw: [{"hq_id": "x1"}, {"hq_id": "x2"}],
    )
    d = today_overview.build()
    assert d["totals"].get("hot_queue") == 2
    hq = [p for p in d["problems"] if "Hot Queue" in p["kya"] or "garam replies" in p["kya"]]
    assert hq, d["problems"]
    assert hq[0]["href"] == "/app/inbox"
    assert d["problems"][0]["href"] == "/app/inbox"


def test_totals_include_owner_money_path_fields():
    d = today_overview.build()
    t = d["totals"]
    for key in (
        "paid_today",
        "activations_today",
        "paid_gross_today_inr",
        "upi_pending",
        "upi_needs_owner",
        "upi_needs_bind",
        "upi_starts_today",
        "onboard_waiting",
        "onboard_running",
        "onboard_failed",
        "dsh_runtime",
        "staff_bus",
        "delivery_at_risk",
        "automation_failures",
        "top_blocker",
        "reviews_sent",
        "drip_emails_sent",
        "drip_emails_opened",
        "forms_submitted",
        "proposals_accepted",
        "reminders_sent",
        "health_at_risk",
        "review_monitor",
        "form_builder",
        "proposal_builder",
        "booking_reminders",
        "client_health_alerts",
        "email_tracking",
    ):
        assert key in t, f"missing totals.{key}"
    assert t["dsh_runtime"] in ("on", "off", "unset")
    assert t["staff_bus"] in ("on", "off", "unset")
    assert t["form_builder"] in ("on", "off", "unset")
    assert t["proposal_builder"] in ("on", "off", "unset")
    assert isinstance(t["upi_needs_owner"], int)
    assert t["upi_needs_owner"] >= 0
    for k in (
        "reviews_sent",
        "drip_emails_sent",
        "drip_emails_opened",
        "forms_submitted",
        "proposals_accepted",
        "reminders_sent",
        "health_at_risk",
    ):
        assert isinstance(t[k], int) and t[k] >= 0


def test_env_tri_state_never_leaks_raw(monkeypatch):
    monkeypatch.setenv("DSH_RUNTIME_ENABLED", "1")
    assert today_overview._env_tri_state("DSH_RUNTIME_ENABLED") == "on"
    monkeypatch.setenv("DSH_RUNTIME_ENABLED", "0")
    assert today_overview._env_tri_state("DSH_RUNTIME_ENABLED") == "off"
    monkeypatch.delenv("DSH_RUNTIME_ENABLED", raising=False)
    assert today_overview._env_tri_state("DSH_RUNTIME_ENABLED") == "unset"


def test_upi_queue_fail_open(monkeypatch):
    import app.platform.upi_payments as upi_payments

    def _boom(*_a, **_k):
        raise RuntimeError("store down")

    monkeypatch.setattr(upi_payments, "list_actionable", _boom)
    monkeypatch.setattr(upi_payments, "list_payments", _boom)
    q = today_overview._upi_owner_queue()
    assert q["upi_needs_owner"] == 0
    assert q["upi_starts_today"] == 0


def test_marketing_feature_totals_fail_open(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("store down")

    monkeypatch.setattr("app.marketing.review_automation.get_sequence_stats", _boom, raising=False)
    monkeypatch.setattr("app.marketing.email_drips.get_drip_stats", _boom, raising=False)
    monkeypatch.setattr("app.marketing.form_builder.get_form_stats", _boom, raising=False)
    monkeypatch.setattr("app.marketing.proposal_builder.get_proposal_stats", _boom, raising=False)
    monkeypatch.setattr(
        "app.marketing.appointment_reminders.get_reminder_stats", _boom, raising=False
    )
    monkeypatch.setattr("app.marketing.customer_health.get_health_summary", _boom, raising=False)
    t = today_overview._marketing_feature_totals()
    assert t["reviews_sent"] == 0
    assert t["drip_emails_sent"] == 0
    assert t["drip_emails_opened"] == 0
    assert t["forms_submitted"] == 0
    assert t["proposals_accepted"] == 0
    assert t["reminders_sent"] == 0
    assert t["health_at_risk"] == 0
    assert t["form_builder"] in ("on", "off", "unset")


def test_marketing_feature_totals_maps_store_counts(monkeypatch):
    """Reviews = requests sent, not Google review pixels. Opens come from drip runs."""
    monkeypatch.setattr(
        "app.marketing.review_automation.get_sequence_stats",
        lambda **_k: {"sent": 3, "google_reviews": 99},
    )
    monkeypatch.setattr(
        "app.marketing.email_drips.get_drip_stats",
        lambda **_k: {"total_emails_sent": 4, "opened": 1},
    )
    monkeypatch.setattr(
        "app.marketing.form_builder.get_form_stats",
        lambda **_k: {"total_responses": 5, "total_forms": 9},
    )
    monkeypatch.setattr(
        "app.marketing.proposal_builder.get_proposal_stats",
        lambda **_k: {"accepted": 2, "sent": 7},
    )
    monkeypatch.setattr(
        "app.marketing.appointment_reminders.get_reminder_stats",
        lambda **_k: {"sent": 6},
    )
    monkeypatch.setattr(
        "app.marketing.customer_health.get_health_summary",
        lambda **_k: {"at_risk": 8, "critical": 1},
    )
    t = today_overview._marketing_feature_totals()
    assert t["reviews_sent"] == 3
    assert t["drip_emails_sent"] == 4
    assert t["drip_emails_opened"] == 1
    assert t["forms_submitted"] == 5
    assert t["proposals_accepted"] == 2
    assert t["reminders_sent"] == 6
    assert t["health_at_risk"] == 8
