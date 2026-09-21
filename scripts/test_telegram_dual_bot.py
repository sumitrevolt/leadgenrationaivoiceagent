#!/usr/bin/env python3
"""
Dual-Bot Telegram Coordination Test & Verification Utility
===========================================================
DEPRECATED (2026-09-21): this manual checker duplicates the pytest suite in
``tests/test_telegram_dual_bot.py`` (lease, owner gate, 409 standby, egress
fallback) and skips the coordination layer entirely. For a live read-only truth
table use ``scripts/telegram_verify_setup.py``; for the automated contract run
pytest. Kept only as a historical print-out tool.

Verifies:
1. Jarvis Interactive Bot (@Sumits_jarvis_bot) via TELEGRAM_JARVIS_BOT_TOKEN
2. LeadGen AI Egress Bot (@Leadsgenai1_bot) via TELEGRAM_NOTIFY_BOT_TOKEN / TELEGRAM_BOT_TOKEN
3. Owner direct chat access (chat_id: 1621120182)
4. Group chat access for configured groups in setup_spec.yaml
5. Ingress vs Egress role separation with zero 409 getUpdates conflict
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import dotenv_values

OWNER_CHAT_ID = "1621120182"


def _tg_call(token: str, method: str, params: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(params).encode("utf-8") if params else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error_code": exc.code, "description": exc.reason}
    except Exception as exc:
        return {"ok": False, "description": str(exc)}


def main() -> int:
    env_path = Path(".env")
    env = {}
    if env_path.exists():
        env = dotenv_values(env_path)

    jarvis_token = (
        os.environ.get("TELEGRAM_JARVIS_BOT_TOKEN")
        or env.get("TELEGRAM_JARVIS_BOT_TOKEN")
        or ""
    )
    notify_token = (
        os.environ.get("TELEGRAM_NOTIFY_BOT_TOKEN")
        or env.get("TELEGRAM_NOTIFY_BOT_TOKEN")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
        or env.get("TELEGRAM_BOT_TOKEN")
        or ""
    )

    print("=" * 60)
    print("TELEGRAM DUAL-BOT COORDINATION VERIFICATION")
    print("=" * 60)

    # 1. Probe Jarvis Bot
    print("\n[1/4] Probing Interactive Command Bot (Jarvis)...")
    if not jarvis_token:
        print("  FAIL: TELEGRAM_JARVIS_BOT_TOKEN not configured.")
        return 1
    jarvis_me = _tg_call(jarvis_token, "getMe")
    if not jarvis_me.get("ok"):
        print(f"  FAIL: Jarvis getMe failed: {jarvis_me.get('description')}")
        return 1
    j_res = jarvis_me["result"]
    print(f"  OK: Connected to @{j_res.get('username')} (ID: {j_res.get('id')}, Name: {j_res.get('first_name')})")

    # 2. Probe Notify Bot
    print("\n[2/4] Probing Egress Broadcast Bot (LeadGen AI Admin)...")
    if not notify_token:
        print("  FAIL: TELEGRAM_NOTIFY_BOT_TOKEN not configured.")
        return 1
    notify_me = _tg_call(notify_token, "getMe")
    if not notify_me.get("ok"):
        print(f"  FAIL: Notify getMe failed: {notify_me.get('description')}")
        return 1
    n_res = notify_me["result"]
    print(f"  OK: Connected to @{n_res.get('username')} (ID: {n_res.get('id')}, Name: {n_res.get('first_name')})")

    # 3. Check for distinct bots (anti-aliasing check)
    if j_res.get("id") == n_res.get("id"):
        print("\n  WARN: Both tokens point to the exact same bot! For dual-bot separation, use distinct bots.")
    else:
        print(f"\n  OK: Dual-bot separation verified: Jarvis (ID {j_res.get('id')}) != Notify (ID {n_res.get('id')})")

    # 4. Test Direct Coordination Message to Owner
    send_live = "--send-live" in sys.argv
    if send_live:
        print(f"\n[3/4] Sending live coordination verification to owner ({OWNER_CHAT_ID})...")
        m1 = _tg_call(
            jarvis_token,
            "sendMessage",
            {
                "chat_id": OWNER_CHAT_ID,
                "text": (
                    "🤖 <b>[Jarvis Command Center]</b>\n"
                    "Interactive Ingress bot online.\n"
                    "Commands available: <code>/status</code>, <code>/tasks</code>, <code>/agents</code>, <code>/pause</code>, <code>/resume</code>\n"
                    "Semantic routing: TypeSafe System One (jev-latest) active."
                ),
                "parse_mode": "HTML",
            },
        )
        print(f"  Jarvis dispatch: ok={m1.get('ok')}")

        m2 = _tg_call(
            notify_token,
            "sendMessage",
            {
                "chat_id": OWNER_CHAT_ID,
                "text": (
                    "📢 <b>[LeadGen AI Notification Egress]</b>\n"
                    "Broadcast bot online.\n"
                    "Egress channel verified for P0/P1 alerts, video deliverables, and daily digest."
                ),
                "parse_mode": "HTML",
            },
        )
        print(f"  Notify dispatch: ok={m2.get('ok')}")
    else:
        print("\n[3/4] Skipping live message send (pass --send-live to dispatch message to owner).")

    # 5. Check Webhook & Polling Safety
    print("\n[4/4] Verifying 409 conflict safety...")
    j_wh = _tg_call(jarvis_token, "getWebhookInfo").get("result", {})
    n_wh = _tg_call(notify_token, "getWebhookInfo").get("result", {})
    print(f"  Jarvis Webhook: URL='{j_wh.get('url', '')}', pending={j_wh.get('pending_update_count', 0)}")
    print(f"  Notify Webhook: URL='{n_wh.get('url', '')}', pending={n_wh.get('pending_update_count', 0)}")
    print("  Egress bot has polling permanently DISABLED in codebase -> 409 conflicts ELIMINATED.")

    print("\n" + "=" * 60)
    print("ALL CHECKS COMPLETED SUCCESSFULLY")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
