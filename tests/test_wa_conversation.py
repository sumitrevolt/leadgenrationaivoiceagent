"""WhatsApp conversation-memory + context-aware reply (2026-07-07 fix).

Guards the bug: inbound WA reply ko context ke bina classify/draft kiya ja raha tha,
isliye AI "samajh nahi pa raha / phir se poochh raha" tha. Ab per-number thread persist
hota hai + classify/draft ko prior context milta hai. Auto-send default OFF (ban-safe),
WHATSAPP_AI_AUTOREPLY=1 pe hi actual send hota hai.
"""

import asyncio
import json

from app.platform import reply_agent as ra
from app.platform import wa_conversation as wc


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(wc, "_CONV_FILE", str(tmp_path / "wa_conversations.jsonl"))
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(tmp_path / "reply_drafts.jsonl"))
    monkeypatch.setattr(ra, "_notify", lambda *a, **k: None)
    # Money path isolation: ensure interested replies don't append pricing footer
    # by default (caught by CI when UPI_VPA is set in env/data-file).
    from app.platform import upi_config

    monkeypatch.setattr(upi_config, "get_vpa", lambda: "")


# --------------------------------------------------------------------------- #
# 1. Module roundtrip
# --------------------------------------------------------------------------- #
def test_record_and_history_roles_and_order(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    wc.record("919876543210", "namaste, price kya hai?", "in", "m1")
    wc.record("9876543210", "Namaste! ₹1999/mo se shuru.", "out")  # same number, no CC
    wc.record("+91 98765 43210", "theek hai, demo dedo", "in", "m2")

    msgs = wc.history_messages("919876543210")
    # 91-prefix / bare-10 / spaced+CC — sab last-10 pe normalise (ek hi thread)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"].startswith("namaste")
    assert msgs[1]["role"] == "assistant"
    # unrelated number = empty thread
    assert wc.history_messages("911111111111") == []


def test_as_context_text_transcript(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    wc.record("9876543210", "kitna cost hoga?", "in")
    wc.record("9876543210", "₹1999/mo", "out")
    txt = wc.context_for("9876543210")
    assert "Customer: kitna cost hoga?" in txt
    assert "Hum: ₹1999/mo" in txt


# --------------------------------------------------------------------------- #
# 2. whatsapp_reply feeds prior context to the classifier (continuity)
# --------------------------------------------------------------------------- #
def test_whatsapp_reply_second_message_gets_prior_context(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    calls = []

    async def fake_chat(system, messages, max_tokens=90, temperature=0.6, **kw):
        calls.append({"max_tokens": max_tokens, "messages": messages})
        # max_tokens==8 => classifier; warna draft
        return (
            ("interested", "fake") if max_tokens == 8 else ("Bilkul! Demo bhej raha hoon.", "fake")
        )

    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "chat", fake_chat)

    # 1st inbound — koi prior context nahi
    asyncio.run(ra.whatsapp_reply("919876543210", "aap kya karte ho?"))
    first_classify = next(c for c in calls if c["max_tokens"] == 8)
    assert "Pichli baat-cheet" not in first_classify["messages"][0]["content"]

    calls.clear()
    # 2nd inbound — ab pehle turn ka context milna chahiye
    asyncio.run(ra.whatsapp_reply("919876543210", "haan interested hoon"))
    second_classify = next(c for c in calls if c["max_tokens"] == 8)
    assert "Pichli baat-cheet" in second_classify["messages"][0]["content"]
    assert "aap kya karte ho?" in second_classify["messages"][0]["content"]
    # draft call ko prior turns conversation-messages ke roop me milne chahiye
    draft_call = next(c for c in calls if c["max_tokens"] != 8)
    assert any("aap kya karte ho?" in m.get("content", "") for m in draft_call["messages"])


# --------------------------------------------------------------------------- #
# 3. Default = auto-send OFF (ban-safe: draft banta hai, bheja nahi jaata)
# --------------------------------------------------------------------------- #
def test_auto_send_off_by_default(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.delenv("WHATSAPP_AI_AUTOREPLY", raising=False)
    sent = []

    async def fake_chat(system, messages, max_tokens=90, temperature=0.6, **kw):
        return ("interested", "fake") if max_tokens == 8 else ("draft reply", "fake")

    class _Sender:
        async def send_text_message(self, to, msg):
            sent.append((to, msg))
            return {"messages": [{"id": "x"}]}

    from app.voice_agent import free_ai
    from app.integrations import whatsapp as wa_int

    monkeypatch.setattr(free_ai, "chat", fake_chat)
    monkeypatch.setattr(wa_int, "get_whatsapp_sender", lambda: _Sender())

    rec = asyncio.run(ra.whatsapp_reply("919876543210", "interested hoon"))
    assert rec["draft"] == "draft reply"  # draft bana (1-click human send ke liye)
    assert rec["auto_sent"] is False  # par bheja nahi (default OFF)
    assert sent == []  # sender kabhi call nahi hua
    # outbound turn record nahi hua (kyunki actually gaya hi nahi)
    assert [m["role"] for m in wc.history_messages("919876543210")] == ["user"]


# --------------------------------------------------------------------------- #
# 4. WHATSAPP_AI_AUTOREPLY=1 => actual send + outbound recorded
# --------------------------------------------------------------------------- #
def test_auto_send_on_sends_and_records_outbound(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("WHATSAPP_AI_AUTOREPLY", "1")
    sent = []

    async def fake_chat(system, messages, max_tokens=90, temperature=0.6, **kw):
        return ("interested", "fake") if max_tokens == 8 else ("Demo bhej diya!", "fake")

    class _Sender:
        async def send_text_message(self, to, msg):
            sent.append((to, msg))
            return {"messages": [{"id": "x"}]}

    from app.voice_agent import free_ai
    from app.integrations import whatsapp as wa_int

    monkeypatch.setattr(free_ai, "chat", fake_chat)
    monkeypatch.setattr(wa_int, "get_whatsapp_sender", lambda: _Sender())

    rec = asyncio.run(ra.whatsapp_reply("919876543210", "interested hoon"))
    assert rec["auto_sent"] is True
    assert sent and sent[0][1] == "Demo bhej diya!"
    # inbound + outbound dono thread me
    roles = [m["role"] for m in wc.history_messages("919876543210")]
    assert roles == ["user", "assistant"]


def test_auto_send_never_for_unsubscribe(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("WHATSAPP_AI_AUTOREPLY", "1")
    sent = []

    async def fake_chat(system, messages, max_tokens=90, temperature=0.6, **kw):
        return ("unsubscribe", "fake") if max_tokens == 8 else ("should not send", "fake")

    class _Sender:
        async def send_text_message(self, to, msg):
            sent.append((to, msg))
            return {"messages": [{"id": "x"}]}

    from app.voice_agent import free_ai
    from app.integrations import whatsapp as wa_int

    monkeypatch.setattr(free_ai, "chat", fake_chat)
    monkeypatch.setattr(wa_int, "get_whatsapp_sender", lambda: _Sender())

    rec = asyncio.run(ra.whatsapp_reply("919876543210", "stop please band karo"))
    assert rec["auto_sent"] is False
    assert sent == []


if __name__ == "__main__":  # pragma: no cover
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
