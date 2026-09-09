#!/usr/bin/env python3
"""Check WAHA inbound messages for hot leads.

Run ON THE VPS:
    python scripts/check_waha_inbound.py

Checks:
1. Lead 197126499872961 (SAL-006 hot lead) — any reply since Sep 4?
2. Jiya Makeover +919876543210 — any inbound?
3. General: last 10 inbound messages
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

WAHA_BASE = os.getenv("WAHA_BASE_URL", "http://127.0.0.1:3111")
WAHA_SESSION = os.getenv("WAHA_SESSION", "default")

HOT_LEAD_PHONE = "197126499872961"
JIYA_PHONE = "919876543210"


def _get(path: str) -> dict | list | None:
    url = f"{WAHA_BASE}{path}"
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def check_session() -> dict | None:
    """Check WAHA session status."""
    return _get(f"/api/{WAHA_SESSION}/status")


def check_chat(chat_id: str, label: str) -> None:
    """Check messages in a specific chat."""
    print(f"\n=== {label} ({chat_id}) ===")
    data = _get(f"/api/{WAHA_SESSION}/chats/{chat_id}")
    if data:
        if isinstance(data, dict):
            msgs = data.get("messages", data.get("history", []))
            if msgs:
                for msg in msgs[-5:]:  # Last 5 messages
                    ts = msg.get("timestamp", "?")
                    sender = msg.get("from", "?")
                    body = msg.get("body", msg.get("text", ""))[:100]
                    print(f"  [{ts}] from={sender}: {body}")
            else:
                print("  No messages found")
        else:
            print(f"  Response: {str(data)[:200]}")
    else:
        print("  Chat not found or error")


def check_recent_inbound() -> None:
    """Check recent inbound messages."""
    print("\n=== Recent Inbound Messages ===")
    data = _get(f"/api/{WAHA_SESSION}/chats")
    if data and isinstance(data, list):
        for chat in data[:10]:
            chat_id = chat.get("id", "?")
            name = chat.get("name", "?")
            last_msg = chat.get("lastMessage", {})
            ts = last_msg.get("timestamp", "?")
            body = last_msg.get("body", "")[:80]
            print(f"  {chat_id} ({name}) [{ts}]: {body}")
    elif data and isinstance(data, dict):
        chats = data.get("chats", data.get("data", []))
        for chat in chats[:10]:
            chat_id = chat.get("id", "?")
            name = chat.get("name", "?")
            last_msg = chat.get("lastMessage", {})
            ts = last_msg.get("timestamp", "?")
            body = last_msg.get("body", "")[:80]
            print(f"  {chat_id} ({name}) [{ts}]: {body}")
    else:
        print("  Could not fetch chats")


def main() -> int:
    print(f"=== WAHA Inbound Check ===")
    print(f"WAHA: {WAHA_BASE} session={WAHA_SESSION}")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")

    # Check session
    status = check_session()
    if status:
        print(f"\nSession status: {json.dumps(status, indent=2)[:300]}")
    else:
        print("\n[WARN] Could not reach WAHA session")

    # Check hot lead
    check_chat(HOT_LEAD_PHONE, "SAL-006 Hot Lead")

    # Check Jiya
    check_chat(JIYA_PHONE, "Jiya Makeover")

    # Recent inbound
    check_recent_inbound()

    return 0


if __name__ == "__main__":
    sys.exit(main())
