"""Lead distribution — round-robin team routing + WA 1-click handoff.

Client ki sales team (2-5 log) me naye leads BAARI-BAARI baante jaate — koi
lead kisi ek bande ke WhatsApp me sadta nahi. Har assignment ka wa.me handoff
link banta (ban-safe: human 1-click send, auto-send NAHI).

  set_config(client_id, members, mode) -> routing config (data/lead_routing.jsonl)
  get_config(client_id)                -> latest config (cursor ke saath)
  assign(client_id, lead)              -> next member + assignment record + wa link
  assignments(client_id, limit)        -> recent assignments

Stores: data/lead_routing.jsonl (config, append-on-update latest-wins) +
data/lead_assignments.jsonl (append-only log).
Pure stdlib + file IO. NEVER raises.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_ROUTING_FILE = os.path.join("data", "lead_routing.jsonl")
_ASSIGN_FILE = os.path.join("data", "lead_assignments.jsonl")

_MAX_MEMBERS = 10


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _phone10(val: Any) -> str:
    return re.sub(r"\D", "", str(val or ""))[-10:]


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[lead_distribution] append failed: {e}")


def _read_all(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(path):
            return out
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except Exception as e:
        logger.debug(f"[lead_distribution] read skip: {e}")
    return out


def _clean_members(members: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in (members or [])[:_MAX_MEMBERS]:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name") or "").strip()[:80]
        phone = _phone10(m.get("phone"))
        if name and len(phone) == 10:
            out.append({"name": name, "phone": phone})
    return out


def set_config(
    client_id: str, members: list[dict[str, Any]], mode: str = "round_robin"
) -> dict[str, Any]:
    """Routing config save (cursor reset 0). Never raises."""
    try:
        client_id = str(client_id or "").strip()[:60]
        if not client_id:
            return {"ok": False, "error": "client_id zaroori hai."}
        clean = _clean_members(members)
        if not clean:
            return {"ok": False, "error": "kam se kam 1 member (name + 10-digit phone) chahiye."}
        rec = {
            "client_id": client_id,
            "members": clean,
            "mode": "round_robin" if str(mode or "") not in ("round_robin",) else mode,
            "cursor": 0,
            "updated_at": _now(),
        }
        _append(_ROUTING_FILE, rec)
        return {"ok": True, "config": rec}
    except Exception as e:
        logger.warning(f"[lead_distribution] set_config failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def get_config(client_id: str) -> dict[str, Any] | None:
    """Latest config for client (append-on-update — last line wins). Never raises."""
    try:
        client_id = str(client_id or "").strip()
        latest: dict[str, Any] | None = None
        for rec in _read_all(_ROUTING_FILE):
            if str(rec.get("client_id") or "") == client_id:
                latest = rec
        return latest
    except Exception:
        return None


def _handoff_text(member: dict[str, str], lead: dict[str, Any]) -> dict[str, str]:
    name = str(lead.get("name") or "naya lead")[:80]
    phone = _phone10(lead.get("phone"))
    note = str(lead.get("message") or lead.get("note") or "")[:160]
    msg = (
        f"🔥 Naya lead aapke naam: {name}"
        + (f" ({phone})" if phone else "")
        + (f"\nNote: {note}" if note else "")
        + "\n2 minute ke andar call karo — lead garam hai! 💪"
    )
    wa_link = f"https://wa.me/91{member['phone']}?text={quote(msg)}"
    return {"message": msg, "wa_link": wa_link}


def assign(client_id: str, lead: dict[str, Any]) -> dict[str, Any]:
    """Round-robin next member + assignment log + WA handoff link. Never raises."""
    try:
        client_id = str(client_id or "").strip()
        if not client_id:
            return {"ok": False, "error": "client_id zaroori hai."}
        if not isinstance(lead, dict) or not lead:
            return {"ok": False, "error": "lead (dict) zaroori hai."}
        cfg = get_config(client_id)
        if not cfg or not cfg.get("members"):
            return {
                "ok": False,
                "error": "is client ka routing config nahi — pehle POST /api/clientops/routing se team set karo.",
            }
        members = cfg["members"]
        cursor = int(cfg.get("cursor") or 0)
        member = members[cursor % len(members)]

        # cursor advance (append-on-update; race acceptable — never blocks)
        _append(
            _ROUTING_FILE,
            {**cfg, "cursor": (cursor + 1) % len(members), "updated_at": _now()},
        )

        handoff = _handoff_text(member, lead)
        rec = {
            "id": uuid.uuid4().hex[:12],
            "ts": _now(),
            "client_id": client_id,
            "member": member,
            "lead": {
                "name": str(lead.get("name") or "")[:120],
                "phone": _phone10(lead.get("phone")),
                "source": str(lead.get("source") or "")[:60],
                "message": str(lead.get("message") or "")[:300],
            },
            "wa_link": handoff["wa_link"],
        }
        _append(_ASSIGN_FILE, rec)
        return {"ok": True, "assigned_to": member, "assignment": rec, **handoff}
    except Exception as e:
        logger.warning(f"[lead_distribution] assign failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def maybe_assign(client_id: str, lead: dict[str, Any]) -> dict[str, Any] | None:
    """Routing config ho to auto round-robin assign — warna None (silent skip)."""
    try:
        client_id = str(client_id or "").strip()
        if not client_id or not isinstance(lead, dict):
            return None
        if not get_config(client_id):
            return None
        out = assign(client_id, lead)
        return out if out.get("ok") else None
    except Exception:
        return None


def assignments(client_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Recent assignments (newest first). Never raises."""
    try:
        client_id = str(client_id or "").strip()
        rows = [
            r
            for r in _read_all(_ASSIGN_FILE)
            if not client_id or str(r.get("client_id") or "") == client_id
        ]
        return list(reversed(rows))[: max(1, min(int(limit or 100), 500))]
    except Exception as e:
        logger.warning(f"[lead_distribution] assignments failed: {e}")
        return []


__all__ = ["set_config", "get_config", "assign", "maybe_assign", "assignments"]
