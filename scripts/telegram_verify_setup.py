#!/usr/bin/env python3
"""
LeadGen AI -- Telegram setup verifier (READ-ONLY, cross-platform)
================================================================
One command that answers: "is Telegram actually working right now?" with live
evidence instead of documentation claims.

Checks (no writes, no message sends, no getUpdates consumption):
  1. Credential slots: present? live-valid (``getMe``)? env-vs-.env divergence?
     Only SHA-256 fingerprints are printed -- never a token value.
  2. Webhook state per valid token (a set webhook blocks polling → coordination).
  3. Polling conflict probe: ``getUpdates(allowed_updates=[])`` returns instantly
     and does NOT consume updates, so HTTP 409 proves another consumer holds the
     token (e.g. the Hermes gateway).
  4. Group wiring from ``config/telegram/setup_spec.yaml``: exists? bot member?
     forum? → unwired coordination groups are called out explicitly.
  5. Ingress coordination snapshot: owner role, lease holder, standby state.

Usage::

    python scripts/telegram_verify_setup.py            # human table
    python scripts/telegram_verify_setup.py --json     # machine readable
    python scripts/telegram_verify_setup.py --no-groups   # fast credential-only
    python scripts/telegram_verify_setup.py --env-file /opt/leadgen/.env

Exit codes: 0 = green · 1 = critical (polling impossible / token dead) ·
2 = degraded (warnings, e.g. unwired groups or dead egress token).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover - dotenv is a hard project dep
    dotenv_values = None  # type: ignore[assignment]

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

_TEXT_SLOTS = (
    ("jarvis", "TELEGRAM_JARVIS_BOT_TOKEN"),
    ("notify", "TELEGRAM_NOTIFY_BOT_TOKEN"),
    ("fallback", "TELEGRAM_BOT_TOKEN"),
)
_SPEC_PATH = ROOT / "config" / "telegram" / "setup_spec.yaml"

# Critical coordination surfaces the owner asked for (cross_product keys).
_REQUIRED_COORDINATION = ("workers_coordination", "agents_coordination", "admin_command_center")


def _fingerprint(value: str | None) -> str:
    if not value:
        return "ABSENT"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def _api(token: str, method: str, http_timeout: float = 12.0, **params: Any) -> dict[str, Any]:
    """Raw Bot API call. ``http_timeout`` is separate from Telegram's own ``timeout`` param."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    body = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error_code": exc.code, "description": exc.reason}
    except Exception as exc:
        return {"ok": False, "description": f"{type(exc).__name__}: {str(exc)[:80]}"}


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if dotenv_values is not None:
        return {k: (v or "") for k, v in dotenv_values(path).items()}
    parsed: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        parsed[key.strip()] = value.strip().strip('"').strip("'")
    return parsed


def check_credentials(file_env: dict[str, str]) -> dict[str, Any]:
    """Credential state per slot with live validity and env/file divergence."""
    out: dict[str, Any] = {}
    for label, env_name in _TEXT_SLOTS:
        proc = os.environ.get(env_name, "").strip()
        filed = (file_env.get(env_name) or "").strip()
        effective = proc or filed
        entry: dict[str, Any] = {
            "env": env_name,
            "present_process_env": bool(proc),
            "present_dotenv": bool(filed),
            "divergent": bool(proc and filed and _fingerprint(proc) != _fingerprint(filed)),
            "fingerprint": _fingerprint(effective),
        }
        if len(effective) < 20:
            entry.update({"valid": False, "reason": "absent_or_short", "username": None})
        else:
            res = _api(effective, "getMe")
            result = res.get("result") or {}
            entry.update(
                {
                    "valid": bool(res.get("ok")),
                    "reason": "ok" if res.get("ok") else ("unauthorized" if res.get("error_code") == 401 else str(res.get("description"))[:80]),
                    "username": ("@" + str(result.get("username"))) if result.get("username") else None,
                    "bot_id": result.get("id"),
                    "effective_source": "process_env" if proc else "dotenv",
                }
            )
            if res.get("ok"):
                webhook = _api(effective, "getWebhookInfo").get("result") or {}
                entry["webhook_url_set"] = bool(webhook.get("url"))
                entry["webhook_pending"] = webhook.get("pending_update_count")
                entry["webhook_last_error"] = webhook.get("last_error_message")
        out[label] = entry
    return out


def check_polling_conflict(jarvis_token: str | None) -> dict[str, Any]:
    """Non-consuming 409 probe. ``allowed_updates=[]`` returns instantly."""
    if not jarvis_token:
        return {"probed": False, "reason": "no_jarvis_token"}
    res = _api(jarvis_token, "getUpdates", http_timeout=10.0, timeout=0, limit=1, allowed_updates=[])
    if res.get("ok"):
        return {
            "probed": True,
            "conflict": False,
            "reason": "no_other_consumer",
            "note": "This probe does not consume updates.",
        }
    desc = str(res.get("description") or "")
    if res.get("error_code") == 409 or "conflict" in desc.lower():
        return {
            "probed": True,
            "conflict": True,
            "indeterminate": False,
            "error_code": res.get("error_code"),
            "reason": desc[:120],
        }
    # Network/TLS failure: the token owner is UNKNOWN, not "nobody".
    return {
        "probed": True,
        "conflict": None,
        "indeterminate": True,
        "error_code": res.get("error_code"),
        "reason": desc[:120],
    }


def _spec_groups() -> list[dict[str, Any]]:
    if yaml is None or not _SPEC_PATH.exists():
        return []
    spec = yaml.safe_load(_SPEC_PATH.read_text(encoding="utf-8")) or {}
    groups: list[dict[str, Any]] = []
    for product in spec.get("products", []) or []:
        for group in product.get("groups", []) or []:
            groups.append({**group, "_scope": f"product:{product.get('id')}"})
    for group in spec.get("cross_product", []) or []:
        groups.append({**group, "_scope": "cross_product", "_key": group.get("key")})
    return groups


def check_groups(token: str | None, bot_id: int | None) -> list[dict[str, Any]]:
    """Group wiring: exists / bot membership / forum / unwired coordination."""
    results: list[dict[str, Any]] = []
    for group in _spec_groups():
        chat_id = str(group.get("chat_id") or "").strip()
        entry: dict[str, Any] = {
            "key": group.get("key"),
            "name": group.get("name"),
            "scope": group.get("_scope"),
            "chat_id_set": bool(chat_id),
            "required": group.get("key") in _REQUIRED_COORDINATION and group.get("_scope") == "cross_product",
        }
        if not chat_id:
            entry.update({"ok": False, "reason": "unwired_no_chat_id", "bot_status": None})
            results.append(entry)
            continue
        if not token:
            entry.update({"ok": False, "reason": "no_valid_token_to_probe", "bot_status": None})
            results.append(entry)
            continue
        chat = _api(token, "getChat", chat_id=chat_id)
        details = chat.get("result") or {}
        member_status = None
        if chat.get("ok") and bot_id:
            member = _api(token, "getChatMember", chat_id=chat_id, user_id=bot_id)
            member_status = (member.get("result") or {}).get("status")
        entry.update(
            {
                "ok": bool(chat.get("ok")) and member_status in {"administrator", "creator", "member"},
                "title": details.get("title"),
                "is_forum": details.get("is_forum"),
                "bot_status": member_status,
                "reason": "ok" if chat.get("ok") else str(chat.get("description"))[:60],
                "expected_topics": group.get("forum_topics") or [],
                "topic_ids": sorted((group.get("topic_ids") or {}).keys()),
            }
        )
        results.append(entry)
    return results


def check_coordination() -> dict[str, Any]:
    """Ingress coordination snapshot (never acquires the lease)."""
    try:
        from app.platform.telegram_coordinator import (
            get_instance_id,
            get_polling_lease,
            ingress_conflict_state,
            ingress_owner_role,
            instance_role,
        )
    except Exception as exc:  # pragma: no cover - import guard
        return {"available": False, "reason": str(exc)[:80]}

    me = get_instance_id()
    lease = get_polling_lease(me)
    return {
        "available": True,
        "ingress_owner_role": ingress_owner_role(),
        "instance_role": instance_role(),
        "instance_id": me,
        "lease": lease,
        "conflicts": ingress_conflict_state(),
        "lease_would_be_free": (not lease.get("holder")) or bool(lease.get("stale")),
    }


def _verdict(report: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    criticals: list[str] = []
    warnings: list[str] = []

    jarvis = report["credentials"]["jarvis"]
    if not jarvis.get("present_process_env") and not jarvis.get("present_dotenv"):
        criticals.append("TELEGRAM_JARVIS_BOT_TOKEN is ABSENT -- no interactive ingress possible")
    elif not jarvis.get("valid"):
        criticals.append(f"Jarvis token slot is INVALID ({jarvis.get('reason')}) -- owner must re-issue it")

    notify = report["credentials"]["notify"]
    if not notify.get("present_process_env") and not notify.get("present_dotenv"):
        warnings.append("TELEGRAM_NOTIFY_BOT_TOKEN ABSENT -- egress falls back to another slot")
    elif not notify.get("valid"):
        warnings.append(
            "Notify egress token is INVALID (401) -- @Leadsgenai1_bot cannot send; "
            "egress falls back to a live slot but the owner should re-issue this token"
        )

    for label, slot in report["credentials"].items():
        if slot.get("divergent"):
            warnings.append(f"Slot '{label}' differs between process env and .env (drift)")

    conflict = report["polling_conflict"]
    if conflict.get("conflict"):
        warnings.append(
            "Another getUpdates consumer holds the Jarvis token (HTTP 409) -- "
            "set TELEGRAM_INGRESS_OWNER so exactly one owner polls"
        )
    elif conflict.get("indeterminate"):
        warnings.append(
            f"Polling-ownership probe was INDETERMINATE ({conflict.get('reason')}) -- "
            "token holder UNKNOWN, not 'nobody'"
        )

    if report.get("webhook_polling_conflict"):
        criticals.append("A webhook is set while a poller is expected -- both cannot own the same token")

    for group in report.get("groups", []) or []:
        if group.get("required") and not group.get("ok"):
            criticals.append(
                f"Required coordination group '{group.get('name')}' is not wired "
                f"({group.get('reason')}) -- run scripts/telegram_wire_coordination_groups.py"
            )
        elif group.get("chat_id_set") and not group.get("ok"):
            warnings.append(f"Group '{group.get('name')}' unreachable ({group.get('reason')})")

    return (1 if criticals else (2 if warnings else 0)), criticals, warnings


def _effective_token(label: str, file_env: dict[str, str]) -> str:
    """Process env wins over .env (mirrors ``load_dotenv`` precedence in runners)."""
    env_name = dict(_TEXT_SLOTS).get(label, "")
    return os.environ.get(env_name, "").strip() or (file_env.get(env_name) or "").strip()


def build_report(file_env: dict[str, str], with_groups: bool = True) -> dict[str, Any]:
    credentials = check_credentials(file_env)
    jarvis_token = _effective_token("jarvis", file_env) if (credentials.get("jarvis") or {}).get("valid") else None

    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(ROOT),
        "credentials": credentials,
        "polling_conflict": check_polling_conflict(jarvis_token),
        "coordination": check_coordination(),
    }

    token, bot_id = None, None
    for label in ("jarvis", "notify", "fallback"):
        slot = credentials.get(label) or {}
        if slot.get("valid"):
            token, bot_id = _effective_token(label, file_env), slot.get("bot_id")
            break

    report["groups"] = check_groups(token, bot_id) if with_groups else []
    report["webhook_polling_conflict"] = bool(
        (credentials.get("jarvis") or {}).get("webhook_url_set") and jarvis_token
    )
    return report


def _print_human(report: dict[str, Any], criticals: list[str], warnings: list[str]) -> None:
    print("=" * 72)
    print("LEADGEN AI -- TELEGRAM SETUP TRUTH TABLE (read-only)")
    print("=" * 72)
    print("CREDENTIAL SLOTS")
    for label, slot in report["credentials"].items():
        print(f"  {label:<8} present(env)={str(slot.get('present_process_env')):<5} "
              f"present(.env)={str(slot.get('present_dotenv')):<5} valid={str(slot.get('valid')):<5} "
              f"fp={slot.get('fingerprint')} {slot.get('username') or ''} "
              f"{'DIVERGENT' if slot.get('divergent') else ''}")
        if slot.get("webhook_url_set") is not None:
            print(f"           webhook_set={slot.get('webhook_url_set')} pending={slot.get('webhook_pending')}")

    conflict = report["polling_conflict"]
    ownership = "UNKNOWN" if conflict.get("indeterminate") else ("OTHER_CONSUMER" if conflict.get("conflict") else "FREE")
    print(f"\nPOLLING CONFLICT PROBE: owner={ownership} ({conflict.get('reason')})")

    coord = report.get("coordination") or {}
    if coord.get("available"):
        lease = coord.get("lease") or {}
        print(f"\nINGRESS COORDINATION: owner={coord.get('ingress_owner_role')} "
              f"instance_role={coord.get('instance_role')} instance={coord.get('instance_id')}")
        print(f"  lease holder={lease.get('holder')} backend={lease.get('backend')} "
              f"held_by_me={lease.get('held_by_me')} stale={lease.get('stale')} "
              f"remaining={lease.get('seconds_remaining')}")
        print(f"  409 conflicts={coord['conflicts'].get('conflict_count')} "
              f"retry_in={coord['conflicts'].get('retry_in_s')} "
              f"last_standby={coord['conflicts'].get('last_standby_reason')}")

    groups = report.get("groups") or []
    if groups:
        wired = sum(1 for g in groups if g.get("ok"))
        print(f"\nGROUPS ({wired}/{len(groups)} wired)")
        for group in groups:
            mark = "OK " if group.get("ok") else ("REQ" if group.get("required") else "ERR")
            print(f"  [{mark}] {str(group.get('name'))[:44]:<44} bot={group.get('bot_status')} "
                  f"forum={group.get('is_forum')} {'' if group.get('ok') else group.get('reason')}")

    print("\n" + "-" * 72)
    for item in criticals:
        print(f"CRITICAL: {item}")
    for item in warnings:
        print(f"WARN    : {item}")
    verdict = "GREEN" if not criticals and not warnings else ("CRITICAL" if criticals else "DEGRADED")
    print(f"VERDICT: {verdict}")
    print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Telegram setup verifier")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--no-groups", action="store_true", help="Skip group membership checks")
    parser.add_argument("--env-file", default=str(ROOT / ".env"), help="Path to the .env to compare against")
    args = parser.parse_args()

    file_env = _load_env_file(Path(args.env_file))
    report = build_report(file_env, with_groups=not args.no_groups)
    code, criticals, warnings = _verdict(report)

    if args.json:
        print(json.dumps({**report, "criticals": criticals, "warnings": warnings, "exit_code": code}, indent=2))
    else:
        _print_human(report, criticals, warnings)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
