"""Email-enrichment pipeline fixes (2026-07-25).

Prod audit found the outreach funnel starving: 18,100 prospects, only 182
sendable. Root causes fixed here:

  1. ``lead_harvester.enrich_missing_emails`` re-tried the SAME head-of-file
     rows every run (no attempt marker) so the scan never advanced past the
     first few failures — 4,137 ready+website rows sat email-less.
  2. A found email never promoted ``needs_enrich``/``new`` -> ``ready``, so
     enriched rows stayed invisible to outreach (which only reads 'ready').
  3. ``udyam_pipeline`` ingested every row as ``status='new'`` — a status no
     job ever advances (1,736 rows stuck).
  4. The only bulk drain path awaited ``enrich_missing_emails`` INLINE in an HTTP
     request (live site fetches, hours) — now a bounded, lease-deduped,
     flag-gated Celery sweep on the existing ``scraping`` queue.
  5. ``scripts/backfill_prospect_status.py`` reclassifies the rows already
     stranded at ``new`` using the same ingest rule.

No email is ever sent by any of this; AUTO_EMAIL_OUTREACH stays untouched.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.platform import email_finder, lead_harvester, prospector, udyam_pipeline

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _write_store(path, rows) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _read_store(path) -> dict[str, dict]:
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                out[r["id"]] = r
    return out


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "prospects.jsonl"
    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(path))
    return path


def _fake_finder(monkeypatch, ok_marker: str = "ok."):
    """email_finder.find stub: websites containing ``ok_marker`` succeed."""
    calls: list[str] = []

    async def _find(website, owner_name="", max_results=3):
        calls.append(website)
        if ok_marker in (website or ""):
            return {"ok": True, "domain": website, "emails": [{"email": "info@found.example"}]}
        return {"ok": False, "domain": website, "emails": []}

    monkeypatch.setattr(email_finder, "find", _find)
    return calls


# ---------------------------------------------------------------------------
# enrich_missing_emails — scan must ADVANCE past previously-failed rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrich_advances_past_failed_rows(store, monkeypatch):
    monkeypatch.setenv("EMAIL_ENRICH_MAX_ATTEMPTS", "1")
    calls = _fake_finder(monkeypatch)
    _write_store(
        store,
        [
            {"id": "a", "status": "ready", "website": "https://fail-one.example", "email": ""},
            {"id": "b", "status": "ready", "website": "https://fail-two.example", "email": ""},
            {"id": "c", "status": "ready", "website": "https://ok.example", "email": ""},
        ],
    )

    r1 = await lead_harvester.enrich_missing_emails(limit=2)
    assert r1["tried"] == 2 and r1["found"] == 0
    rows = _read_store(store)
    assert rows["a"]["email_enrich_attempts"] == 1
    assert rows["b"]["email_enrich_attempts"] == 1
    assert "email_enrich_attempts" not in rows["c"]

    # Second run must SKIP the exhausted failures and reach row c —
    # the old code retried a+b forever and never got here.
    r2 = await lead_harvester.enrich_missing_emails(limit=2)
    assert r2["found"] == 1
    assert r2["skipped_exhausted"] == 2
    rows = _read_store(store)
    assert rows["c"]["email"] == "info@found.example"
    assert rows["a"].get("email", "") == "" and rows["b"].get("email", "") == ""
    assert calls == [
        "https://fail-one.example",
        "https://fail-two.example",
        "https://ok.example",
    ]


@pytest.mark.asyncio
async def test_enrich_bounded_attempts_never_retry_exhausted(store, monkeypatch):
    monkeypatch.setenv("EMAIL_ENRICH_MAX_ATTEMPTS", "1")
    calls = _fake_finder(monkeypatch)
    _write_store(
        store,
        [{"id": "a", "status": "ready", "website": "https://fail.example", "email": ""}],
    )

    await lead_harvester.enrich_missing_emails(limit=5)
    r2 = await lead_harvester.enrich_missing_emails(limit=5)
    assert r2["tried"] == 0 and r2["skipped_exhausted"] == 1
    assert len(calls) == 1  # finder never called again for an exhausted row


@pytest.mark.asyncio
async def test_enrich_promotes_needs_enrich_and_new_to_ready(store, monkeypatch):
    _fake_finder(monkeypatch)
    _write_store(
        store,
        [
            {"id": "n1", "status": "needs_enrich", "website": "https://ok.example", "email": ""},
            {"id": "n2", "status": "new", "website": "https://ok.example", "email": ""},
        ],
    )

    r = await lead_harvester.enrich_missing_emails(limit=5)
    assert r["found"] == 2
    rows = _read_store(store)
    assert rows["n1"]["status"] == "ready" and rows["n1"]["email"] == "info@found.example"
    assert rows["n2"]["status"] == "ready" and rows["n2"]["email"] == "info@found.example"


@pytest.mark.asyncio
async def test_enrich_never_touches_advanced_statuses(store, monkeypatch):
    _fake_finder(monkeypatch)
    _write_store(
        store,
        [
            {"id": "r1", "status": "ready", "website": "https://ok.example", "email": ""},
            {"id": "s1", "status": "sent", "website": "https://ok.example", "email": ""},
            {"id": "d1", "status": "dead", "website": "https://ok.example", "email": ""},
        ],
    )

    await lead_harvester.enrich_missing_emails(limit=5)
    rows = _read_store(store)
    # email fills in, but status is NEVER moved for non-new/needs_enrich rows
    assert rows["r1"]["status"] == "ready"
    assert rows["s1"]["status"] == "sent"
    assert rows["d1"]["status"] == "dead"
    assert all(rows[k]["email"] == "info@found.example" for k in ("r1", "s1", "d1"))


@pytest.mark.asyncio
async def test_enrich_skips_rows_without_website_or_with_email(store, monkeypatch):
    calls = _fake_finder(monkeypatch)
    _write_store(
        store,
        [
            {"id": "x1", "status": "needs_enrich", "website": "", "email": ""},
            {"id": "x2", "status": "ready", "website": "https://ok.example", "email": "have@x.in"},
        ],
    )

    r = await lead_harvester.enrich_missing_emails(limit=5)
    assert r["tried"] == 0 and calls == []


# ---------------------------------------------------------------------------
# udyam ingest — status must mirror harvester semantics, never black-hole "new"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_udyam_ingest_status_ready_or_needs_enrich(monkeypatch):
    monkeypatch.setenv("UDYAM_PIPELINE", "1")

    async def _seeds(city, limit):
        return [
            {"business_name": "Alpha Traders", "city": "Pune"},
            {"business_name": "Beta Services", "city": "Pune"},
        ]

    async def _maps(name, city, pincode=""):
        if name.startswith("Alpha"):
            return {"phone": "+919876543210", "website": "", "email": ""}
        return {}

    async def _web(website):
        return {"email": "", "phone": ""}

    monkeypatch.setattr(udyam_pipeline, "_udyam_seeds", _seeds)
    monkeypatch.setattr(udyam_pipeline, "_maps_enrich", _maps)
    monkeypatch.setattr(udyam_pipeline, "_web_enrich", _web)
    monkeypatch.setattr(lead_harvester, "_existing_keys", lambda: (set(), set()))
    stored: list[dict] = []
    monkeypatch.setattr(prospector, "_append", lambda rec: stored.append(rec) or True)

    res = await udyam_pipeline.run(limit=2, city="Pune")
    assert res["new"] == 2
    by = {r["business_name"]: r for r in stored}
    assert by["Alpha Traders"]["status"] == "ready"  # has phone -> outreachable pool
    assert by["Beta Services"]["status"] == "needs_enrich"  # no contact -> enrich sweep
    assert not any(r["status"] == "new" for r in stored)


# ---------------------------------------------------------------------------
# hard per-run deadline — a batch must never die unflushed inside Celery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrich_deadline_stops_early_but_keeps_progress(store, monkeypatch):
    """deadline_s expiring must break the scan AND still persist the attempt
    markers for rows already tried — otherwise a timed-out run leaves the file
    untouched and the next run repeats the same head rows (the original stall)."""
    monkeypatch.setenv("EMAIL_ENRICH_ROW_DELAY_S", "0")
    clock = {"t": 0.0}
    monkeypatch.setattr(lead_harvester.time, "monotonic", lambda: clock["t"])

    async def _find(website, owner_name="", max_results=3):
        clock["t"] += 40.0  # each row "takes" 40s of the budget
        return {"ok": False, "domain": website, "emails": []}

    monkeypatch.setattr(email_finder, "find", _find)
    _write_store(
        store,
        [
            {"id": f"r{i}", "status": "ready", "website": f"https://s{i}.example", "email": ""}
            for i in range(5)
        ],
    )

    r = await lead_harvester.enrich_missing_emails(limit=5, deadline_s=60)
    assert r["deadline_hit"] is True
    assert r["tried"] == 2  # row 3 starts after the 60s budget is gone
    rows = _read_store(store)
    assert rows["r0"]["email_enrich_attempts"] == 1
    assert rows["r1"]["email_enrich_attempts"] == 1
    assert "email_enrich_attempts" not in rows["r2"]


@pytest.mark.asyncio
async def test_enrich_no_deadline_is_unbounded_as_before(store, monkeypatch):
    monkeypatch.setenv("EMAIL_ENRICH_ROW_DELAY_S", "0")
    _fake_finder(monkeypatch)
    _write_store(
        store,
        [
            {"id": "a", "status": "ready", "website": "https://ok.example", "email": ""},
            {"id": "b", "status": "ready", "website": "https://ok.example", "email": ""},
        ],
    )
    r = await lead_harvester.enrich_missing_emails(limit=5)
    assert r["tried"] == 2 and r["deadline_hit"] is False


# ---------------------------------------------------------------------------
# Celery sweep task — flag gate, single-flight lease, bounded batching
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Minimal SET NX EX / GET / DELETE for the sweep's dedupe lease."""

    def __init__(self, preset: dict[str, str] | None = None):
        self.data: dict[str, str] = dict(preset or {})

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    def get(self, key):
        v = self.data.get(key)
        return v.encode() if isinstance(v, str) else v

    def delete(self, key):
        self.data.pop(key, None)
        return 1


@pytest.fixture
def sweep(monkeypatch):
    """The sweep task with its ledger write stubbed and delays disabled."""
    from app.tasks import scraping

    monkeypatch.setenv("EMAIL_ENRICH_ROW_DELAY_S", "0")
    monkeypatch.setattr(lead_harvester, "_append_run", lambda rec: None)
    return scraping


def test_sweep_inert_when_flag_off(sweep, monkeypatch):
    monkeypatch.delenv("EMAIL_ENRICH_SWEEP", raising=False)
    res = sweep.email_enrichment_sweep.run()
    assert res == {"status": "skipped", "reason": "flag_off", "flag": "EMAIL_ENRICH_SWEEP"}


def test_sweep_fails_closed_without_redis(sweep, monkeypatch):
    """No Redis = no dedupe guarantee. Two concurrent runs would each _read_all()
    and rewrite the whole JSONL, silently clobbering each other's markers — so
    refuse to run rather than risk it."""
    monkeypatch.setenv("EMAIL_ENRICH_SWEEP", "1")
    monkeypatch.setattr(sweep, "_sweep_redis", lambda: None)
    assert sweep.email_enrichment_sweep.run()["reason"] == "no_redis"


def test_sweep_single_flight_when_lease_held(sweep, monkeypatch):
    monkeypatch.setenv("EMAIL_ENRICH_SWEEP", "1")
    held = _FakeRedis({sweep._SWEEP_LEASE_KEY: "someone-else"})
    monkeypatch.setattr(sweep, "_sweep_redis", lambda: held)
    assert sweep.email_enrichment_sweep.run()["reason"] == "already_running"
    assert held.data[sweep._SWEEP_LEASE_KEY] == "someone-else"  # never stolen


def test_sweep_batches_and_releases_lease(sweep, store, monkeypatch):
    """5 rows at batch=2 must drain in bounded batches (one bulk write each) and
    release the lease so the next scheduled run can acquire it."""
    monkeypatch.setenv("EMAIL_ENRICH_SWEEP", "1")
    _fake_finder(monkeypatch)
    fake = _FakeRedis()
    monkeypatch.setattr(sweep, "_sweep_redis", lambda: fake)
    _write_store(
        store,
        [
            {"id": f"p{i}", "status": "needs_enrich", "website": "https://ok.example", "email": ""}
            for i in range(5)
        ],
    )

    res = sweep.email_enrichment_sweep.run(max_rows=10, batch=2)
    assert res["status"] == "completed"
    assert res["tried"] == 5 and res["found"] == 5
    assert res["batches"] == 3  # 2 + 2 + 1, i.e. one bulk write per batch
    assert res["stopped"] == "backlog_empty"
    assert sweep._SWEEP_LEASE_KEY not in fake.data  # lease released for the next run
    rows = _read_store(store)
    assert all(rows[f"p{i}"]["status"] == "ready" for i in range(5))


def test_sweep_respects_max_rows_cap(sweep, store, monkeypatch):
    monkeypatch.setenv("EMAIL_ENRICH_SWEEP", "1")
    _fake_finder(monkeypatch)
    monkeypatch.setattr(sweep, "_sweep_redis", lambda: _FakeRedis())
    _write_store(
        store,
        [
            {"id": f"p{i}", "status": "needs_enrich", "website": "https://ok.example", "email": ""}
            for i in range(10)
        ],
    )

    res = sweep.email_enrichment_sweep.run(max_rows=3, batch=2)
    assert res["tried"] == 3 and res["stopped"] == "rows_cap"
    rows = _read_store(store)
    assert sum(1 for i in range(10) if rows[f"p{i}"]["status"] == "ready") == 3


# ---------------------------------------------------------------------------
# scripts/backfill_prospect_status.py — one-time hygiene for stranded 'new' rows
# ---------------------------------------------------------------------------


def _backfill_module():
    import importlib.util

    path = ROOT / "scripts" / "backfill_prospect_status.py"
    spec = importlib.util.spec_from_file_location("backfill_prospect_status", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_backfill_plan_applies_ingest_rule_only_to_new_rows():
    bf = _backfill_module()
    p = bf.plan(
        [
            {"id": "p1", "status": "new", "phone": "+919876543210", "email": ""},
            {"id": "p2", "status": "new", "phone": "", "email": "a@b.example"},
            {"id": "p3", "status": "new", "phone": "", "email": ""},
            {"id": "p4", "status": "new", "phone": "N/A", "email": "-"},
            {"id": "p5", "status": "ready", "phone": "", "email": ""},
            {"id": "p6", "status": "dead", "phone": "+919876543211", "email": ""},
            {"id": "p7", "status": "replied", "phone": "", "email": "c@d.example"},
        ]
    )
    assert p["updates"] == {
        "p1": {"status": "ready"},
        "p2": {"status": "ready"},
        "p3": {"status": "needs_enrich"},
        "p4": {"status": "needs_enrich"},  # junk placeholders are not a contact
    }
    # ready / dead / replied are never re-touched — no downgrade, no resurrection
    assert not {"p5", "p6", "p7"} & set(p["updates"])
    assert p["stats"]["to_ready"] == 2 and p["stats"]["to_needs_enrich"] == 2


def test_backfill_dry_run_writes_nothing_then_apply_is_idempotent(store, monkeypatch):
    bf = _backfill_module()
    _write_store(
        store,
        [
            {"id": "p1", "status": "new", "phone": "+919876543210", "email": "", "source": "udyam"},
            {"id": "p2", "status": "new", "phone": "", "email": "", "source": "udyam"},
            {"id": "p3", "status": "ready", "phone": "", "email": "x@y.example", "source": "osm"},
        ],
    )
    before = store.read_text(encoding="utf-8")

    dry = bf.run(prospector, apply=False)
    assert dry["candidates"] == 2 and dry["applied"] is False
    assert store.read_text(encoding="utf-8") == before  # byte-identical

    applied = bf.run(prospector, apply=True)
    assert applied["applied"] is True and applied["updated"] == 2
    assert not applied.get("mismatch")
    rows = _read_store(store)
    assert rows["p1"]["status"] == "ready"
    assert rows["p2"]["status"] == "needs_enrich"
    assert rows["p3"]["status"] == "ready"  # untouched

    # Re-run: no rows left at 'new' -> zero candidates and NO write at all.
    after = store.read_text(encoding="utf-8")
    again = bf.run(prospector, apply=True)
    assert again["candidates"] == 0 and again["applied"] is False
    assert store.read_text(encoding="utf-8") == after
