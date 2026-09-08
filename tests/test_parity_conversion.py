"""Tests for the conversion-feature batch (chat widget, lead-in webhook, trial,
form-builder-lite).

Offline + isolated: koi network/DB nahi. File-stores tmp_path pe monkeypatch.
Style: tests/test_2026_features.py jaisa (pure-python unit tests).
"""

import json


# --------------------------------------------------------------------------- #
# conversion.extract_phone — in-chat lead capture
# --------------------------------------------------------------------------- #
def test_extract_phone_variants():
    from app.api.conversion import extract_phone

    assert extract_phone("mera number 9876543210 hai") == "+919876543210"
    assert extract_phone("call me at +91 9876543210") == "+919876543210"
    assert extract_phone("ph: 09876543210") == "+919876543210"
    assert extract_phone("price kya hai?") is None
    # landline-style (starts with 1-5) / short / long → None
    assert extract_phone("1234567890") is None
    assert extract_phone("98765") is None
    assert extract_phone("98765432101234") is None
    # defensive
    assert extract_phone(None) is None


# --------------------------------------------------------------------------- #
# conversion.map_lead_fields — flexible webhook payloads
# --------------------------------------------------------------------------- #
def test_map_lead_fields_aliases():
    from app.api.conversion import map_lead_fields

    m = map_lead_fields(
        {
            "Full_Name": "Ravi Kumar",
            "Mobile": "9876543210",
            "work_email": "ravi@x.com",
            "Location": "Pune",
            "Platform": "indiamart",
            "Notes": "solar chahiye",
        }
    )
    assert m["name"] == "Ravi Kumar"
    assert m["phone"] == "9876543210"
    assert m["email"] == "ravi@x.com"
    assert m["city"] == "Pune"
    assert m["source"] == "indiamart"
    assert "solar" in m["message"]


def test_map_lead_fields_fb_and_extras():
    from app.api.conversion import map_lead_fields

    fb = {
        "field_data": [
            {"name": "full_name", "values": ["Sita"]},
            {"name": "phone_number", "values": ["+919812345678"]},
            {"name": "budget", "values": ["2 lakh"]},
        ]
    }
    m = map_lead_fields(fb)
    assert m["name"] == "Sita"
    assert "9812345678" in m["phone"]
    assert "budget" in m["message"]  # unknown extra → message me append
    # defensive: non-dict input
    assert map_lead_fields(None) == {}
    assert map_lead_fields([1, 2]) == {}


# --------------------------------------------------------------------------- #
# conversion._log_chat — jsonl turn log
# --------------------------------------------------------------------------- #
def test_chat_log_append(tmp_path, monkeypatch):
    from app.api import conversion

    p = tmp_path / "chats.jsonl"
    monkeypatch.setattr(conversion, "_CHATS_FILE", str(p))
    conversion._log_chat("sharma-solar-7b6f", "sess1", "user", "price?")
    conversion._log_chat("sharma-solar-7b6f", "sess1", "bot", "₹999 se shuru", lead_captured=True)
    lines = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    assert lines[0]["role"] == "user" and lines[0]["slug"] == "sharma-solar-7b6f"
    assert lines[1]["lead_captured"] is True
    assert "ts" in lines[0] and "session_id" in lines[0]


# --------------------------------------------------------------------------- #
# embed_widget — form-builder-lite config + chat mode markup
# --------------------------------------------------------------------------- #
def test_form_config_save_get(tmp_path, monkeypatch):
    from app.marketing import embed_widget

    monkeypatch.setattr(embed_widget, "_FORMS_FILE", str(tmp_path / "forms.jsonl"))
    assert embed_widget.get_form_config("abc") is None  # no config yet
    res = embed_widget.save_form_config(
        "Abc",
        [
            {"name": "name", "label": "Naam *", "type": "text", "required": True},
            {"name": "phone", "label": "Phone *", "type": "tel", "required": True},
            {
                "name": "Service Type!",
                "label": "Service",
                "type": "select",
                "options": ["AC", "Fridge"],
            },
            {"name": "bad type", "type": "weird"},  # name sanitized, type→text
        ],
    )
    assert res["ok"] is True
    cfg = embed_widget.get_form_config("ABC")  # case-insensitive
    assert cfg is not None and len(cfg) == 4
    sel = [f for f in cfg if f["type"] == "select"][0]
    assert sel["options"] == ["AC", "Fridge"]
    # select bina options → text fallback
    res2 = embed_widget.save_form_config("xyz", [{"name": "pick", "type": "select"}])
    assert res2["fields"][0]["type"] == "text"
    # invalid inputs
    assert embed_widget.save_form_config("", [{"name": "a"}])["ok"] is False
    assert embed_widget.save_form_config("s", [])["ok"] is False


def test_effective_fields_always_has_name_phone(tmp_path, monkeypatch):
    from app.marketing import embed_widget

    monkeypatch.setattr(embed_widget, "_FORMS_FILE", str(tmp_path / "forms.jsonl"))
    embed_widget.save_form_config("noco", [{"name": "budget", "label": "Budget", "type": "text"}])
    eff = embed_widget._effective_fields("noco")
    names = [f["name"] for f in eff]
    assert "name" in names and "phone" in names and "budget" in names
    # default (no config) = current 3 fields
    deff = embed_widget._effective_fields("unknown-slug")
    assert [f["name"] for f in deff] == ["name", "phone", "message"]


def test_embed_page_html_form_and_chat(tmp_path, monkeypatch):
    from app.marketing import embed_widget

    monkeypatch.setattr(embed_widget, "_FORMS_FILE", str(tmp_path / "forms.jsonl"))
    client = {"business_name": "Sharma Solar", "slug": "sharma-solar-7b6f"}
    page = embed_widget.embed_page_html(client)
    # form (default) — inquiry POST + honeypot intact
    assert "/api/public/inquiry" in page
    assert 'data-lgf="name"' in page and 'data-lgf="phone"' in page
    assert "lgHP" in page
    # chat UI ships in same page, gated by ?mode=chat client-side
    assert "/api/public/widget-chat" in page
    assert "mode=chat" in page and "lgaiChat" in page
    # custom field renders
    embed_widget.save_form_config(
        "sharma-solar-7b6f", [{"name": "budget", "label": "Aapka Budget", "type": "text"}]
    )
    page2 = embed_widget.embed_page_html(client)
    assert "Aapka Budget" in page2 and 'data-lgf="budget"' in page2


def test_widget_js_and_snippet_modes():
    from app.marketing import embed_widget

    js = embed_widget.widget_js("sharma-solar-7b6f")
    assert "mode=chat" in js and "document.currentScript" in js
    assert "/b/sharma-solar-7b6f/embed" in js
    assert embed_widget.snippet("s1").endswith("</script>")
    assert "?mode=chat" in embed_widget.snippet("s1", mode="chat")
    assert "?mode=chat" not in embed_widget.snippet("s1")  # default unchanged


# --------------------------------------------------------------------------- #
# packages — trial additive + status helper
# --------------------------------------------------------------------------- #
def test_packages_backward_compatible():
    from app.marketing.packages import get_packages

    plain = get_packages()
    assert [p["key"] for p in plain] == ["starter", "growth", "advanced"]  # unchanged
    with_trial = get_packages(include_trial=True)
    assert with_trial[0]["key"] == "trial"
    assert with_trial[0]["price_inr_month"] == 0
    assert len(with_trial) == 4


def test_trial_status_active_expired():
    from datetime import datetime, timedelta, timezone

    from app.marketing.packages import trial_expiry_iso, trial_status

    # not a trial client
    assert trial_status({"plan": "starter"})["trial"] is False
    assert trial_status(None)["active"] is False
    # active
    st = trial_status({"trial": True, "trial_expires": trial_expiry_iso(7)})
    assert st["trial"] is True and st["active"] is True and st["expired"] is False
    assert 1 <= st["days_left"] <= 7
    # expired
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    st2 = trial_status({"trial": True, "trial_expires": past})
    assert st2["expired"] is True and st2["active"] is False
    # garbage expiry — no raise
    st3 = trial_status({"trial": True, "trial_expires": "not-a-date"})
    assert st3["trial"] is True and st3["active"] is False


def test_clients_store_trial_fields(tmp_path, monkeypatch):
    from app.marketing import clients_store

    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", lambda: str(tmp_path / "clients.jsonl"))
    monkeypatch.setattr(clients_store, "brand_kit", None)  # no real data/ side-effect
    rec = clients_store.add_client("Trial Biz", "solar", phone="9876500001")
    cid = rec["id"]
    upd = clients_store.update_client(cid, trial=True, trial_expires="2026-06-17T00:00:00+00:00")
    assert upd is not None
    fetched = clients_store.get_client(cid)
    assert fetched["trial"] is True
    assert fetched["trial_expires"].startswith("2026-06-17")
