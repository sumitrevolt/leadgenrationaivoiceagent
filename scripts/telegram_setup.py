#!/usr/bin/env python3
"""LeadGen AI — Telegram setup bootstrap (Bot-API, fail-closed).

WHAT THIS DOES
--------------
Reads ``config/telegram/setup_spec.yaml`` and, for every chat whose ``chat_id``
is filled in, *configures* it: sets description, creates forum topics, posts +
pins the intro message, and exports an invite link for private chats.

WHAT IT CANNOT DO
----------------
Telegram Bot API **cannot create channels or groups** (only a user account /
Telethon session can). So the owner first creates the chats manually (or via
the Telethon snippet in docs/TELEGRAM_ENTERPRISE_SETUP.md), pastes each
``chat_id`` into the spec, then runs this script. This keeps the sandbox honest:
no fake "created" claims.

FAIL-CLOSED
-----------
* Disabled unless ``TELEGRAM_SETUP_ENABLED=1``.
* Refuses to touch the network without ``TELEGRAM_BOT_TOKEN``.
* --plan prints intended actions with ZERO network calls (safe default).
* Any API error is reported, never swallowed as success.

Run:
    python scripts/telegram_setup.py --validate     # parse spec only
    python scripts/telegram_setup.py --plan         # dry run, no network
    TELEGRAM_SETUP_ENABLED=1 TELEGRAM_BOT_TOKEN=xxxx \
        python scripts/telegram_setup.py --apply    # live configure
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

try:
    import yaml
except Exception as exc:  # pragma: no cover
    print(f"[telegram_setup] PyYAML missing: {exc}", file=sys.stderr)
    sys.exit(2)

# Windows console (cp1252) cannot encode the emoji used in forum-topic names,
# which crashed --plan/--apply with UnicodeEncodeError. Force UTF-8 on the
# standard streams so the bootstrap works from any shell (cmd/PowerShell).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover - non-reconfigurable stream
        pass

SPEC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "telegram", "setup_spec.yaml",
)
API_BASE = "https://api.telegram.org/bot{token}/{method}"


# --------------------------------------------------------------------------- #
# Gating
# --------------------------------------------------------------------------- #
def setup_enabled() -> bool:
    return os.environ.get("TELEGRAM_SETUP_ENABLED", "0") == "1"


def get_token() -> str | None:
    return os.environ.get("TELEGRAM_BOT_TOKEN") or None


def load_spec(path: str = SPEC_PATH) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# --------------------------------------------------------------------------- #
# Bot API (stdlib urllib only — no extra dependency)
# --------------------------------------------------------------------------- #
def _api_call(token: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    url = API_BASE.format(token=token, method=method)
    data = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} HTTP {exc.code}: {body[:300]}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} network error: {exc}")
    if not payload.get("ok"):
        raise RuntimeError(f"{method} failed: {payload.get('description')}")
    return payload["result"]


def _all_groups(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for prod in spec.get("products", []):
        for g in prod.get("groups", []):
            g = dict(g)
            g["_product"] = prod.get("name")
            out.append(g)
    for g in spec.get("cross_product", []):
        g = dict(g)
        g["_product"] = "cross-product"
        out.append(g)
    return out


# --------------------------------------------------------------------------- #
# Plan (no network)
# --------------------------------------------------------------------------- #
def plan(spec: dict[str, Any]) -> int:
    groups = _all_groups(spec)
    print(f"[telegram_setup] PLAN — {len(groups)} entities from {SPEC_PATH}\n")
    pending = 0
    for g in groups:
        cid = g.get("chat_id")
        state = "READY (chat_id set)" if cid else "NEEDS chat_id (owner creates first)"
        if not cid:
            pending += 1
        print(f"  • [{g['_product']}] {g['name']}")
        print(f"      kind={g['kind']}  access={g['access']}  {state}")
        if g.get("forum_topics"):
            print(f"      topics: {', '.join(g['forum_topics'])}")
        print(f"      will set description, post+pin intro"
              + (f", export invite link" if g['access'] == 'private' else ""))
    print(f"\n[telegram_setup] {pending} entity/ies still need a chat_id before --apply.")
    return 0


# --------------------------------------------------------------------------- #
# Apply (live)
# --------------------------------------------------------------------------- #
def apply(spec: dict[str, Any], token: str) -> int:
    groups = _all_groups(spec)
    done, skipped, failed = 0, 0, 0
    print(f"[telegram_setup] APPLY — configuring {len(groups)} entities\n")
    for g in groups:
        cid = g.get("chat_id")
        if not cid:
            print(f"  SKIP  {g['name']} — no chat_id (owner must create + fill spec)")
            skipped += 1
            continue
        try:
            _api_call(token, "setChatDescription",
                      {"chat_id": cid, "description": _description(g)})
            if g.get("forum_topics") and g["kind"] == "supergroup":
                for topic in g["forum_topics"]:
                    _api_call(token, "createForumTopic",
                              {"chat_id": cid, "name": topic[:128]})
            if g.get("intro"):
                sent = _api_call(token, "sendMessage",
                                 {"chat_id": cid, "text": g["intro"],
                                  "disable_web_page_preview": True})
                _api_call(token, "pinChatMessage",
                          {"chat_id": cid,
                           "message_id": sent["message_id"],
                           "disable_notification": True})
            link = None
            if g["access"] == "private":
                link = _api_call(token, "exportChatInviteLink",
                                 {"chat_id": cid}).get("invite_link")
            print(f"  OK    {g['name']}"
                  + (f"  invite={link}" if link else ""))
            done += 1
        except RuntimeError as exc:
            print(f"  FAIL  {g['name']} — {exc}")
            failed += 1
    print(f"\n[telegram_setup] done={done} skipped={skipped} failed={failed}")
    return 1 if failed else 0


def _description(g: dict[str, Any]) -> str:
    parts = [g.get("purpose", "").strip()]
    if g.get("target_audience"):
        parts.append(f"Audience: {g['target_audience']}")
    if g.get("access"):
        parts.append(f"Access: {g['access']}")
    return "\n".join(p for p in parts if p)[:256]


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LeadGen AI Telegram setup bootstrap")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--validate", action="store_true", help="parse spec only")
    grp.add_argument("--plan", action="store_true", help="dry run, no network")
    grp.add_argument("--apply", action="store_true", help="live configure (needs token+enabled)")
    args = ap.parse_args(argv)

    if args.validate:
        spec = load_spec()
        n = len(_all_groups(spec))
        print(f"[telegram_setup] spec OK — {n} entities, "
              f"{len(spec.get('admin_roles', {}))} roles")
        return 0

    if args.plan:
        if not setup_enabled():
            print("[telegram_setup] NOTE: TELEGRAM_SETUP_ENABLED not set — "
                  "plan is safe regardless. (no network used)")
        return plan(load_spec())

    # --apply
    if not setup_enabled():
        print("[telegram_setup] REFUSED: set TELEGRAM_SETUP_ENABLED=1 to apply.",
              file=sys.stderr)
        return 3
    token = get_token()
    if not token:
        print("[telegram_setup] REFUSED: TELEGRAM_BOT_TOKEN missing.",
              file=sys.stderr)
        return 3
    return apply(load_spec(), token)


if __name__ == "__main__":
    raise SystemExit(main())
