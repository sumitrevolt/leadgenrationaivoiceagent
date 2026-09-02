"""Tests — Rowboat-inspired compounding memory (memory_vault, call_prep, live_notes).

Offline + isolated: koi network/DB nahi. Stores tmp_path pe monkeypatch,
free_ai.chat mocked. Style: tests/test_parity_conversion.py jaisa.
"""

import asyncio
import json


def _setup_vault(tmp_path, monkeypatch):
    from app.platform import memory_vault

    monkeypatch.setattr(memory_vault, "_MEM_DIR", str(tmp_path / "memory"))
    return memory_vault


# --------------------------------------------------------------------------- #
# memory_vault — events, profile facts, markdown round-trip
# --------------------------------------------------------------------------- #
def test_add_event_and_profile(tmp_path, monkeypatch):
    mv = _setup_vault(tmp_path, monkeypatch)

    assert mv.add_event(
        "prospects", "9876543210", "Inquiry via website: solar chahiye", title="Sharma Solar"
    )
    assert mv.upsert_profile_fact("prospects", "9876543210", "City: Pune")
    assert mv.upsert_profile_fact(
        "prospects", "9876543210", "city: pune"
    )  # dedupe (case-insensitive)

    md = mv.get_memory("prospects", "9876543210")
    assert md is not None
    assert "# Sharma Solar" in md
    assert "## Profile" in md and "## Timeline" in md and "## Summary" in md
    assert md.count("City: Pune") + md.count("city: pune") == 1
    assert "solar chahiye" in md

    # consecutive duplicate event guard
    mv.add_event("prospects", "9876543210", "Inquiry via website: solar chahiye")
    parsed = mv._parse(mv.get_memory("prospects", "9876543210"))
    assert len(parsed["timeline"]) == 1

    # invalid kind / missing file
    assert mv.get_memory("nope", "x") is None
    assert mv.get_memory("prospects", "0000000000") is None
    assert mv.add_event("nope", "x", "ev") is False


def test_compaction_trims_timeline(tmp_path, monkeypatch):
    mv = _setup_vault(tmp_path, monkeypatch)
    for i in range(85):
        assert mv.add_event("prospects", "9812345678", f"Call (dialer): no-answer attempt {i}")
    parsed = mv._parse(mv.get_memory("prospects", "9812345678"))
    assert len(parsed["timeline"]) <= mv._KEEP_AFTER_COMPACT + 5  # compact hua
    assert "compact" in parsed["summary"]  # digest summary me gaya


def test_edit_memory_and_list(tmp_path, monkeypatch):
    mv = _setup_vault(tmp_path, monkeypatch)
    r = mv.edit_memory("clients", "client-1", "# Mera Client\n\nnotes yahan")
    assert r["ok"] is True
    assert "Mera Client" in mv.get_memory("clients", "client-1")
    # 64KB cap
    big = "x" * (65 * 1024)
    assert mv.edit_memory("clients", "client-1", big)["ok"] is False
    # bad kind
    assert mv.edit_memory("hacker", "k", "x")["ok"] is False
    ents = mv.list_entities("clients")
    assert len(ents) == 1 and ents[0]["key"] == "client-1"
    assert mv.list_entities("badkind") == []


def test_context_snippet(tmp_path, monkeypatch):
    mv = _setup_vault(tmp_path, monkeypatch)
    mv.add_event("prospects", "9876543210", "Inquiry via website: gym membership", title="FitZone")
    mv.upsert_profile_fact("prospects", "9876543210", "Niche: gym")
    snip = mv.context_snippet(phone="+919876543210")
    assert "FitZone" in snip and "gym" in snip
    assert mv.context_snippet(phone="9999999999") == ""  # no memory = empty
    assert mv.context_snippet() == ""


# --------------------------------------------------------------------------- #
# memory_vault.sync_all — cursor tail over jsonl stores
# --------------------------------------------------------------------------- #
def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_sync_all_cursor(tmp_path, monkeypatch):
    mv = _setup_vault(tmp_path, monkeypatch)
    inq = tmp_path / "inquiries.jsonl"
    chats = tmp_path / "widget_chats.jsonl"
    dialer = tmp_path / "dialer_logs.jsonl"
    deals = tmp_path / "deals.jsonl"
    monkeypatch.setattr(mv, "_INQUIRIES", str(inq))
    monkeypatch.setattr(mv, "_CHATS", str(chats))
    monkeypatch.setattr(mv, "_DIALER", str(dialer))
    monkeypatch.setattr(mv, "_DEALS", str(deals))

    _write_jsonl(
        inq,
        [
            {
                "phone": "+919876543210",
                "name": "Ravi",
                "business_name": "Ravi Solar",
                "niche": "solar",
                "city": "Pune",
                "message": "subsidy wala lagwana hai",
                "source": "website",
                "client_id": None,
            },
            {
                "phone": "+919812345678",
                "name": "Sita",
                "business_name": "Sita Gym",
                "message": "pricing?",
                "source": "mini_site",
                "client_id": "cl-77",
                "source_slug": "sita-gym",
            },
        ],
    )
    _write_jsonl(
        chats,
        [
            {"ts": "t", "slug": "s", "session_id": "A", "role": "user", "text": "price kya hai?"},
            {
                "ts": "t",
                "slug": "s",
                "session_id": "A",
                "role": "user",
                "text": "mera number 9876543210",
            },
            {"ts": "t", "slug": "s", "session_id": "A", "role": "bot", "text": "₹999 se"},
            {
                "ts": "t",
                "slug": "s",
                "session_id": "B",
                "role": "user",
                "text": "no phone here",
            },  # skip
        ],
    )
    _write_jsonl(
        dialer,
        [
            {
                "phone": "9876543210",
                "disposition": "interested",
                "notes": "demo chahiye",
                "at": "2026-06-10T10:00:00",
            },
        ],
    )
    _write_jsonl(
        deals,
        [
            {
                "id": "d1",
                "business_name": "Ravi Solar",
                "phone": "9876543210",
                "stage": "interested",
                "niche": "solar",
                "city": "Pune",
            },
        ],
    )

    res = mv.sync_all()
    assert res["ok"] is True
    assert res["inquiries"] == 3  # 2 prospects + 1 client event
    assert res["widget_chats"] == 2  # session A ke 2 user turns
    assert res["dialer_logs"] == 1
    assert res["deals"] == 1

    md = mv.get_memory("prospects", "9876543210")
    assert "Inquiry via website" in md and "Web chat" in md
    assert "Call (dialer): interested" in md and "Deal 'Ravi Solar'" in md
    assert "Naam: Ravi" in md and "City: Pune" in md
    assert mv.get_memory("clients", "cl-77") is not None
    # session B (no phone) skip hua
    assert mv.get_memory("prospects", "1111111111") is None

    # second run — cursor se kuch naya nahi
    res2 = mv.sync_all()
    assert res2["inquiries"] == 0 and res2["widget_chats"] == 0
    assert res2["dialer_logs"] == 0 and res2["deals"] == 0

    # naya line append → sirf wahi process ho
    with open(dialer, "a", encoding="utf-8") as f:
        f.write(json.dumps({"phone": "9876543210", "disposition": "callback", "notes": ""}) + "\n")
    res3 = mv.sync_all()
    assert res3["dialer_logs"] == 1

    # missing/corrupt store = defensive skip
    monkeypatch.setattr(mv, "_INQUIRIES", str(tmp_path / "nahi-hai.jsonl"))
    assert mv.sync_all()["ok"] is True


def test_sync_gate_off(tmp_path, monkeypatch):
    mv = _setup_vault(tmp_path, monkeypatch)
    monkeypatch.delenv("MEMORY_VAULT", raising=False)
    r = asyncio.run(mv.sync_if_enabled())
    assert r["ok"] is False and "off" in r["skipped"]
    monkeypatch.setenv("MEMORY_VAULT", "1")
    monkeypatch.setattr(mv, "_INQUIRIES", str(tmp_path / "none.jsonl"))
    monkeypatch.setattr(mv, "_CHATS", str(tmp_path / "none2.jsonl"))
    monkeypatch.setattr(mv, "_DIALER", str(tmp_path / "none3.jsonl"))
    monkeypatch.setattr(mv, "_DEALS", str(tmp_path / "none4.jsonl"))
    assert asyncio.run(mv.sync_if_enabled())["ok"] is True


# --------------------------------------------------------------------------- #
# call_prep — brief with LLM mock + static fallback
# --------------------------------------------------------------------------- #
def test_prep_brief_llm_and_fallback(tmp_path, monkeypatch):
    mv = _setup_vault(tmp_path, monkeypatch)
    mv.add_event("prospects", "9876543210", "Inquiry via website: solar", title="Ravi Solar")

    from app.platform import prospector

    pfile = tmp_path / "prospects.jsonl"
    _write_jsonl(
        pfile,
        [
            {
                "id": "p1",
                "business_name": "Ravi Solar",
                "phone": "+919876543210",
                "niche": "solar",
                "city": "Pune",
                "status": "ready",
            }
        ],
    )
    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(pfile))

    import app.voice_agent.free_ai as free_ai

    async def fake_chat(sys, msgs, **kw):
        return (
            json.dumps(
                {
                    "kaun_hai": "Ravi Solar, Pune ka solar installer",
                    "history_summary": "Website se inquiry aayi thi",
                    "pain_points": ["leads miss hote"],
                    "talking_points": ["Subsidy angle", "Free audit", "Demo"],
                    "objections": [{"objection": "mehnga", "jawab": "10 leads free"}],
                    "next_action": "Demo book karo",
                    "best_time_hint": "Shaam 5 baje",
                }
            ),
            "mock",
        )

    monkeypatch.setattr(free_ai, "chat", fake_chat)

    from app.platform import call_prep

    r = asyncio.run(call_prep.prep_brief(phone="9876543210"))
    assert r["ok"] is True and r["memory_found"] is True
    assert r["brief"]["kaun_hai"].startswith("Ravi Solar")
    assert len(r["brief"]["talking_points"]) == 3
    assert r["brief"]["objections"][0]["jawab"] == "10 leads free"
    assert isinstance(r["score"], int)

    # LLM fail → static fallback, never-empty
    async def boom(*a, **kw):
        raise RuntimeError("429")

    monkeypatch.setattr(free_ai, "chat", boom)
    r2 = asyncio.run(call_prep.prep_brief(phone="9876543210"))
    assert r2["ok"] is True and r2["provider"] == "fallback"
    assert r2["brief"]["talking_points"] and r2["brief"]["objections"]

    # no identifiers
    assert asyncio.run(call_prep.prep_brief())["ok"] is False


# --------------------------------------------------------------------------- #
# live_notes — registry + refresh + daily dedupe + gate
# --------------------------------------------------------------------------- #
def test_live_notes_topics_and_refresh(tmp_path, monkeypatch):
    mv = _setup_vault(tmp_path, monkeypatch)
    from app.platform import live_notes

    monkeypatch.setattr(live_notes, "_TOPICS_FILE", str(tmp_path / "live_topics.jsonl"))

    r = live_notes.add_topic("Solar Pune", niche="solar", city="")
    assert r["ok"] is True and r["existing"] is False
    assert live_notes.add_topic("solar pune")["existing"] is True  # slug dedupe
    assert len(live_notes.list_topics()) == 1
    assert live_notes.add_topic("")["ok"] is False

    # mock trends + free_ai (no network)
    from app.marketing import trends

    async def fake_angles(niche, biz, n=3):
        return {
            "angles": ["Subsidy push karo", "Garmi me solar ROI"],
            "trending": ["IPL", "Budget"],
        }

    monkeypatch.setattr(trends, "trend_angles", fake_angles)

    import app.voice_agent.free_ai as free_ai

    async def fake_chat(sys, msgs, **kw):
        return ("Aaj solar subsidy trending hai — post daalo.", "mock")

    monkeypatch.setattr(free_ai, "chat", fake_chat)

    t = live_notes.list_topics()[0]
    res = asyncio.run(live_notes.refresh_topic(t))
    assert res["ok"] is True and res["slug"] == "solar-pune"

    md = mv.get_memory("topics", "solar-pune")
    assert md is not None
    assert "# Solar Pune" in md and "subsidy" in md.lower()
    assert "Angle: Subsidy push karo" in md

    # same-day dedupe: refresh_due skip kare
    out = asyncio.run(live_notes.refresh_due())
    assert out["ok"] is True and out["skipped"] == 1 and out["refreshed"] == []

    # remove
    assert live_notes.remove_topic(t["id"])["ok"] is True
    assert live_notes.list_topics() == []
    assert live_notes.remove_topic("nahi")["ok"] is False


def test_live_notes_gate_off(monkeypatch):
    from app.platform import live_notes

    monkeypatch.delenv("LIVE_NOTES", raising=False)
    r = asyncio.run(live_notes.refresh_if_enabled())
    assert r["ok"] is False and "off" in r["skipped"]


# --------------------------------------------------------------------------- #
# F4 glue — sales_assistant backward-compat (+ optional phone)
# --------------------------------------------------------------------------- #
def test_sales_assistant_phone_param(tmp_path, monkeypatch):
    mv = _setup_vault(tmp_path, monkeypatch)
    mv.add_event("prospects", "9876543210", "Inquiry via website: price poocha", title="Ravi Solar")

    import app.voice_agent.free_ai as free_ai

    captured = {}

    async def fake_chat(sys, msgs, **kw):
        captured["user"] = msgs[0]["content"]
        return ('{"intent":"price","reply":"₹999 me shuru, 10 leads free!"}', "mock")

    monkeypatch.setattr(free_ai, "chat", fake_chat)

    from app.marketing import sales_assistant

    # old signature (no phone) — backward compatible
    r = asyncio.run(sales_assistant.handle_message("kitna mehnga hai?", "Ravi Solar", "solar"))
    assert r["ok"] is True and r["intent"] == "price"
    assert "History" not in captured["user"]

    # with phone — memory context prompt me prepend
    r2 = asyncio.run(
        sales_assistant.handle_message(
            "kitna mehnga hai?", "Ravi Solar", "solar", phone="9876543210"
        )
    )
    assert r2["ok"] is True
    assert "History" in captured["user"] and "price poocha" in captured["user"]

    # LLM fail + memory fail bhi → template fallback ok
    async def boom(*a, **kw):
        raise RuntimeError("down")

    monkeypatch.setattr(free_ai, "chat", boom)
    r3 = asyncio.run(sales_assistant.handle_message("hello", phone="0000"))
    assert r3["ok"] is True and r3["reply"]
