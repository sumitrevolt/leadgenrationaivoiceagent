"""Tests: multi-step wizard — services + offer + editable voice opening.

Covers:
  - get_script_preview(): niche opening, suggested opening from services/offer,
    discovery/closing/objection types; general fallback for unknown types.
  - apply_auto_setup(): services/offer/opening_line persist (flag-gated), applied
    list includes services_offer_opening.
  - TelecallerBrain.opening_line(): client record wizard_setup.opening_line override
    (step 0) vs normal chain fallback.
"""

from __future__ import annotations

from app.marketing import onboard_wizard as wz

# --------------------------------------------------------------------------- #
# Script preview
# --------------------------------------------------------------------------- #


def test_script_preview_salon_has_opening_and_suggested():
    p = wz.get_script_preview("salon")
    assert p["ok"] is True
    assert p["niche"] == "salon_spa"
    assert p["has_script"] is True  # salon_spa apni script — general fallback nahi
    assert p["opening"] and "salon" in p["opening"].lower()
    assert len(p["discovery"]) >= 3
    assert p["closing"]
    assert p["suggested_opening"]


def test_script_preview_tiffin_has_own_script():
    p = wz.get_script_preview("tiffin")
    assert p["ok"] is True
    assert p["niche"] == "tiffin_service"
    assert p["has_script"] is True
    assert p["opening"] and "tiffin" in p["opening"].lower()
    assert len(p["discovery"]) >= 3
    assert p["closing"]
    assert "mehenga" in p["objection_types"]


def test_script_preview_suggested_uses_services_offer():
    p = wz.get_script_preview(
        "salon-men",
        business_name="Urban Cuts",
        services="Haircut, Beard styling",
        offer="Weekday 20% off",
    )
    assert p["suggested_opening"]
    assert "Urban Cuts" in p["suggested_opening"]
    assert "Haircut" in p["suggested_opening"]
    assert "Weekday 20% off" in p["suggested_opening"]


def test_script_preview_unknown_type_general():
    p = wz.get_script_preview("nope_xyz")
    assert p["niche"] == "general"
    assert p["has_script"] is True  # general script hamesha hota hai
    assert p["suggested_opening"]


# --------------------------------------------------------------------------- #
# Extended apply — services / offer / opening persist
# --------------------------------------------------------------------------- #


def test_apply_persists_services_offer_opening(monkeypatch):
    monkeypatch.setenv("ONBOARD_WIZARD_APPLY", "1")
    stored: dict = {}

    class _FakeStore:
        @staticmethod
        def get_client(cid):
            return stored.get(cid)

        @staticmethod
        def update_client(cid, **fields):
            rec = stored.setdefault(cid, {})
            rec.update(fields)
            return rec

    import app.marketing.onboard_wizard as wzm

    monkeypatch.setattr(
        wzm, "_persist_setup_fields", lambda cid, **kw: stored.setdefault(cid, {}).update(kw)
    )

    res = wz.apply_auto_setup(
        "client_w1",
        "tiffin",
        business_name="Annapurna Tiffin",
        services="Veg thali, Jain thali, Office bulk",
        offer="Monthly subscription — 10% off",
        opening_line="Namaste! Main Swara bol rahi hoon Annapurna Tiffin se — office lunch ka naya plan hai, 2 minute?",
    )
    assert res["niche"] == "tiffin_service"
    assert "services_offer_opening" in res["applied"]
    # _persist_setup_fields ko saare values mile
    assert stored.get("client_w1", {}).get("services") == "Veg thali, Jain thali, Office bulk"
    assert stored.get("client_w1", {}).get("offer") == "Monthly subscription — 10% off"
    assert stored.get("client_w1", {}).get("opening_line", "").startswith("Namaste")


def test_real_persist_setup_fields_writes_client_record(monkeypatch):
    """Regression (2026-08-17 E2E catch): asli _persist_setup_fields ab clients_store
    ko **kwargs se call karta hai — positional dict se TypeError silent-swallow hota
    tha aur services/offer/opening kabhi persist nahi hoti thi."""
    monkeypatch.setenv("ONBOARD_WIZARD_APPLY", "1")
    stored: dict[str, dict] = {"client_w5": {"id": "client_w5"}}

    def _fake_get(cid):
        return stored.get(cid)

    def _fake_update(cid, **fields):
        rec = stored.setdefault(cid, {})
        rec.update(fields)
        return rec

    monkeypatch.setattr("app.marketing.clients_store.get_client", _fake_get)
    monkeypatch.setattr("app.marketing.clients_store.update_client", _fake_update)

    wz._persist_setup_fields(
        "client_w5",
        business_name="Annapurna Tiffin",
        services="Veg thali, Jain thali, Office bulk",
        offer="Monthly subscription - 10% off",
        opening_line="Namaste! Main Swara bol rahi hoon Annapurna Tiffin se - 2 minute?",
        business_type="tiffin",
        niche="tiffin_service",
    )
    rec = stored["client_w5"]
    assert rec.get("services") == "Veg thali, Jain thali, Office bulk"
    assert rec.get("offer") == "Monthly subscription - 10% off"
    assert rec["wizard_setup"]["opening_line"].startswith("Namaste")
    assert rec["wizard_setup"]["niche"] == "tiffin_service"


def test_real_persist_client_knowledge_writes_record(monkeypatch):
    """Same regression for _persist_client_knowledge (positional-dict TypeError)."""
    stored: dict[str, dict] = {"client_w6": {"id": "client_w6"}}

    def _fake_get(cid):
        return stored.get(cid)

    def _fake_update(cid, **fields):
        stored[cid].update(fields)
        return stored[cid]

    monkeypatch.setattr("app.marketing.clients_store.get_client", _fake_get)
    monkeypatch.setattr("app.marketing.clients_store.update_client", _fake_update)

    wz._persist_client_knowledge("client_w6", {"source": "onboard_wizard", "facts": ["f1", "f2"]})
    assert stored["client_w6"]["wizard_setup"]["last_auto_setup"]["source"] == "onboard_wizard"


def test_clients_store_whitelist_accepts_wizard_fields(monkeypatch):
    """clients_store.update_client ab wizard_setup (dict) + offer (str) accept karta
    hai — pehle whitelist se silently skip ho jaate the."""
    from app.marketing import clients_store as cs

    rec = {"id": "client_w7"}
    stored: dict[str, dict] = {"client_w7": rec}
    monkeypatch.setattr(cs, "_read_all", lambda: list(stored.values()))

    # _rewrite rows wapas store kare (file mat chhuo)
    monkeypatch.setattr(cs, "_rewrite", lambda rows: stored.update({r["id"]: r for r in rows}))

    out = cs.update_client(
        "client_w7",
        wizard_setup={"opening_line": "Namaste! Custom."},
        offer="Weekday 20% off",
    )
    assert out and out.get("wizard_setup") == {"opening_line": "Namaste! Custom."}
    assert out.get("offer") == "Weekday 20% off"


def test_apply_without_fields_skips_fields_persist(monkeypatch):
    monkeypatch.setenv("ONBOARD_WIZARD_APPLY", "1")
    called: list[dict] = []

    import app.marketing.onboard_wizard as wzm

    def _fake_persist(cid, **kw):
        called.append(kw)

    monkeypatch.setattr(wzm, "_persist_setup_fields", _fake_persist)

    res = wz.apply_auto_setup("client_w2", "tiffin")
    assert called == []  # koi services/offer/opening nahi → persist call nahi
    assert "services_offer_opening" not in res["applied"]


def test_apply_disabled_still_blocks_fields(monkeypatch):
    monkeypatch.delenv("ONBOARD_WIZARD_APPLY", raising=False)
    res = wz.apply_auto_setup("client_w3", "tiffin", services="Veg thali", opening_line="Namaste")
    assert res["ok"] is False
    assert "disabled" in (res.get("error") or "")


# --------------------------------------------------------------------------- #
# Brain opening-line override
# --------------------------------------------------------------------------- #


def test_brain_uses_wizard_opening_override(monkeypatch):
    from app.voice_agent import telecaller_brain as tb

    class _FakeStore:
        @staticmethod
        def get_client(cid):
            return {
                "id": cid,
                "wizard_setup": {
                    "opening_line": "Namaste! Main Swara hoon Urban Cuts se — custom line.",
                },
            }

    monkeypatch.setattr("app.marketing.clients_store.get_client", _FakeStore.get_client)

    brain = tb.TelecallerBrain(
        niche="gents_salon", client_name="Urban Cuts", client_id="client_abc"
    )
    line = brain.opening_line()
    assert "custom line" in line
    assert line.startswith("Namaste")


def test_brain_no_wizard_override_falls_through(monkeypatch):
    from app.voice_agent import telecaller_brain as tb

    class _FakeStore:
        @staticmethod
        def get_client(cid):
            return {"id": cid}  # no wizard_setup

    monkeypatch.setattr("app.marketing.clients_store.get_client", _FakeStore.get_client)

    brain = tb.TelecallerBrain(
        niche="gents_salon", client_name="Urban Cuts", client_id="client_abc"
    )
    line = brain.opening_line()
    # normal niche script chain — gents_salon script ka opening
    assert line and "[Company]" not in line
    assert "Urban Cuts" in line  # [Company] placeholder filled
