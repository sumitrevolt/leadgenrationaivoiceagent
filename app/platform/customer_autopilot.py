"""Customer Autopilot — per-client hands-free automations (draft/store-only).

4 background jobs jo har paid client ke business ke liye KHUD chalti hain. Sab:
  * env-flag gated, DEFAULT-OFF (deploy pe inert = zero regression)
  * draft/store-only — koi bulk auto-send NAHI (ban-safe)
  * per-client loop, idempotent (date-key dedupe), KABHI raise nahi karti
  * free-stack (existing engines reuse: evergreen / nps / speed_to_lead / clients_store)

Wired into team_scheduler 'content' job via run_all(). Behind-flag = inert.
Output drafts `data/autopilot_*.jsonl` me jaate (customer dashboard/ops read kar sakta).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DATA_DIR = "data"


def _flag_on(name: str) -> bool:
    """Env flag truthy? Default OFF (unset = off)."""
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _existing_keys(path: str, today: str) -> set[str]:
    """Aaj ke already-written dedupe-keys (idempotency — ek din ek hi draft)."""
    keys: set[str] = set()
    try:
        if not os.path.exists(path):
            return keys
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("date") == today and rec.get("dedupe_key"):
                    keys.add(str(rec["dedupe_key"]))
    except Exception as e:  # pragma: no cover
        logger.debug(f"[autopilot] _existing_keys skip ({path}): {e}")
    return keys


def _append(path: str, rec: dict[str, Any]) -> bool:
    """Best-effort append one jsonl row. Never raises."""
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception as e:  # pragma: no cover
        logger.debug(f"[autopilot] _append skip ({path}): {e}")
        return False


def _clients() -> list[dict[str, Any]]:
    try:
        from app.marketing import clients_store

        return list(clients_store.list_clients() or [])
    except Exception as e:  # pragma: no cover
        logger.debug(f"[autopilot] clients load skip: {e}")
        return []


# ── 1) Evergreen content auto-repost ──────────────────────────────────────────
async def evergreen_recycle_all(max_clients: int = 25) -> dict[str, Any]:
    """Har client ke 1-2 purane top posts auto-freshen + content-queue me re-append.
    evergreen.recycle_for_client khud draft + date-dedupe handle karta (idempotent)."""
    if not _flag_on("EVERGREEN_RECYCLE"):
        return {"ok": True, "skipped": "flag_off"}
    added = 0
    clients_done = 0
    try:
        from app.marketing import evergreen

        for c in _clients()[:max_clients]:
            try:
                items = await evergreen.recycle_for_client(c)
                added += len(items or [])
                clients_done += 1
            except Exception as e:  # pragma: no cover
                logger.debug(f"[autopilot] evergreen client skip: {e}")
    except Exception as e:  # pragma: no cover
        logger.warning(f"[autopilot] evergreen_recycle_all failed: {e}")
    return {"ok": True, "clients": clients_done, "recycled": added}


# ── 2) NPS / CSAT auto survey-drafts ──────────────────────────────────────────
def nps_survey_drafts(limit: int = 50) -> dict[str, Any]:
    """Har active client ke liye NPS-survey WhatsApp draft (ban-safe, no auto-send).
    Drafts data/autopilot_nps.jsonl me store — date+slug dedupe (ek din ek baar)."""
    if not _flag_on("NPS_AUTO"):
        return {"ok": True, "skipped": "flag_off"}
    path = os.path.join(_DATA_DIR, "autopilot_nps.jsonl")
    today = _today()
    seen = _existing_keys(path, today)
    written = 0
    try:
        from app.platform import nps

        for d in nps.request_drafts(limit=limit) or []:
            slug = str(d.get("slug") or d.get("client") or "").strip()
            key = f"nps:{slug}"
            if not slug or key in seen:
                continue
            if _append(
                path,
                {
                    "date": today,
                    "dedupe_key": key,
                    "kind": "nps_survey",
                    "client": d.get("client"),
                    "slug": slug,
                    "message": d.get("message"),
                    "wa_link": d.get("wa_link"),
                    "status": "draft",
                    "created_at": _now_iso(),
                },
            ):
                seen.add(key)
                written += 1
    except Exception as e:  # pragma: no cover
        logger.warning(f"[autopilot] nps_survey_drafts failed: {e}")
    return {"ok": True, "drafts": written}


# ── 3) Stale-inquiry auto-followup nudge ──────────────────────────────────────
def stale_inquiry_nudges(max_clients: int = 25, stale_hours: int = 24) -> dict[str, Any]:
    """Jin inquiries ko abhi tak koi touch nahi mila (aur >stale_hours purani) un par
    ek follow-up nudge DRAFT banao. data/autopilot_stale.jsonl, date+phone dedupe."""
    if not _flag_on("STALE_INQUIRY_NUDGE"):
        return {"ok": True, "skipped": "flag_off"}
    path = os.path.join(_DATA_DIR, "autopilot_stale.jsonl")
    today = _today()
    seen = _existing_keys(path, today)
    written = 0
    try:
        from app.platform import speed_to_lead

        # best-effort age parser (module helper) — fail pe age-filter skip kar do.
        _to_epoch = getattr(speed_to_lead, "_to_epoch", None)
        now_ep = datetime.now(timezone.utc).timestamp()
        cutoff = stale_hours * 3600

        for c in _clients()[:max_clients]:
            cid = str(c.get("id") or "").strip()
            biz = str(c.get("business_name") or "Aapka Business").strip()
            try:
                rows = speed_to_lead.per_inquiry_for_client(cid, c, days=7)
            except Exception:
                rows = []
            for r in rows or []:
                if r.get("first_touch_seconds") is not None:
                    continue  # already touched
                phone = str(r.get("phone") or "").strip()
                if not phone:
                    continue
                # age gate (best-effort) — naye inquiries ko nudge mat karo
                if _to_epoch is not None:
                    try:
                        ep = _to_epoch(r.get("inquiry_at"))
                        if ep and (now_ep - ep) < cutoff:
                            continue
                    except Exception:
                        pass
                key = f"stale:{phone}"
                if key in seen:
                    continue
                msg = (
                    f"Namaste! 🙏 {biz} se — aapne kuch din pehle inquiry ki thi, abhi tak "
                    f"baat nahi ho paayi. Kya hum aaj aapki madad kar sakte hain? Reply kijiye, "
                    f"hum turant respond karenge."
                )
                if _append(
                    path,
                    {
                        "date": today,
                        "dedupe_key": key,
                        "kind": "stale_inquiry_nudge",
                        "client_id": cid,
                        "business_name": biz,
                        "phone": phone,
                        "source": r.get("source"),
                        "wa_link": f"https://wa.me/{phone.lstrip('+')}",
                        "message": msg,
                        "status": "draft",
                        "created_at": _now_iso(),
                    },
                ):
                    seen.add(key)
                    written += 1
    except Exception as e:  # pragma: no cover
        logger.warning(f"[autopilot] stale_inquiry_nudges failed: {e}")
    return {"ok": True, "nudges": written}


# ── 4) Daily Owner Brief auto-prepare ─────────────────────────────────────────
def owner_brief_daily(max_clients: int = 50) -> dict[str, Any]:
    """Har client ke liye roz-subah ek chhota 'aaj ka brief' auto-prepare karo
    (untouched-inquiries count + ek next-step line). data/autopilot_brief.jsonl,
    date+client dedupe (ek din ek brief). Studio owner-brief tool ka auto/scheduled
    version — customer ko bina click ke ready milta."""
    if not _flag_on("OWNER_BRIEF_DAILY"):
        return {"ok": True, "skipped": "flag_off"}
    path = os.path.join(_DATA_DIR, "autopilot_brief.jsonl")
    today = _today()
    seen = _existing_keys(path, today)
    written = 0
    try:
        from app.platform import speed_to_lead

        for c in _clients()[:max_clients]:
            cid = str(c.get("id") or "").strip()
            if not cid:
                continue
            key = f"brief:{cid}"
            if key in seen:
                continue
            biz = str(c.get("business_name") or "Aapka Business").strip()
            try:
                rows = speed_to_lead.per_inquiry_for_client(cid, c, days=2)
            except Exception:
                rows = []
            untouched = sum(1 for r in (rows or []) if r.get("first_touch_seconds") is None)
            if untouched:
                line = f"{untouched} naye inquiry abhi tak untouched — pehle inko reply karein."
            else:
                line = "Sab inquiries handled. Aaj ek naya offer-post share karke reach badhayein."
            brief = f"☀️ {biz} — Aaj ka brief: {line}"
            if _append(
                path,
                {
                    "date": today,
                    "dedupe_key": key,
                    "kind": "owner_brief",
                    "client_id": cid,
                    "business_name": biz,
                    "untouched_inquiries": untouched,
                    "brief": brief,
                    "status": "ready",
                    "created_at": _now_iso(),
                },
            ):
                seen.add(key)
                written += 1
    except Exception as e:  # pragma: no cover
        logger.warning(f"[autopilot] owner_brief_daily failed: {e}")
    return {"ok": True, "briefs": written}


# ── Orchestrator (scheduler entry) ────────────────────────────────────────────
async def run_all() -> dict[str, Any]:
    """team_scheduler se single entry. Har sub-job apne flag ke peeche; sab inert-by-default,
    never-raise. Returns per-job summary."""
    out: dict[str, Any] = {"ok": True}
    try:
        out["evergreen"] = await evergreen_recycle_all()
    except Exception as e:  # pragma: no cover
        out["evergreen"] = {"ok": False, "error": str(e)[:160]}
    for name, fn in (
        ("nps", nps_survey_drafts),
        ("stale_inquiry", stale_inquiry_nudges),
        ("owner_brief", owner_brief_daily),
    ):
        try:
            out[name] = fn()
        except Exception as e:  # pragma: no cover
            out[name] = {"ok": False, "error": str(e)[:160]}
    return out


__all__ = [
    "evergreen_recycle_all",
    "nps_survey_drafts",
    "stale_inquiry_nudges",
    "owner_brief_daily",
    "run_all",
]
