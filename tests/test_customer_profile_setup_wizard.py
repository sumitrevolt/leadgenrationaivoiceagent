"""GET/POST /api/customer/profile — Setup Wizard's read/write path (business
profile/social/WhatsApp/brand-tone, the mission's 4 wizard dimensions).

IDOR-safe (require_customer, same pattern as every other /api/customer/* route).
Real file I/O against tmp-path-redirected clients_store/brand_kit (not mocks) —
this is the only way to actually prove the privileged-field-ignored contract
(advisor's concern: don't just trust the Pydantic model, prove plan/status/
trial/niche never reach the client record even if present in the raw body)."""

import os

from fastapi.testclient import TestClient

from app.marketing import brand_kit, clients_store


def _override_customer(app, cid):
    from app.api.customer_auth import require_customer

    app.dependency_overrides[require_customer] = lambda: cid


def _redirect_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(
        clients_store, "_CLIENTS_FILE", lambda: os.path.join(str(tmp_path), "clients.jsonl")
    )
    monkeypatch.setattr(brand_kit, "_BRAND_DIR", os.path.join(str(tmp_path), "brand_kits"))


def test_get_profile_prefills_current_values(monkeypatch, tmp_path):
    from app.main import app

    _redirect_stores(monkeypatch, tmp_path)
    rec = clients_store.add_client(
        "Sharma Solar",
        "solar_residential",
        phone="9812345678",
        city="Pune",
        socials={"instagram": "@sharma_solar"},
    )
    _override_customer(app, rec["id"])

    with TestClient(app) as c:
        resp = c.get("/api/customer/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["business_name"] == "Sharma Solar"
    assert body["city"] == "Pune"
    assert body["phone"] == "9812345678"
    assert body["instagram"] == "@sharma_solar"
    app.dependency_overrides.clear()


def test_post_profile_saves_business_fields_and_socials(monkeypatch, tmp_path):
    from app.main import app

    _redirect_stores(monkeypatch, tmp_path)
    rec = clients_store.add_client("Old Name", "general", phone="9000000001")
    _override_customer(app, rec["id"])

    with TestClient(app) as c:
        resp = c.post(
            "/api/customer/profile",
            json={
                "business_name": "New Name Pvt Ltd",
                "city": "Mumbai",
                "phone": "9111111111",
                "instagram": "@newname",
                "facebook": "fb.com/newname",
                "gbp": "goo.gl/maps/xyz",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    saved = clients_store.get_client(rec["id"])
    assert saved["business_name"] == "New Name Pvt Ltd"
    assert saved["city"] == "Mumbai"
    assert saved["phone"] == "9111111111"
    assert saved["socials"]["instagram"] == "@newname"
    assert saved["socials"]["gbp"] == "goo.gl/maps/xyz"
    app.dependency_overrides.clear()


def test_post_profile_saves_brand_tagline_colors_logo(monkeypatch, tmp_path):
    from app.main import app

    _redirect_stores(monkeypatch, tmp_path)
    rec = clients_store.add_client("Brand Biz", "general", phone="9000000002")
    _override_customer(app, rec["id"])

    with TestClient(app) as c:
        resp = c.post(
            "/api/customer/profile",
            json={
                "tagline": "Roshni bhi, bachat bhi",
                "primary_color": "#6d28d9",
                "accent_color": "#f59e0b",
                "logo_text": "BB",
            },
        )
    assert resp.json()["ok"] is True

    saved = clients_store.get_client(rec["id"])
    assert saved["brand"]["tagline"] == "Roshni bhi, bachat bhi"
    assert saved["brand"]["primary"] == "#6d28d9"
    # update_client mirrors brand -> brand_kit automatically (pre-existing behavior)
    mirrored = brand_kit.get_brand(rec["id"])
    assert mirrored["tagline"] == "Roshni bhi, bachat bhi"
    assert mirrored["logo_text"] == "BB"
    app.dependency_overrides.clear()


def test_post_profile_tone_does_not_clobber_previously_saved_brand_fields(monkeypatch, tmp_path):
    """tone isn't part of update_client's brand->brand_kit mirror; the
    read-modify-write must preserve tagline/colors/logo_text set moments earlier."""
    from app.main import app

    _redirect_stores(monkeypatch, tmp_path)
    rec = clients_store.add_client("Tone Biz", "general", phone="9000000003")
    _override_customer(app, rec["id"])

    with TestClient(app) as c:
        c.post("/api/customer/profile", json={"tagline": "Original Tagline", "logo_text": "TB"})
        resp = c.post("/api/customer/profile", json={"tone": "Friendly aur casual"})

    assert resp.json()["ok"] is True
    mirrored = brand_kit.get_brand(rec["id"])
    assert mirrored["tone"] == "Friendly aur casual"
    assert mirrored["tagline"] == "Original Tagline"  # NOT clobbered
    assert mirrored["logo_text"] == "TB"  # NOT clobbered
    app.dependency_overrides.clear()


def test_post_profile_ignores_privileged_fields_even_if_present_in_raw_body(monkeypatch, tmp_path):
    """The mission-critical guard advisor flagged: plan/status/trial/niche must
    never be settable here, even if a crafted request includes them — proven
    against the REAL clients_store record, not just by trusting the Pydantic
    model's declared fields."""
    from app.main import app

    _redirect_stores(monkeypatch, tmp_path)
    rec = clients_store.add_client(
        "Privilege Test Biz", "general", phone="9000000004", plan="starter"
    )
    clients_store.update_client(rec["id"], status="active")
    _override_customer(app, rec["id"])

    with TestClient(app) as c:
        resp = c.post(
            "/api/customer/profile",
            json={
                "business_name": "Renamed Biz",
                "plan": "advanced",  # not a declared field -> FastAPI drops it
                "status": "dead",  # not a declared field -> FastAPI drops it
                "trial": False,  # not a declared field -> FastAPI drops it
                "niche": "gym_fitness",  # not a declared field -> FastAPI drops it
            },
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    saved = clients_store.get_client(rec["id"])
    assert saved["business_name"] == "Renamed Biz"  # the real, allowed field DID save
    assert saved["plan"] == "starter"  # unchanged — privileged field ignored
    assert saved["status"] == "active"  # unchanged
    assert saved["niche"] == "general"  # unchanged
    app.dependency_overrides.clear()


def test_post_profile_unknown_client_404(monkeypatch, tmp_path):
    from app.main import app

    _redirect_stores(monkeypatch, tmp_path)
    _override_customer(app, "does-not-exist")

    with TestClient(app) as c:
        resp = c.post("/api/customer/profile", json={"business_name": "X"})
    assert resp.status_code == 404
    app.dependency_overrides.clear()


def test_get_profile_requires_auth():
    from app.main import app

    app.dependency_overrides.clear()
    with TestClient(app) as c:
        resp = c.get("/api/customer/profile")
    assert resp.status_code in (401, 403)


def test_post_profile_empty_body_is_a_noop_not_an_error(monkeypatch, tmp_path):
    """Customer opening then closing the wizard without changing anything
    must not error or wipe existing data."""
    from app.main import app

    _redirect_stores(monkeypatch, tmp_path)
    rec = clients_store.add_client("Untouched Biz", "general", phone="9000000005")
    _override_customer(app, rec["id"])

    with TestClient(app) as c:
        resp = c.post("/api/customer/profile", json={})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    saved = clients_store.get_client(rec["id"])
    assert saved["business_name"] == "Untouched Biz"
    assert saved["phone"] == "9000000005"
    app.dependency_overrides.clear()
