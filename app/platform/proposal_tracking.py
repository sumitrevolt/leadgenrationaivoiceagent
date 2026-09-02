"""Trackable proposals — "client ne proposal khola ya nahi" pata chale.

Proposal bhejo to plain link nahi — tracking link bhejo. Client kholta hai to
view log hota hai (ts + UA + coarse IP). views>0 = "proposal khola" — sales
follow-up ka PERFECT timing signal.

  make_tracked(url|html, phone?, label?) -> token + tracking URL (/api/clientops/p/{token})
  resolve(token)                          -> {"url": ...} ya {"html": ...} ya None
  record_view(token, ua, ip)              -> view log (data/proposal_views.jsonl)
  views(token)                            -> view list + opened bool + first_view
  list_tracked(limit)                     -> recent tracked proposals + view counts

Stores: data/tracked_proposals.jsonl (links) + data/proposal_views.jsonl (views)
+ data/proposal_html/<token>.html (stored HTML variant).
Privacy: IP coarse (last octet masked), UA truncated.
Pure stdlib + file IO. NEVER raises.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_LINKS_FILE = os.path.join("data", "tracked_proposals.jsonl")
_VIEWS_FILE = os.path.join("data", "proposal_views.jsonl")
_HTML_DIR = os.path.join("data", "proposal_html")

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,48}$")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[proposal_tracking] append failed: {e}")


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
        logger.debug(f"[proposal_tracking] read skip: {e}")
    return out


def _site_base() -> str:
    try:
        from app.marketing.embed_widget import site_base

        return site_base()
    except Exception:
        return "https://leadsgenai.in"


def _coarse_ip(ip: str) -> str:
    """Privacy-coarse IP — last octet mask (DPDP-friendly view log)."""
    try:
        parts = str(ip or "").strip().split(".")
        if len(parts) == 4:
            return ".".join(parts[:3]) + ".x"
        return str(ip or "")[:24]  # ipv6/other — truncate
    except Exception:
        return ""


def _html_path(token: str) -> str:
    safe = "".join(ch for ch in token if ch.isalnum() or ch in "_-")[:48]
    return os.path.join(_HTML_DIR, f"{safe}.html")


def make_tracked(
    url: str = "",
    html: str = "",
    phone: str = "",
    label: str = "",
) -> dict[str, Any]:
    """Tracking link banao — `url` (redirect) YA `html` (stored page). Never raises."""
    try:
        url = str(url or "").strip()
        html = str(html or "")
        if not url and not html.strip():
            return {"ok": False, "error": "url ya html me se ek zaroori hai."}
        if url and not url.lower().startswith(("http://", "https://")):
            return {"ok": False, "error": "valid http(s) URL chahiye."}
        token = secrets.token_urlsafe(12)
        rec = {
            "token": token,
            "url": url[:2000],
            "has_html": bool(html.strip()),
            "phone": re.sub(r"\D", "", str(phone or ""))[-10:],
            "label": str(label or "").strip()[:120],
            "created_at": _now(),
        }
        if html.strip():
            try:
                os.makedirs(_HTML_DIR, exist_ok=True)
                with open(_html_path(token), "w", encoding="utf-8") as f:
                    f.write(html[:500_000])
            except Exception as e:
                logger.warning(f"[proposal_tracking] html store failed: {e}")
                rec["has_html"] = False
                if not url:
                    return {"ok": False, "error": "html store nahi ho paya."}
        _append(_LINKS_FILE, rec)
        return {
            "ok": True,
            "token": token,
            "tracking_url": f"{_site_base()}/api/clientops/p/{token}",
            "record": rec,
        }
    except Exception as e:
        logger.warning(f"[proposal_tracking] make_tracked failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def _find(token: str) -> dict[str, Any] | None:
    if not token or not _TOKEN_RE.match(token):
        return None
    latest: dict[str, Any] | None = None
    for rec in _read_all(_LINKS_FILE):
        if rec.get("token") == token:
            latest = rec
    return latest


def resolve(token: str) -> dict[str, Any] | None:
    """Token → {"url": ...} ya {"html": ...}. Unknown = None. Never raises."""
    try:
        rec = _find(str(token or "").strip())
        if rec is None:
            return None
        if rec.get("has_html"):
            try:
                with open(_html_path(str(rec["token"])), encoding="utf-8") as f:
                    return {"html": f.read()}
            except Exception:
                pass  # html gum — url fallback
        u = str(rec.get("url") or "")
        return {"url": u} if u else None
    except Exception as e:
        logger.warning(f"[proposal_tracking] resolve failed: {e}")
        return None


def record_view(token: str, ua: str = "", ip: str = "") -> None:
    """View log (ts + UA + coarse IP). Never raises."""
    try:
        token = str(token or "").strip()
        if not _TOKEN_RE.match(token):
            return
        _append(
            _VIEWS_FILE,
            {
                "ts": _now(),
                "token": token,
                "ua": str(ua or "")[:120],
                "ip": _coarse_ip(ip),
            },
        )
    except Exception as e:
        logger.debug(f"[proposal_tracking] view log skip: {e}")


def views(token: str) -> dict[str, Any]:
    """Ek proposal ke views — opened detection (views>0). Never raises."""
    try:
        token = str(token or "").strip()
        rows = [v for v in _read_all(_VIEWS_FILE) if v.get("token") == token]
        rec = _find(token)
        return {
            "ok": True,
            "token": token,
            "label": (rec or {}).get("label") or "",
            "opened": len(rows) > 0,
            "view_count": len(rows),
            "first_view": rows[0].get("ts") if rows else None,
            "last_view": rows[-1].get("ts") if rows else None,
            "views": rows[-50:],
            "hint": (
                "Client ne proposal khol liya — abhi follow-up call karo! 🔥"
                if rows
                else "Abhi nahi khola — kal yaad dilao."
            ),
        }
    except Exception as e:
        logger.warning(f"[proposal_tracking] views failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def list_tracked(limit: int = 100) -> list[dict[str, Any]]:
    """Recent tracked proposals + view counts (newest first). Never raises."""
    try:
        counts: dict[str, int] = {}
        firsts: dict[str, str] = {}
        for v in _read_all(_VIEWS_FILE):
            t = str(v.get("token") or "")
            counts[t] = counts.get(t, 0) + 1
            firsts.setdefault(t, str(v.get("ts") or ""))
        rows = []
        for rec in _read_all(_LINKS_FILE):
            t = str(rec.get("token") or "")
            rows.append(
                {
                    **rec,
                    "tracking_url": f"{_site_base()}/api/clientops/p/{t}",
                    "view_count": counts.get(t, 0),
                    "opened": counts.get(t, 0) > 0,
                    "first_view": firsts.get(t),
                }
            )
        return list(reversed(rows))[: max(1, min(int(limit or 100), 500))]
    except Exception as e:
        logger.warning(f"[proposal_tracking] list failed: {e}")
        return []


_SWEEP_CURSOR = os.path.join("data", "proposal_sweep_cursor.json")


def sweep_new_opens() -> dict[str, Any]:
    """Naye proposal-opens ka sweep (watchdog-job se hourly) — "client ne proposal
    khola — abhi call karo" team-event. Cursor se dedupe; sirf event log, NO send.
    Never raises."""
    try:
        last_ts = ""
        try:
            with open(_SWEEP_CURSOR, encoding="utf-8") as f:
                last_ts = str(json.load(f).get("last_ts") or "")
        except Exception:
            pass
        new_opens: list[dict[str, Any]] = []
        max_ts = last_ts
        for v in _read_all(_VIEWS_FILE):
            ts = str(v.get("ts") or "")
            if ts and ts > last_ts:
                new_opens.append(v)
                if ts > max_ts:
                    max_ts = ts
        if new_opens:
            links = {str(r.get("token") or ""): r for r in _read_all(_LINKS_FILE)}
            try:
                from app.platform.team import log_event

                for v in new_opens[:10]:
                    rec = links.get(str(v.get("token") or ""), {})
                    label = rec.get("label") or rec.get("phone") or v.get("token")
                    log_event(
                        "rohan",
                        "proposal_opened",
                        f"📂 Proposal khola: {label} — abhi follow-up call ka best time!",
                    )
            except Exception as e:
                logger.warning(f"[proposal_tracking] sweep event failed: {e}")
            try:
                os.makedirs(os.path.dirname(_SWEEP_CURSOR) or ".", exist_ok=True)
                with open(_SWEEP_CURSOR, "w", encoding="utf-8") as f:
                    json.dump({"last_ts": max_ts}, f)
            except Exception:
                pass
        return {"ok": True, "new_opens": len(new_opens)}
    except Exception as e:
        logger.warning(f"[proposal_tracking] sweep failed: {e}")
        return {"ok": False, "error": str(e)}


__all__ = [
    "make_tracked",
    "resolve",
    "record_view",
    "views",
    "list_tracked",
    "sweep_new_opens",
]
