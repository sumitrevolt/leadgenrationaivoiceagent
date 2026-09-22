#!/usr/bin/env python3
"""
Coordination Group Setup — VPS Remote Execution
=================================================
Run this on VPS when SSH is back:
  ssh root@72.61.245.204
  cd /opt/leadgen && docker exec leadgen_app python3 /tmp/setup_coordination_groups.py

This script:
1. Reads the existing setup_spec.yaml
2. Creates forum topics for each coordination group
3. Updates the spec with topic IDs
4. Verifies all 3 groups are wired

Pre-requisites:
- TELEGRAM_JARVIS_BOT_TOKEN set in .env
- Bot must be a member of each group
- Bot must have Manage Topics permission
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# VPS paths
SPEC_PATH = Path("/opt/leadgen/config/telegram/setup_spec.yaml")
STATE_PATH = Path("/opt/leadgen/data/telegram_coordination_state.json")

COORDINATION_KEYS = [
    "workers_coordination",
    "agents_coordination",
    "admin_command_center",
]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def get_token() -> str:
    """Read bot token from VPS .env."""
    env_path = Path("/opt/leadgen/.env")
    if not env_path.exists():
        log("ERROR: /opt/leadgen/.env not found")
        sys.exit(1)

    with open(env_path) as f:
        for line in f:
            if line.startswith("TELEGRAM_JARVIS_BOT_TOKEN="):
                return line.strip().split("=", 1)[1]

    log("ERROR: TELEGRAM_JARVIS_BOT_TOKEN not in .env")
    sys.exit(1)


def api_call(token: str, method: str, params: dict) -> dict:
    """Call Telegram Bot API."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(params).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"ok": False, "error_code": e.code, "description": body[:300]}


def load_spec() -> dict:
    import yaml
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8")) or {}


def save_spec(spec: dict) -> None:
    import yaml
    SPEC_PATH.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")


def create_topic(token: str, chat_id: str, name: str) -> int | None:
    res = api_call(token, "createForumTopic", {"chat_id": chat_id, "name": name})
    if res.get("ok"):
        return res.get("result", {}).get("message_thread_id")
    log(f"  createForumTopic failed: {res.get('description')}")
    return None


def verify_group(token: str, chat_id: str) -> bool:
    res = api_call(token, "getChat", {"chat_id": chat_id})
    return bool(res.get("ok"))


def main() -> int:
    log("=== Coordination Group Setup ===")
    token = get_token()

    spec = load_spec()
    results = {}

    for key in COORDINATION_KEYS:
        # Find group
        group = None
        for g in spec.get("cross_product", []):
            if g.get("key") == key:
                group = g
                break

        if not group:
            log(f"SKIP: {key} not found in spec")
            results[key] = {"status": "NOT_IN_SPEC"}
            continue

        chat_id = str(group.get("chat_id") or "").strip()
        if not chat_id:
            log(f"SKIP: {key} has no chat_id")
            results[key] = {"status": "NO_CHAT_ID"}
            continue

        # Verify group exists
        if not verify_group(token, chat_id):
            log(f"SKIP: {key} chat {chat_id} unreachable")
            results[key] = {"status": "UNREACHABLE"}
            continue

        # Create topics
        topics = group.get("forum_topics") or []
        topic_ids = dict(group.get("topic_ids") or {})

        for topic_name in topics:
            if topic_name in topic_ids:
                log(f"  {key}: '{topic_name}' already exists (id={topic_ids[topic_name]})")
                continue

            topic_id = create_topic(token, chat_id, topic_name)
            if topic_id:
                topic_ids[topic_name] = topic_id
                log(f"  {key}: created '{topic_name}' (id={topic_id})")
            else:
                log(f"  {key}: FAILED to create '{topic_name}'")

        group["topic_ids"] = topic_ids
        results[key] = {
            "status": "WIRED",
            "chat_id": chat_id,
            "topics": len(topic_ids),
        }

    # Save updated spec
    save_spec(spec)

    # Write state
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": results,
        "all_wired": all(r.get("status") == "WIRED" for r in results.values()),
    }, indent=2), encoding="utf-8")

    log(f"\n=== RESULTS ===")
    for key, result in results.items():
        log(f"  {key}: {result.get('status')}")

    if all(r.get("status") == "WIRED" for r in results.values()):
        log("\nALL COORDINATION GROUPS WIRED ✅")
        return 0
    else:
        log("\nSome groups not wired — check results above ⚠️")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
