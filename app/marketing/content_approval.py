"""Client content-approval loop (agency-grade) — draft → client 1-click approve.

Agency clients ko post publish hone se PEHLE approve karna hota hai. Yeh module
har content piece ka approval record banata hai + client ko bhejne ka WhatsApp
1-click link text (ban-safe: human khud WA pe bhejta hai, auto-send NAHI).

  submit(client_id, content)   -> approval record (status=pending, secret token)
  approve(token) / reject(token, note) -> decide (idempotent)
  pending(client_id="")        -> pending approvals (latest state)
  get_by_token(token)          -> latest state of one approval

Store: data/content_approvals.jsonl — append-on-update, latest line per id wins
(minisite_builder config pattern — lock-free, multi-worker safe enough).
Pure stdlib + file IO. NEVER raises.
"""

from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FILE = os.path.join("data", "content_approvals.jsonl")

_STATUSES = {"pending", "approved", "rejected"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _site_base() -> str:
    try:
        from app.marketing.embed_widget import site_base

        return site_base()
    except Exception:
        return "https://leadsgenai.in"


def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_FILE) or ".", exist_ok=True)
        with open(_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[content_approval] append failed: {e}")


def _read_all() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(_FILE):
            return out
        with open(_FILE, encoding="utf-8") as f:
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
        logger.debug(f"[content_approval] read skip: {e}")
    return out


def _latest_states() -> dict[str, dict[str, Any]]:
    """id → merged latest state (append-on-update; baad wali line jeet ti)."""
    states: dict[str, dict[str, Any]] = {}
    for rec in _read_all():
        rid = str(rec.get("id") or "")
        if not rid:
            continue
        cur = states.get(rid) or {}
        cur.update(rec)
        states[rid] = cur
    return states


def _client_phone(client_id: str) -> str:
    try:
        from app.marketing import clients_store

        c = clients_store.get_client(client_id) or {}
        import re as _re

        return _re.sub(r"\D", "", str(c.get("phone") or ""))[-10:]
    except Exception:
        return ""


def approval_url(token: str, action: str = "approve") -> str:
    return f"{_site_base()}/api/clientops/approve/{token}?action={action}"


def wa_share_text(rec: dict[str, Any]) -> dict[str, str]:
    """Client ko bhejne wala WA message (1-click approve/reject links) + wa.me
    draft link (ban-safe — human send)."""
    content = rec.get("content") or {}
    caption = str(content.get("caption") or content.get("text") or "")[:200]
    title = str(content.get("title") or content.get("occasion") or "naya post")[:80]
    msg = (
        f"Namaste! Aapke business ka {title} taiyaar hai 👇\n\n"
        + (f"“{caption}”\n\n" if caption else "")
        + f"✅ Approve: {approval_url(str(rec.get('token') or ''), 'approve')}\n"
        + f"❌ Change chahiye: {approval_url(str(rec.get('token') or ''), 'reject')}\n\n"
        + "Ek click me ho jayega — shukriya!"
    )
    phone = _client_phone(str(rec.get("client_id") or ""))
    wa_link = (
        f"https://wa.me/91{phone}?text={quote(msg)}"
        if phone
        else f"https://wa.me/?text={quote(msg)}"
    )
    return {"message": msg, "wa_link": wa_link}


def submit(client_id: str, content: dict[str, Any]) -> dict[str, Any]:
    """Naya approval record (status=pending) + WA share draft. Never raises."""
    try:
        client_id = str(client_id or "").strip()[:60]
        if not client_id:
            return {"ok": False, "error": "client_id zaroori hai."}
        if not isinstance(content, dict) or not content:
            return {"ok": False, "error": "content (dict) zaroori hai."}
        rec = {
            "id": uuid.uuid4().hex[:12],
            "token": secrets.token_urlsafe(16),
            "client_id": client_id,
            "content": content,
            "status": "pending",
            "note": "",
            "created_at": _now(),
        }
        _append(rec)
        share = wa_share_text(rec)
        return {
            "ok": True,
            "approval": rec,
            "approve_url": approval_url(rec["token"], "approve"),
            "reject_url": approval_url(rec["token"], "reject"),
            **share,
        }
    except Exception as e:
        logger.warning(f"[content_approval] submit failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def get_by_token(token: str) -> dict[str, Any] | None:
    try:
        token = str(token or "").strip()
        if not token or len(token) > 64:
            return None
        for rec in _latest_states().values():
            if rec.get("token") == token:
                return rec
        return None
    except Exception:
        return None


def _decide(token: str, status: str, note: str = "") -> dict[str, Any]:
    try:
        rec = get_by_token(token)
        if rec is None:
            return {"ok": False, "error": "approval nahi mila (galat ya purana link)."}
        if rec.get("status") in ("approved", "rejected"):
            return {"ok": True, "already_decided": True, "approval": rec}
        update = {
            "id": rec["id"],
            "token": rec.get("token"),
            "client_id": rec.get("client_id"),
            "status": status if status in _STATUSES else "pending",
            "note": str(note or "").strip()[:300],
            "decided_at": _now(),
        }
        _append(update)
        merged = {**rec, **update}
        if status == "approved":
            try:
                from app.marketing import auto_content

                auto_content.enqueue_approved(
                    str(merged.get("client_id") or ""),
                    merged.get("content") or {},
                    str(merged.get("id") or ""),
                )
            except Exception:
                pass
            # Video-ad approve -> publish-queue mark (scheduler hi publish karta; web light).
            try:
                if (merged.get("content") or {}).get("type") == "video_ad":
                    from app.marketing import video_ad_cycle

                    video_ad_cycle.on_approved(merged)
            except Exception:
                pass
        # Video-ad "change chahiye" (reject) -> changes_requested mark (scheduler regen).
        if status == "rejected":
            try:
                if (merged.get("content") or {}).get("type") == "video_ad":
                    from app.marketing import video_ad_cycle

                    video_ad_cycle.on_changes_requested(merged)
            except Exception:
                pass
        # Best-effort team event — dashboard pe dikhe (kabhi raise nahi).
        try:
            from app.platform.team import log_event

            log_event(
                "isha",
                "content_approval",
                f"Client {merged.get('client_id')} ne content {status} kiya"
                + (f" — note: {update['note']}" if update["note"] else ""),
                meta={"approval_id": merged.get("id"), "status": status},
            )
        except Exception:
            pass
        return {"ok": True, "approval": merged}
    except Exception as e:
        logger.warning(f"[content_approval] decide failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def approve(token: str) -> dict[str, Any]:
    return _decide(token, "approved")


def reject(token: str, note: str = "") -> dict[str, Any]:
    return _decide(token, "rejected", note)


def pending(client_id: str = "") -> list[dict[str, Any]]:
    """Pending approvals (optionally ek client ke). Never raises."""
    try:
        client_id = str(client_id or "").strip()
        rows = [
            r
            for r in _latest_states().values()
            if r.get("status") == "pending" and (not client_id or r.get("client_id") == client_id)
        ]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows
    except Exception as e:
        logger.warning(f"[content_approval] pending failed: {e}")
        return []


def _by_id_for_client(client_id: str, approval_id: str) -> dict[str, Any] | None:
    rec = _latest_states().get(str(approval_id or "").strip())
    if not rec or str(rec.get("client_id") or "") != str(client_id or "").strip():
        return None
    return rec


def decide_for_client(
    client_id: str, approval_id: str, action: str, note: str = ""
) -> dict[str, Any]:
    """Authenticated customer portal — id se approve/reject (token expose nahi)."""
    rec = _by_id_for_client(client_id, approval_id)
    if rec is None:
        return {"ok": False, "error": "approval nahi mila."}
    token = str(rec.get("token") or "")
    if action == "reject":
        return reject(token, note)
    return approve(token)


def decide_by_id(approval_id: str, action: str, note: str = "") -> dict[str, Any]:
    """Admin/support — approval id se decide (client_id verify nahi)."""
    rec = _latest_states().get(str(approval_id or "").strip())
    if not rec:
        return {"ok": False, "error": "approval nahi mila."}
    token = str(rec.get("token") or "")
    if not token:
        return {"ok": False, "error": "approval token missing."}
    if action == "reject":
        return reject(token, note)
    return approve(token)


def list_all(client_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Saare approvals latest-state (admin list). Never raises."""
    try:
        client_id = str(client_id or "").strip()
        rows = [
            r for r in _latest_states().values() if not client_id or r.get("client_id") == client_id
        ]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows[: max(1, min(int(limit or 100), 500))]
    except Exception as e:
        logger.warning(f"[content_approval] list failed: {e}")
        return []


def decision_html(result: dict[str, Any], action: str) -> str:
    """Tiny Hinglish HTML — public approve/reject link ka response page."""
    if not result.get("ok"):
        title, body = (
            "Link sahi nahi",
            "Yeh approval link galat ya expire ho chuka hai. Apni agency se naya link maang lo.",
        )
        emoji = "🤔"
    elif result.get("already_decided"):
        st = (result.get("approval") or {}).get("status")
        emoji = "✅" if st == "approved" else "❌"
        title = "Pehle se ho chuka"
        body = f"Yeh content pehle hi {('approve' if st == 'approved' else 'reject')} ho chuka hai — kuch aur karna ho to agency ko batao."
    elif action == "reject":
        emoji, title = "❌", "Reject ho gaya"
        body = "Theek hai — team ko bata diya, naya version jald milega. Shukriya!"
    else:
        emoji, title = "✅", "Approve ho gaya — shukriya!"
        body = "Post ab publish ke liye ready hai. Aapka time bachane ke liye dhanyawad!"
    return (
        "<!doctype html><html lang='hi'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title></head>"
        "<body style='font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;"
        "display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0'>"
        "<div style='text-align:center;padding:32px;max-width:420px'>"
        f"<div style='font-size:56px'>{emoji}</div>"
        f"<h2 style='margin:12px 0 8px'>{title}</h2>"
        f"<p style='color:#94a3b8;line-height:1.5'>{body}</p>"
        "</div></body></html>"
    )


__all__ = [
    "submit",
    "approve",
    "reject",
    "pending",
    "list_all",
    "get_by_token",
    "decide_for_client",
    "wa_share_text",
    "approval_url",
    "decision_html",
]
