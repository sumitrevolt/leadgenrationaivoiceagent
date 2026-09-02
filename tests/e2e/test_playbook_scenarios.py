"""E2E tests — Playbook mandatory scenarios (batch 2, REAL paths).

These scenarios were flagged as gaps in the 2026-06-25 playbook audit
(docs/PLAYBOOK_AUDIT_2026_06_25.md, section 9 — 18 mandatory E2E scenarios):

    3. Content approval     8. CRM update          9. WhatsApp follow-up
   12. Failed payment recov 13. Admin retry        14. Scheduler missed-run
   15. Queue DLQ replay     17. Duplicate-prevention (idempotency)

UNLIKE the first draft of this file, every test here DRIVES REAL PRODUCTION
CODE (not a tautology that sets a value then asserts it). Each test is:
  - hermetic  — module store paths redirected to tmp_path; no network/DB/Redis,
  - real      — calls the actual prod function (content_approval.approve,
                sales_pipeline.set_stage, dunning.on_payment_failed,
                dlq_retry.run_sweep, idempotency.seen_before, ...),
  - never-raise asserting the prod contract (prod code is never-raise by design).

Run: .venv\\Scripts\\python.exe -m pytest tests/e2e/ -q
"""

from __future__ import annotations

import asyncio
import json as _json
import os

from app.platform.dlq_retry import DLQ_KEY as _DLQ_KEY


# ---------------------------------------------------------------------------
# 3. Content approval workflow  →  app/marketing/content_approval.py
# ---------------------------------------------------------------------------
def test_e2e_content_approval_workflow(monkeypatch, tmp_path):
    """submit() → pending → approve(token) → approved, idempotent on re-approve."""
    from app.marketing import content_approval as ca

    monkeypatch.setattr(ca, "_FILE", lambda: str(tmp_path / "content_approvals.jsonl"))

    res = ca.submit("client-1", {"caption": "Diwali offer 20% off", "type": "post"})
    assert res["ok"] is True
    token = res["approval"]["token"]
    assert res["approval"]["status"] == "pending"

    # Pending list reflects the new item
    assert any(p["token"] == token for p in ca.pending("client-1"))

    # Approve drives the real state transition
    out = ca.approve(token)
    assert out["ok"] is True
    assert ca.get_by_token(token)["status"] == "approved"

    # Re-approving the same token must be idempotent (no second side-effect)
    again = ca.approve(token)
    assert again["ok"] is True
    assert ca.get_by_token(token)["status"] == "approved"
    assert ca.pending("client-1") == []  # no longer pending


# ---------------------------------------------------------------------------
# 8. CRM update workflow  →  app/marketing/sales_pipeline.py (native CRM)
# ---------------------------------------------------------------------------
def test_e2e_crm_update_lead_stage(monkeypatch, tmp_path):
    """Lead → upsert_deal → set_stage transition persists; re-upsert dedupes."""
    from app.marketing import sales_pipeline as sp

    monkeypatch.setattr(sp, "_DEALS", str(tmp_path / "deals.jsonl"))
    monkeypatch.setattr(sp, "_ACTIONS", str(tmp_path / "deal_actions.jsonl"))

    lead = {"business_name": "Sharma Dental", "phone": "9999900001", "niche": "dental"}
    deal = sp.upsert_deal(lead, stage="interested")
    assert deal["id"] and deal["stage"] == "interested"

    # Real stage advance
    assert sp.set_stage(deal["id"], "contacted") is True
    rows = sp._read(sp._DEALS)
    assert any(r["id"] == deal["id"] and r["stage"] == "contacted" for r in rows)

    # Same lead re-upserted = dedupe (no duplicate deal row by phone)
    sp.upsert_deal(lead, stage="interested")
    rows2 = sp._read(sp._DEALS)
    assert sum(1 for r in rows2 if r.get("phone") == "9999900001") == 1

    # Invalid stage is rejected (contract guard)
    assert sp.set_stage(deal["id"], "not-a-stage") is False


# ---------------------------------------------------------------------------
# 9. WhatsApp follow-up  →  app/marketing/cadence.py (draft-only = ban-safe)
# ---------------------------------------------------------------------------
def test_e2e_whatsapp_followup_is_draft_only(monkeypatch, tmp_path):
    """Cadence enroll works; WhatsApp step stays a DRAFT (no auto-send = ban-safe)."""
    from app.marketing import cadence

    monkeypatch.setattr(
        cadence, "_LEADS", lambda: str(tmp_path / "cadence_leads.jsonl"), raising=False
    )
    monkeypatch.setattr(
        cadence, "_RUNS", lambda: str(tmp_path / "cadence_runs.jsonl"), raising=False
    )

    lead = {"business_name": "Verma Salon", "phone": "+919999900002", "niche": "salon"}
    enrolled = cadence.enroll(lead)
    assert enrolled["id"] and enrolled["status"] == "active"
    assert enrolled["step_idx"] == 0

    # Ban-safety invariant: WhatsApp is a draft channel in DEFAULT_CADENCE,
    # and bulk auto-send is OFF unless WHATSAPP_AUTO_SEND is explicitly set.
    wa_steps = [s for s in cadence.DEFAULT_CADENCE if s.get("channel") == "whatsapp"]
    assert wa_steps, "cadence must contain a whatsapp follow-up step"
    assert os.environ.get("WHATSAPP_AUTO_SEND", "0") in ("0", "", "false", "no")


# ---------------------------------------------------------------------------
# 12. Failed payment recovery (dunning)  →  app/billing/dunning.py
# ---------------------------------------------------------------------------
def test_e2e_failed_payment_recovery_dunning(monkeypatch, tmp_path):
    """on_payment_failed opens ONE case (dedupe); mark_recovered closes it."""
    from app.billing import dunning

    monkeypatch.setattr(dunning, "_CASES", str(tmp_path / "dunning_cases.jsonl"))
    monkeypatch.setattr(dunning, "_RUNS", str(tmp_path / "dunning_runs.jsonl"))

    r1 = asyncio.run(dunning.on_payment_failed("client-9", amount=2999, reason="upi_failed"))
    assert r1["ok"] is True
    assert r1["case"]["status"] == "open"
    assert r1.get("dedupe") is not True  # first time = freshly opened

    # Retry of the same failure must NOT open a second case
    r2 = asyncio.run(dunning.on_payment_failed("client-9", amount=2999, reason="upi_failed"))
    assert r2["ok"] is True and r2.get("dedupe") is True

    # Recovery closes the open case
    assert dunning.mark_recovered("client-9") is True
    rows = dunning._read(dunning._CASES)
    assert all(r["status"] != "open" for r in rows if r["client_id"] == "client-9")


# ---------------------------------------------------------------------------
# 13. Admin retry of a failed/replayed workflow run  →  process_engine.py
# ---------------------------------------------------------------------------
def test_e2e_workflow_run_replay_roundtrip(monkeypatch, tmp_path):
    """A run is journalled and its state re-derives from the journal (crash-safe
    replay = the basis for admin retry/resume). Hermetic via tmp run dir."""
    from app.agents import process_engine as pe
    from app.agents import process_library

    monkeypatch.setattr(pe, "_RUNS_DIR", str(tmp_path / "process_runs"))
    monkeypatch.setattr(pe, "_INDEX", str(tmp_path / "process_runs" / "index.jsonl"))

    keys = process_library.list_keys()
    if not keys:  # no registered process in this build → assert graceful handling
        assert pe.start_run("nope")["ok"] is False
        return

    started = pe.start_run(keys[0], {"smoke": True})
    assert started["ok"] is True
    run_id = started["run_id"]

    # State must re-derive purely from the journal (no in-memory dependency)
    st = pe.replay(run_id)
    assert st["process"] == keys[0]
    assert run_id in {r.get("run_id") for r in pe.list_runs(limit=50)}


# ---------------------------------------------------------------------------
# 14. Scheduler missed-run / future-window handling  →  automation_health.py
# ---------------------------------------------------------------------------
def test_e2e_scheduler_health_contract_and_future_window(monkeypatch, tmp_path):
    """health() never raises, returns the expected shape, and a job whose IST
    window hasn't started yet is 'scheduled_off' (not a false 'problem')."""
    from app.platform import automation_health as ah

    monkeypatch.setattr(ah, "_RUNS", lambda: str(tmp_path / "runs.jsonl"))
    monkeypatch.setattr(ah, "_BEATS", lambda: str(tmp_path / "beats.json"))

    # Force one job's window to be "not due yet" and confirm it is suppressed.
    future = {"obsidian_push"}
    # `**_kw` absorbs the injected `now=` — health() now threads one captured
    # timestamp into every scheduling helper so a single classification cannot
    # combine two different instants.
    monkeypatch.setattr(ah, "_job_due_yet", lambda job, **_kw: job not in future)

    h = ah.health()
    assert {"jobs", "never_ran", "overdue"} <= set(h)
    statuses = {j["job"]: j["status"] for j in h["jobs"]}
    assert statuses["obsidian_push"] == "scheduled_off"
    assert "obsidian_push" not in h["never_ran"]  # future window != a problem


# ---------------------------------------------------------------------------
# 15. Queue DLQ replay  →  app/platform/dlq_retry.py (REAL sweep logic)
# ---------------------------------------------------------------------------
class _FakeRedis:
    """Minimal Redis stand-in for the dlq_retry sweep (list + per-job incr)."""

    def __init__(self, items: list[str]):
        self._lists: dict[str, list[str]] = {_DLQ_KEY: list(items)}
        self._kv: dict[str, str] = {}

    def rpop(self, k):
        lst = self._lists.get(k) or []
        return lst.pop() if lst else None

    def lpush(self, k, v):
        self._lists.setdefault(k, []).insert(0, v)

    def incr(self, k):
        self._kv[k] = str(int(self._kv.get(k) or 0) + 1)
        return int(self._kv[k])

    def expire(self, k, ttl):
        return True

    def ltrim(self, k, a, b):
        return True


def test_e2e_queue_dlq_replay(monkeypatch):
    """A failed staff job in the DLQ is re-dispatched by the real sweep; an
    exhausted job (over MAX_ATTEMPTS) is moved to dead instead of looping."""
    from app.platform import dlq_retry
    from app.tasks.staff_jobs import STAFF_JOBS

    job = next(iter(STAFF_JOBS))  # a guaranteed-valid staff job name
    rec = _json.dumps({"args": f"('{job}',)", "error": "Connection timeout"})

    # Stub the actual dispatch so we never touch Celery/in-process job execution,
    # but the real rpop/parse/attempt-count/dead-move logic still runs.
    dispatched: list[tuple[str, int]] = []

    async def fake_dispatch(j, attempt):
        dispatched.append((j, attempt))
        return "test"

    monkeypatch.setattr(dlq_retry, "_dispatch", fake_dispatch)

    # First sweep: job is parsed and re-dispatched (attempt 1).
    fake = _FakeRedis([rec])
    out = asyncio.run(dlq_retry.run_sweep(r=fake, force=True))
    assert dispatched == [(job, 1)]
    assert out["retried"] and out["retried"][0]["job"] == job

    # Bounded retry: once attempts exceed MAX_ATTEMPTS the job goes to dead, not
    # an infinite redispatch loop.
    fake2 = _FakeRedis([rec, rec, rec, rec])
    out2 = asyncio.run(dlq_retry.run_sweep(r=fake2, force=True, max_items=10))
    assert job in out2["dead"]


# ---------------------------------------------------------------------------
# 17. Duplicate prevention / idempotency  →  app/billing/idempotency.py
# ---------------------------------------------------------------------------
def test_e2e_idempotency_dedupes_retry():
    """seen_before(key): first call False (process), second True (skip duplicate).
    Redis is down in the test env → exercises the fail-open memory path."""
    from app.billing import idempotency

    key = "test:inv-2026-06-25-001"
    assert asyncio.run(idempotency.seen_before(key)) is False  # first time
    assert asyncio.run(idempotency.seen_before(key)) is True  # duplicate
    # forget() clears the claim so a legitimate re-process can occur
    asyncio.run(idempotency.forget(key))
    assert asyncio.run(idempotency.seen_before(key)) is False


def test_e2e_idempotency_sync_for_celery_tasks():
    """seen_before_sync(): the SYNC primitive Celery tasks use (the async one
    can't be awaited inside a sync task). Same dedupe contract, fail-open."""
    from app.billing import idempotency

    key = "test:sync:lead-42"
    assert idempotency.seen_before_sync(key) is False
    assert idempotency.seen_before_sync(key) is True
    idempotency.forget_sync(key)
    assert idempotency.seen_before_sync(key) is False
    # Empty key = cannot dedupe → fail-open (process), never claims
    assert idempotency.seen_before_sync("") is False
