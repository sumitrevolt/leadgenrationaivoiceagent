#!/usr/bin/env python3
"""Local PC <-> VPS Telegram/coordination runner (owner contract R4/M7).

What this process is — and is NOT:
  * IS: presence/heartbeat producer to the VPS Coordination Hub (existing
    HMAC-signed tool channel: /api/admin/owner-os/coordination-hub/tools/...),
    an optional local coordination bot poller (its OWN token — never the
    Jarvis token, which is owned exclusively by the VPS ingress), and an
    owner-command surface for local actions (/local, /approve).
  * IS NOT: a second getUpdates consumer for any token the VPS owns. Two
    pollers on one token => 409 conflict. The two machines coordinate via
    the Coordination Hub event/presence ledger (VPS is the authority), not
    by racing over Telegram update streams.

Runs on the owner's Windows PC. Stdlib only (no venv required):
    python scripts/local_telegram_coord.py --once            # one heartbeat
    python scripts/local_telegram_coord.py --loop            # heartbeat every N s
    python scripts/local_telegram_coord.py --with-bot        # + local bot poller
                                                            #   (needs TELEGRAM_LOCAL_BOT_TOKEN)
Environment (never in source — set in the user's env / secrets manager):
    COORD_HUB_BASE_URL            default https://leadsgenai.in
    COORD_HUB_TOOL_LOCALPC_SECRET  >=32 chars; the Hub per-tool HMAC secret
    COORD_HUB_BRANCH / COORD_HUB_WORKTREE / COORD_HUB_HOST   optional tags
    TELEGRAM_LOCAL_BOT_TOKEN       optional; local coordination bot (own token)
    TELEGRAM_LOCAL_OWNER_IDS       numeric allowlist for the local bot
                                   (e.g. the owner's numeric Telegram user id)
    LOCAL_COORD_INTERVAL           heartbeat interval seconds (default 30)

Secret discipline: this script prints nothing that looks like a secret;
missing-config errors name the variable, not its value.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("COORD_HUB_BASE_URL", "https://leadsgenai.in").rstrip("/")
TOOL_ID = "localpc"
SECRET_ENV = "COORD_HUB_TOOL_LOCALPC_SECRET"
MIN_SECRET = 32
ATTESTATION_VERSION = "coord-hub-hmac-sha256-v1"  # MUST match app.platform.coordination_hub_auth


# ---------------------------------------------------------------------------
# Coordination Hub HMAC heartbeat (canonical payload = the same verifier
# the deployed backend uses; see scripts/coord_hub_heartbeat.py)
# ---------------------------------------------------------------------------


def _canonical_payload(*, tool_id: str, body_sha256: str, issued_at: int, nonce: str) -> bytes:
    payload = {
        "body_sha256": body_sha256,
        "event_type": "heartbeat",
        "issued_at": int(issued_at),
        "nonce": nonce,
        "tool_id": tool_id,
        "version": ATTESTATION_VERSION,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def local_status() -> dict:
    """Owner-visible local PC status (no secrets, no customer data)."""
    status = {
        "host": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    branch = os.environ.get("COORD_HUB_BRANCH", "").strip()
    worktree = os.environ.get("COORD_HUB_WORKTREE", "").strip()
    if not branch and _git_present():
        branch = _git_branch()
    if branch:
        status["branch"] = branch
    if worktree:
        status["worktree"] = worktree
    return status


def _git_present() -> bool:
    for cand in ("C:\\PROGRA~1\\Git\\cmd\\git.exe", "/usr/bin/git", "git"):
        try:
            if cand.endswith(".exe") and not os.path.exists(cand):
                continue
            subprocess.run([cand, "--version"], capture_output=True, timeout=5)
            return True
        except Exception:
            continue
    return False


def _git_branch() -> str:
    import glob

    candidates = glob.glob(os.path.expanduser("~/leadgen-work")) + [
        os.path.join(os.path.expanduser("~"), "leadgen-work")
    ]
    for repo in dict.fromkeys(candidates):
        if not os.path.isdir(os.path.join(repo, ".git")):
            continue
        try:
            for cand in ("C:\\PROGRA~1\\Git\\cmd\\git.exe", "git"):
                out = subprocess.run(
                    [cand, "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if out.returncode == 0 and out.stdout.strip():
                    return f"{repo.split(os.sep)[-1]}:{out.stdout.strip()}"
        except Exception:
            continue
    return ""


def send_heartbeat(meta: dict | None = None, status: str = "online") -> dict:
    """One HMAC-signed presence/event to the VPS Coordination Hub.

    Returns a redacted result dict (HTTP code + short message). Never raises
    network errors into the caller loop."""
    secret = os.environ.get(SECRET_ENV, "").strip()
    if len(secret) < MIN_SECRET:
        return {
            "ok": False,
            "reason": "secret_missing",
            "detail": f"{SECRET_ENV} not set or < {MIN_SECRET} chars (set it; value never printed)",
        }

    body = json.dumps(
        {"status": status[:32], "meta": {k: str(v)[:80] for k, v in (meta or {}).items()}},
        separators=(",", ":"),
    ).encode("utf-8")
    issued_at = int(time.time())
    nonce = secrets.token_urlsafe(24)
    digest = hashlib.sha256(body).hexdigest()
    signature = hmac.new(
        secret.encode("utf-8"),
        _canonical_payload(
            tool_id=TOOL_ID, body_sha256=digest, issued_at=issued_at, nonce=nonce
        ),
        hashlib.sha256,
    ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-CoordHub-Timestamp": str(issued_at),
        "X-CoordHub-Nonce": nonce,
        "X-CoordHub-Signature": signature,
        "X-CoordHub-Event-Type": "heartbeat",
    }
    req = urllib.request.Request(
        f"{BASE}/api/admin/owner-os/coordination-hub/tools/{TOOL_ID}/heartbeat",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8", "replace")
            ok = resp.status == 200
            return {
                "ok": ok,
                "http": resp.status,
                "note": text[:200],
            }
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            detail = ""
        return {"ok": False, "http": e.code, "reason": "http_error", "detail": detail}
    except Exception as e:  # network problems must not crash the PC runner
        return {"ok": False, "reason": "network_error", "detail": str(e)[:160]}


# ---------------------------------------------------------------------------
# Local coordination bot (OPTIONAL, own token only)
# ---------------------------------------------------------------------------


class LocalBot:
    """Polls the LOCAL coordination bot token (never Jarvis's) for owner
    commands in the owner's allowed chats. Commands:
      /local     -> local PC status (host/branch/python/last coord result)
      /approve   -> record owner decision on the Hub via next heartbeat meta
    State (offset + decisions) persists to data/telegram/local_coord_state.json
    relative to CWD so a restart resumes without double-processing."""

    def __init__(self, token: str):
        self.token = token
        self._state_path = os.path.join(
            os.getcwd(), "data", "telegram", "local_coord_state.json"
        )

    # -- state persistence ----------------------------------------------------
    def _load_state(self) -> dict:
        try:
            with open(self._state_path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {"offset": 0, "decisions": []}

    def _save_state(self, state: dict) -> None:
        os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
        tmp = self._state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp, self._state_path)

    def _api(self, method: str, params: dict | None = None) -> dict:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        data = json.dumps(params).encode() if params else None
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"} if data else {}
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8", "replace"))
            except Exception:
                return {"ok": False, "error_code": e.code}
        except Exception as e:
            return {"ok": False, "error": str(e)[:160]}

    def _owner_allowed(self, user_id, chat_id) -> bool:
        raw = os.environ.get("TELEGRAM_LOCAL_OWNER_IDS", "").strip()
        ids = set()
        for item in raw.split(","):
            c = item.strip().lstrip("@")
            if c.isdigit() or (c.startswith("-") and c[1:].isdigit()):
                ids.add(int(c))
        if not ids:
            return False  # allowlist required — fail closed
        return (user_id in ids) or (chat_id in ids)

    def poll_once(self) -> dict:
        state = self._load_state()
        res = self._api(
            "getUpdates", {"offset": state["offset"] + 1, "timeout": 0, "limit": 50}
        )
        if not res.get("ok"):
            return {"ok": False, "detail": res.get("description", "getUpdates failed")}
        updates = res.get("result", [])
        handled = 0
        for upd in updates:
            upd_id = upd.get("update_id")
            msg = upd.get("message") or {}
            chat_id = (msg.get("chat") or {}).get("id")
            user_id = (msg.get("from") or {}).get("id")
            text = (msg.get("text") or "").strip()
            if not text:
                if upd_id:
                    state["offset"] = max(state["offset"], upd_id)
                continue
            if not self._owner_allowed(user_id, chat_id):
                self._api("sendMessage", {"chat_id": chat_id, "text": "🔒 Not authorized."})
                state["offset"] = max(state["offset"], upd_id or 0)
                continue
            if text.lower().startswith("/local"):
                self._api(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": f"🖥 **Local PC Status**\n"
                        + json.dumps(local_status(), indent=2)[:3500],
                        "parse_mode": "Markdown",
                    },
                )
                handled += 1
            elif text.lower().startswith("/approve"):
                decision = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "text": text[:200]}
                state.setdefault("decisions", []).append(decision)
                self._api(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": (
                            f"✅ Recorded: `{text[:120]}`\n"
                            "It will ride the next localpc heartbeat meta to the "
                            "VPS Coordination Hub (owner-visible event)."
                        ),
                        "parse_mode": "Markdown",
                    },
                )
                handled += 1
            if upd_id:
                state["offset"] = max(state["offset"], upd_id)
        self._save_state(state)
        return {"ok": True, "handled": handled, "state_offset": state["offset"]}

    def pending_decision_meta(self) -> dict:
        """Drain recorded decisions into heartbeat meta (one-shot)."""
        state = self._load_state()
        pending = state.pop("decisions", [])
        if pending:
            self._save_state(state)
            latest = pending[-1]
            return {"last_decision": f"{latest.get('text', '')[:120]}", "decision_count": len(pending)}
        return {}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Local PC <-> VPS coordination runner")
    parser.add_argument("--once", action="store_true", help="one heartbeat, exit")
    parser.add_argument("--loop", action="store_true", help="heartbeat every N seconds")
    parser.add_argument("--with-bot", action="store_true", help="also run the local bot poller")
    args = parser.parse_args(argv)

    bot: LocalBot | None = None
    if args.with_bot or os.environ.get("TELEGRAM_LOCAL_BOT_TOKEN", "").strip():
        token = os.environ.get("TELEGRAM_LOCAL_BOT_TOKEN", "").strip()
        if len(token) < 20:
            print("[local-coord] TELEGRAM_LOCAL_BOT_TOKEN unset/short — bot disabled")
            bot = None
        else:
            bot = LocalBot(token)

    if args.once:
        meta = local_status()
        if bot:
            meta.update(bot.pending_decision_meta())
        result = send_heartbeat(meta=meta)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    interval = int(os.environ.get("LOCAL_COORD_INTERVAL", "30") or 30)
    print(
        f"[local-coord] loop start (interval={interval}s, hub={BASE}, bot={'on' if bot else 'off'})"
    )
    stop = {"flag": False}

    def _term(signum, frame):
        stop["flag"] = True

    try:
        import signal as _sig

        _sig.signal(_sig.SIGTERM, _term)
        _sig.signal(_sig.SIGINT, _term)
    except Exception:
        pass

    while not stop["flag"]:
        meta = local_status()
        if bot:
            meta.update(bot.pending_decision_meta())
            bot.poll_once()
        result = send_heartbeat(meta=meta)
        if not result.get("ok"):
            print(f"[local-coord] heartbeat failed: {result.get('reason', result.get('detail', ''))[:120]}")
        time.sleep(interval)
    print("[local-coord] stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
