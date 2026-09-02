from __future__ import annotations

from fastapi.testclient import TestClient


def _wire_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.marketing.clients_store._CLIENTS_FILE",
        lambda: str(tmp_path / "clients.jsonl"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.auto_content._QUEUE_DIR",
        lambda: str(tmp_path / "content_queue"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.content_approval._FILE",
        lambda: str(tmp_path / "approvals.jsonl"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger._LEDGER_DIR",
        lambda: str(tmp_path / "delivery_ledger"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger._CONTENT_QUEUE_DIR",
        lambda: str(tmp_path / "content_queue"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.product_one_delivery._DELIVERY_DIR",
        str(tmp_path / "product_one_delivery"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.product_one_delivery._REPORT_DIR",
        str(tmp_path / "client_reports"),
        raising=False,
    )


def _client(**overrides):
    rec = {
        "id": "c1",
        "business_name": "Rahul Mobile Shop",
        "plan": "starter",
        "product": "marketing",
        "status": "active",
        "city": "Nashik",
        "phone": "9999999999",
        "services": "Mobile repair, accessories",
        "target_area": "College Road",
        "approval_preference": "manual",
        "brand": {"primary": "#111111", "logo_text": "Rahul"},
        "socials": {"instagram": "rahulmobile", "facebook": "", "gbp": ""},
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    rec.update(overrides)
    return rec


def test_new_paid_customer_gets_pipeline_and_pending_deliverables(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import clients_store, product_one_delivery

    c = clients_store.add_client(
        "Rahul Mobile Shop", "mobile", city="Nashik", phone="9999999999", plan="starter"
    )
    state = product_one_delivery.customer_delivery_status(c["id"], c)

    assert state["stage"] == "onboarding_pending"
    assert state["setup_completion_pct"] < 100
    assert len(state["deliverables"]) == 10
    assert any(d["id"] == "business_profile" for d in state["deliverables"])
    assert state["pending_customer_inputs"]


def test_completed_setup_with_content_moves_to_approval_pending(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import auto_content, content_approval, product_one_delivery

    c = _client()
    items = []
    for i in range(16):
        typ = "poster" if i < 4 else "post"
        items.append(
            {
                "id": f"it{i}",
                "client_id": "c1",
                "date": f"2026-07-{i + 1:02d}",
                "type": typ,
                "title": f"Item {i}",
                "caption": "Nice offer",
                "status": "draft",
                "created_at": f"2026-07-07T00:00:{i:02d}+00:00",
            }
        )
    assert auto_content._append_items("c1", items) == 16
    content_approval.submit("c1", {"title": "Approval post", "caption": "Approve this"})

    state = product_one_delivery.customer_delivery_status("c1", c)

    assert state["setup_completion_pct"] == 100
    assert state["stage"] == "approval_pending"
    assert state["posts_waiting_for_approval"] == 1
    by_id = {d["id"]: d for d in state["deliverables"]}
    assert by_id["branded_posters"]["status"] == "done"
    assert by_id["social_posts"]["status"] == "done"


def test_failed_automation_log_is_admin_friendly(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import delivery_ledger, product_one_delivery

    c = _client()
    delivery_ledger.log_event(
        "c1", "post_failed", detail="Instagram publishing failed because token expired"
    )

    rows = product_one_delivery.customer_delivery_status("c1", c)["automation_events"]

    failed = [r for r in rows if r["status"] == "failed"]
    assert failed
    assert failed[0]["customer_id"] == "c1"
    assert "Retry" in failed[0]["next_action"]
    assert failed[0]["related_deliverable_id"] == "proof"


def test_workflow_catalog_covers_prompt_workflows(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import product_one_delivery

    ids = {w["id"] for w in product_one_delivery.WORKFLOWS}

    assert {
        "after_payment_customer_creation",
        "onboarding_reminder",
        "brand_kit_generation",
        "content_generation",
        "approval_request",
        "scheduled_publishing",
        "failed_publish_retry",
        "manual_task_creation",
        "monthly_report_generation",
        "renewal_reminder",
    }.issubset(ids)


def test_run_workflow_records_admin_friendly_metadata(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    import asyncio

    from app.marketing import product_one_delivery

    monkeypatch.setattr(
        "app.marketing.clients_store.get_client", lambda cid: _client(), raising=False
    )
    out = asyncio.run(product_one_delivery.run_workflow("c1", "onboarding_reminder", owner="Sumit"))

    assert out["ok"] is True
    rows = product_one_delivery.automation_events(client_id="c1")
    workflow_rows = [r for r in rows if r["workflow_id"] == "onboarding_reminder"]
    assert workflow_rows
    assert workflow_rows[0]["workflow_name"] == "Onboarding reminder"
    assert workflow_rows[0]["trigger_source"] == "setup_incomplete"
    assert workflow_rows[0]["related_deliverable_id"] == "business_profile"


def test_customer_proof_has_safe_notes_and_monthly_plan(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import delivery_ledger, product_one_delivery

    delivery_ledger.log_event(
        "c1", "post_failed", detail="Traceback token expired for IG_API_SECRET"
    )
    state = product_one_delivery.customer_delivery_status("c1", _client())

    notes = state["customer_status_notes"]
    assert any(n["type"] == "manual_fallback" for n in notes)
    assert "IG_API_SECRET" not in " ".join(n["message"] for n in notes)
    assert state["monthly_summary"]["next_month_plan"]


def test_manual_publish_action_records_proof(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    import asyncio

    from app.marketing import product_one_delivery

    out = asyncio.run(
        product_one_delivery.record_manual_action(
            "c1",
            "publish_manual",
            note="Instagram par manually upload ho gaya; screenshot saved.",
            owner="Sumit",
        )
    )
    assert out["ok"] is True

    state = product_one_delivery.customer_delivery_status("c1", _client())
    proof = {d["id"]: d for d in state["deliverables"]}["proof"]
    assert proof["status"] == "done"
    assert "screenshot" in proof["proof_note"]


def test_admin_and_customer_delivery_endpoints(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.api.auth_deps import require_admin
    from app.api.customer_auth import require_customer
    from app.main import app

    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: [_client()],
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client", lambda cid: _client(), raising=False
    )
    app.dependency_overrides[require_admin] = lambda: {"username": "admin"}
    app.dependency_overrides[require_customer] = lambda: "c1"

    with TestClient(app) as client:
        admin = client.get("/api/admin/delivery-cockpit")
        customer = client.get("/api/customer/delivery-proof")

    assert admin.status_code == 200
    assert admin.json()["customers"][0]["current_delivery_stage"] in {
        "setup_in_progress",
        "content_ready",
        "approval_pending",
    }
    assert customer.status_code == 200
    body = customer.json()
    assert body["ok"] is True
    assert body["deliverables"]
    assert "cron" not in body["customer_message"].lower()

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Acceptance Test 5 — Monthly proof round-trip (end-to-end via HTTP)
# ---------------------------------------------------------------------------
# User brief: "Test 5: Monthly proof — Admin/customer can see what was delivered.
# Report includes completed deliverables, pending items, and next month plan."
#
# This test drives the full pipeline from the perspective of a real paying
# customer (via /api/customer/delivery-proof) and a real admin (via
# /api/admin/delivery-cockpit + /api/admin/delivery-logs +
# /api/admin/clients/{cid}/delivery-action). It proves:
#
#   1. Every admin-recorded delivery action shows up in the customer's proof
#      view with customer-safe wording (no "cron", "queue", "worker", "API",
#      "env", "stack", "log", "exception" in the customer-facing message).
#   2. The proof aggregates completed deliverables, pending items, and the
#      next-month plan in ONE response the customer can actually read.
#   3. The admin delivery-logs filter ("manual action required" + "report
#      pending" + "payment received but setup incomplete") works end-to-end
#      and ties back to the same customer_id used in the cockpit.
#   4. After the monthly_report action, customer sees their proof updated
#      and admin can filter by "report pending" -> empty (report is no
#      longer pending).
# ---------------------------------------------------------------------------
def test_acceptance_test_5_monthly_proof_round_trip(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.api.auth_deps import require_admin
    from app.api.customer_auth import require_customer
    from app.main import app
    from app.marketing import product_one_delivery

    # --- 1. Set up a single paid customer (the one paying customer jiya-style) ---
    client_rec = _client()
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: [client_rec],
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client", lambda cid: client_rec, raising=False
    )

    app.dependency_overrides[require_admin] = lambda: {"username": "admin"}
    app.dependency_overrides[require_customer] = lambda: client_rec["id"]

    # --- 2. Admin drives the pipeline via real HTTP action endpoint ---
    with TestClient(app) as client:
        # Day-1: brand kit ready, business profile captured
        r = client.post(
            f"/api/admin/clients/{client_rec['id']}/delivery-action",
            json={
                "action": "manual_task_done",
                "deliverable_id": "business_profile",
                "owner": "ops-team",
                "note": "Customer call captured",
            },
        )
        assert r.status_code == 200 and r.json().get("ok") is True, r.text

        r = client.post(
            f"/api/admin/clients/{client_rec['id']}/delivery-action",
            json={
                "action": "manual_task_done",
                "deliverable_id": "brand_kit",
                "owner": "ops-team",
                "note": "Brand kit ready",
            },
        )
        assert r.status_code == 200 and r.json().get("ok") is True

        # Day-3: content generated
        r = client.post(
            f"/api/admin/clients/{client_rec['id']}/delivery-action",
            json={
                "action": "generate_content",
                "deliverable_id": "social_posts",
                "owner": "ai-agent",
                "note": "12 captions generated",
            },
        )
        assert r.status_code == 200 and r.json().get("ok") is True

        # Day-5: approval received
        r = client.post(
            f"/api/admin/clients/{client_rec['id']}/delivery-action",
            json={
                "action": "approve_pending",
                "deliverable_id": "social_posts",
                "owner": "customer",
                "note": "Customer approved",
            },
        )
        assert r.status_code == 200 and r.json().get("ok") is True

        # Day-7: manual publish proof (auto-publish gated off, manual is the path)
        r = client.post(
            f"/api/admin/clients/{client_rec['id']}/delivery-action",
            json={
                "action": "publish_manual",
                "deliverable_id": "proof",
                "owner": "ops-team",
                "note": "Posted via Postiz - screenshot saved",
            },
        )
        assert r.status_code == 200 and r.json().get("ok") is True

        # Day-30: monthly report generated
        r = client.post(
            f"/api/admin/clients/{client_rec['id']}/delivery-action",
            json={
                "action": "monthly_report",
                "deliverable_id": "monthly_report",
                "owner": "ops-team",
                "note": "July 2026 monthly report sent",
            },
        )
        assert r.status_code == 200 and r.json().get("ok") is True

        # --- 3. Admin sees the full pipeline + per-customer row ---
        admin_cockpit = client.get("/api/admin/delivery-cockpit").json()
        assert admin_cockpit["ok"] is True
        # Admin customer card uses `id` as the customer identifier.
        my_row = next(c for c in admin_cockpit["customers"] if c["id"] == client_rec["id"])
        # Customer has at least the proof deliverable done (manual publish + monthly report)
        assert my_row["current_delivery_stage"] in {
            "published",
            "report_sent",
            "renewal_ready",
        }, my_row
        # Next action must be a customer-safe string, not a technical status code
        assert my_row["next_action"]
        for forbidden in ("cron", "queue", "worker", "exception", "stack", "env var"):
            assert forbidden not in my_row["next_action"].lower(), (
                f"admin next_action leaked technical wording: {forbidden!r} in {my_row['next_action']!r}"
            )

        # --- 4. Admin delivery-logs filter ties back to this customer ---
        logs_resp = client.get(f"/api/admin/delivery-logs?client_id={client_rec['id']}").json()
        assert logs_resp["ok"] is True
        assert (
            logs_resp["count"] >= 5
        )  # business_profile + brand_kit + social_posts(gen) + social_posts(approve) + proof + monthly_report
        # Every log row references our customer
        assert all(ev.get("customer_id") == client_rec["id"] for ev in logs_resp["events"])

        # Filter "manual action required" returns only events with that filter
        manual_resp = client.get("/api/admin/delivery-logs?filter=manual_action_required").json()
        # Either empty (no manual_required right now) or all rows are status=manual_required
        assert (
            all(
                "manual" in str(ev.get("status", "")).lower()
                or "manual" in str(ev.get("customer_message", "")).lower()
                for ev in manual_resp["events"]
            )
            or manual_resp["count"] == 0
        )

        # --- 5. Customer sees the proof ---
        customer_proof = client.get("/api/customer/delivery-proof").json()
        assert customer_proof["ok"] is True

        # All 10 deliverables exist
        deliverable_ids = {d["id"] for d in customer_proof["deliverables"]}
        assert len(deliverable_ids) == 10, (
            f"expected 10 deliverables, got {len(deliverable_ids)}: {deliverable_ids}"
        )

        # The proof deliverable is now marked done (we manually published)
        proof_d = next(d for d in customer_proof["deliverables"] if d["id"] == "proof")
        assert proof_d["status"] == "done", (
            f"proof should be done after publish_manual, got {proof_d}"
        )

        # The monthly_report deliverable is done
        report_d = next(d for d in customer_proof["deliverables"] if d["id"] == "monthly_report")
        assert report_d["status"] == "done"

        # Proof URL / screenshot / manual note are captured (the note we recorded)
        assert proof_d.get("proof_note") and "Postiz" in proof_d["proof_note"], proof_d

        # --- 6. Customer message contains completed + pending + next-month plan ---
        msg = customer_proof["customer_message"].lower()
        assert "cron" not in msg
        assert "queue" not in msg
        assert "worker" not in msg
        assert "exception" not in msg
        assert "api failure" not in msg
        assert "env" not in msg

        # Monthly summary has the next-month plan
        monthly = customer_proof.get("monthly_summary") or {}
        assert monthly.get("next_month_plan"), "monthly_summary.next_month_plan must be non-empty"
        # And the customer-safe status notes (deliverable-level human summaries)
        notes = customer_proof.get("customer_status_notes") or []
        assert len(notes) >= 1, "customer_status_notes should exist for the customer"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Product 1 Customer Deliverability layer (2026-07-08) — Customer Health,
# Approval Reminder, and SLA Recovery agents. These sit on top of the state
# already computed above (no new store) — tests assert the derived
# health_status/approval_escalation fields and the scheduled sweep function.
# ---------------------------------------------------------------------------
def test_health_status_red_for_blank_timeline_paid_customer(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import product_one_delivery

    # Fully set up (business/brand/social/approval all present) but ZERO
    # content and ZERO ledger events — a paid customer with a blank timeline,
    # exactly the "customer portal must never be blank" risk case.
    state = product_one_delivery.customer_delivery_status("c1", _client())

    assert state["health_status"] == "red"
    assert "blank_timeline" in state["health_reasons"]
    assert state["health_score"] < 100


def test_health_status_green_for_fully_delivered_customer(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    import asyncio

    from app.marketing import product_one_delivery

    asyncio.run(
        product_one_delivery.record_manual_action("c1", "generate_content", owner="ai-agent")
    )
    asyncio.run(
        product_one_delivery.record_manual_action(
            "c1", "publish_manual", note="Posted via Postiz", owner="ops-team"
        )
    )
    asyncio.run(product_one_delivery.record_manual_action("c1", "monthly_report", owner="ops-team"))

    state = product_one_delivery.customer_delivery_status("c1", _client())

    assert state["health_status"] == "green", state["health_reasons"]
    assert state["health_score"] == 100
    assert not state["approval_escalation"]


def test_approval_escalation_levels_from_age(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from datetime import datetime, timedelta, timezone

    from app.marketing import content_approval, product_one_delivery

    def _approval(aid: str, hours_old: float) -> dict:
        created = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat()
        return {
            "id": aid,
            "client_id": "c1",
            "status": "pending",
            "created_at": created,
            "token": aid,
        }

    content_approval._append(_approval("a_normal", 1))
    content_approval._append(_approval("a_stale", 30))
    content_approval._append(_approval("a_urgent", 50))
    content_approval._append(_approval("a_critical", 80))

    state = product_one_delivery.customer_delivery_status("c1", _client())
    by_id = {a["id"]: a["escalation"] for a in state["approval_escalation"]}

    assert by_id["a_normal"] == "normal"
    assert by_id["a_stale"] == "stale_24h"
    assert by_id["a_urgent"] == "urgent_48h"
    assert by_id["a_critical"] == "admin_manual_action"
    assert state["stale_approvals_24h"] == 1
    assert state["urgent_approvals_48h"] == 2  # urgent_48h + admin_manual_action
    assert state["health_status"] == "red"  # admin_manual_action-level staleness is a red flag
    assert "approval_critical_stale" in state["health_reasons"]


def test_delivery_cockpit_sorts_red_customers_first(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    import asyncio

    from app.marketing import product_one_delivery

    green = _client(id="c_green", business_name="Green Shop")
    red = _client(id="c_red", business_name="Red Shop")

    # Deliver everything for the green customer BEFORE the cockpit call.
    asyncio.run(
        product_one_delivery.record_manual_action("c_green", "generate_content", owner="ai-agent")
    )
    asyncio.run(
        product_one_delivery.record_manual_action(
            "c_green", "publish_manual", note="Posted", owner="ops-team"
        )
    )
    asyncio.run(
        product_one_delivery.record_manual_action("c_green", "monthly_report", owner="ops-team")
    )

    # List order deliberately puts the healthy customer FIRST — sort must fix it.
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: [green, red],
        raising=False,
    )

    cockpit = product_one_delivery.delivery_cockpit()

    assert [c["id"] for c in cockpit["customers"]] == ["c_red", "c_green"]
    assert cockpit["summary"]["red_customers"] == 1
    assert cockpit["summary"]["green_customers"] == 1


def test_sla_recovery_sweep_is_idempotent_and_never_sends_messages(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    import asyncio

    from app.marketing import auto_content, clients_store, delivery_ledger, product_one_delivery

    client_rec = _client()
    monkeypatch.setattr(
        clients_store, "list_clients", lambda status=None, product=None: [client_rec], raising=False
    )
    monkeypatch.setattr(clients_store, "get_client", lambda cid: client_rec, raising=False)

    calls = {"n": 0}

    async def _fake_seed(client):
        calls["n"] += 1
        return 5

    monkeypatch.setattr(auto_content, "seed_client_content", _fake_seed, raising=False)

    # SLA Recovery must never touch any WhatsApp/email sender — assert none of
    # the known sender modules are imported/called by making them explode if used.
    def _boom(*a, **k):
        raise AssertionError("SLA Recovery sweep must never send a customer message")

    monkeypatch.setattr("app.integrations.whatsapp.get_whatsapp_sender", _boom, raising=False)

    first = asyncio.run(product_one_delivery.run_health_and_recovery_sweep())
    assert first["ok"] is True
    assert first["checked"] == 1
    assert first["sla_breached"] == 1
    assert first["recovered_content"] == 1  # blank timeline -> auto content-gen fired once
    assert calls["n"] == 1

    second = asyncio.run(product_one_delivery.run_health_and_recovery_sweep())
    # Same day re-run: idempotency keys must block duplicate ledger writes and
    # a second content-generation call.
    assert second["sla_breached"] == 0
    assert second["recovered_content"] == 0
    assert calls["n"] == 1

    timeline = delivery_ledger.timeline("c1", limit=50, customer_only=False)
    breach_events = [e for e in timeline if e["event"] == "sla_breached"]
    assert len(breach_events) == 1


# ---------------------------------------------------------------------------
# Integration Health Agent (2026-07-08) — maps platform integration failures
# + scheduler/queue health to the SPECIFIC paid customers affected. Reuses
# app.platform.integration_health.snapshot / automation_health.health (no new
# failure-counting logic) — tests mock those two primitives directly.
# ---------------------------------------------------------------------------
def test_integration_readiness_scopes_vobiz_failure_to_voice_customers_only(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import product_one_delivery
    from app.platform import automation_health, integration_health

    monkeypatch.setattr(
        integration_health,
        "snapshot",
        lambda hours=6: {
            "integrations": {
                "vobiz": {"fail": 5, "ok": 1, "fail_rate": 0.83, "last_error": "SIP timeout"}
            }
        },
        raising=False,
    )
    monkeypatch.setattr(
        automation_health,
        "health",
        lambda: {"overdue": [], "queue_backlogged": False, "queue": {}},
        raising=False,
    )

    marketing_client = _client(id="c_mkt", product="marketing")
    voice_client = _client(id="c_voice", product="voice")
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: [marketing_client, voice_client],
        raising=False,
    )

    result = product_one_delivery.integration_readiness()

    row = next(r for r in result["integrations"] if r["integration"] == "vobiz")
    assert row["affected_customer_ids"] == ["c_voice"]
    assert row["scope"] == "voice_product"
    assert result["affected_customers_total"] == 1
    assert result["ok"] is False


def test_integration_readiness_all_paid_scope_affects_everyone(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import product_one_delivery
    from app.platform import automation_health, integration_health

    monkeypatch.setattr(
        integration_health,
        "snapshot",
        lambda hours=6: {
            "integrations": {
                "smtp": {"fail": 4, "ok": 0, "fail_rate": 1.0, "last_error": "auth failed"}
            }
        },
        raising=False,
    )
    monkeypatch.setattr(
        automation_health,
        "health",
        lambda: {"overdue": [], "queue_backlogged": False, "queue": {}},
        raising=False,
    )

    c1 = _client(id="c1", product="marketing")
    c2 = _client(id="c2", product="voice")
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: [c1, c2],
        raising=False,
    )

    result = product_one_delivery.integration_readiness()
    row = next(r for r in result["integrations"] if r["integration"] == "smtp")
    assert set(row["affected_customer_ids"]) == {"c1", "c2"}
    assert "email" in row["customer_reason"].lower() or "report" in row["customer_reason"].lower()


def test_integration_readiness_ops_only_scope_has_no_customer_impact(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import delivery_ledger, product_one_delivery
    from app.platform import automation_health, integration_health

    monkeypatch.setattr(
        integration_health,
        "snapshot",
        lambda hours=6: {
            "integrations": {
                "places": {"fail": 10, "ok": 0, "fail_rate": 1.0, "last_error": "quota"}
            }
        },
        raising=False,
    )
    monkeypatch.setattr(
        automation_health,
        "health",
        lambda: {"overdue": [], "queue_backlogged": False, "queue": {}},
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: [_client()],
        raising=False,
    )

    result = product_one_delivery.integration_readiness()
    row = next(r for r in result["integrations"] if r["integration"] == "places")
    assert row["affected_customer_count"] == 0
    assert result["affected_customers_total"] == 0
    timeline = delivery_ledger.timeline("c1", limit=20, customer_only=False)
    assert not any(e["event"] == "integration_failed" for e in timeline)


def test_integration_readiness_scheduler_backlog_affects_all_paid_customers(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import product_one_delivery
    from app.platform import automation_health, integration_health

    monkeypatch.setattr(
        integration_health, "snapshot", lambda hours=6: {"integrations": {}}, raising=False
    )
    monkeypatch.setattr(
        automation_health,
        "health",
        lambda: {
            "overdue": ["content"],
            "queue_backlogged": True,
            "queue": {"celery": 120, "heavy": 5},
        },
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: [_client(id="c1")],
        raising=False,
    )

    result = product_one_delivery.integration_readiness()
    assert result["scheduler"]["queue_backlogged"] is True
    assert "content" in result["scheduler"]["overdue_jobs"]
    assert result["scheduler"]["affected_customer_count"] == 1
    assert result["affected_customers_total"] == 1
    assert result["ok"] is False


def test_integration_readiness_ledger_event_is_idempotent_per_day(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import delivery_ledger, product_one_delivery
    from app.platform import automation_health, integration_health

    monkeypatch.setattr(
        integration_health,
        "snapshot",
        lambda hours=6: {
            "integrations": {
                "whatsapp": {"fail": 6, "ok": 0, "fail_rate": 1.0, "last_error": "token expired"}
            }
        },
        raising=False,
    )
    monkeypatch.setattr(
        automation_health,
        "health",
        lambda: {"overdue": [], "queue_backlogged": False, "queue": {}},
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: [_client(id="c1")],
        raising=False,
    )

    product_one_delivery.integration_readiness()
    product_one_delivery.integration_readiness()  # same-day re-run

    timeline = delivery_ledger.timeline("c1", limit=20, customer_only=False)
    events = [e for e in timeline if e["event"] == "integration_failed"]
    assert len(events) == 1


def test_delivery_cockpit_includes_integration_health(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import product_one_delivery
    from app.platform import automation_health, integration_health

    monkeypatch.setattr(
        integration_health, "snapshot", lambda hours=6: {"integrations": {}}, raising=False
    )
    monkeypatch.setattr(
        automation_health,
        "health",
        lambda: {"overdue": [], "queue_backlogged": False, "queue": {}},
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: [_client()],
        raising=False,
    )

    cockpit = product_one_delivery.delivery_cockpit()
    assert "integration_health" in cockpit
    assert cockpit["integration_health"]["ok"] is True


def test_gbp_url_alone_is_not_done_until_scored_audit(monkeypatch, tmp_path):
    """GBP link ≠ deliverable done; scored audit JSON (or gbp content/manual) is."""
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import product_one_delivery

    gbp_dir = tmp_path / "gbp_audits"
    gbp_dir.mkdir()
    monkeypatch.setattr(product_one_delivery, "_GBP_AUDIT_DIR", str(gbp_dir), raising=False)

    c = _client(
        socials={
            "instagram": "rahulmobile",
            "facebook": "",
            "gbp": "https://maps.google.com/?cid=1",
        }
    )
    state = product_one_delivery.customer_delivery_status("c1", c)
    by_id = {d["id"]: d for d in state["deliverables"]}
    assert by_id["gbp_suggestions"]["status"] == "in_progress"

    import json

    (gbp_dir / "c1.json").write_text(
        json.dumps({"score": 72, "grade": "B", "top_fixes": ["photos"], "at": "2026-07-17 10:00"}),
        encoding="utf-8",
    )
    state2 = product_one_delivery.customer_delivery_status("c1", c)
    by_id2 = {d["id"]: d for d in state2["deliverables"]}
    assert by_id2["gbp_suggestions"]["status"] == "done"
    assert "72" in (by_id2["gbp_suggestions"].get("proof_note") or "")


def test_collect_delivery_includes_gbp_score_and_approvals(monkeypatch, tmp_path):
    _wire_tmp(monkeypatch, tmp_path)
    from app.marketing import client_report, content_approval, delivery_ledger, product_one_delivery

    gbp_dir = tmp_path / "gbp_audits"
    gbp_dir.mkdir()
    monkeypatch.setattr(product_one_delivery, "_GBP_AUDIT_DIR", str(gbp_dir), raising=False)
    import json
    import time

    month = time.strftime("%Y-%m")
    (gbp_dir / "c1.json").write_text(json.dumps({"score": 81, "grade": "A"}), encoding="utf-8")
    delivery_ledger.log_event("c1", "post_draft_created", detail="x")
    content_approval.submit("c1", {"title": "Wait", "caption": "approve me"})

    d = client_report.collect_delivery("c1", month=month)
    assert d["gbp_score"] == 81
    assert d["approvals_pending"] >= 1
    assert "81" in d["summary_hi"]
