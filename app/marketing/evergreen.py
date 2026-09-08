"""
evergreen.py — content recycling so the queue NEVER dries up.
=============================================================

Best-performing purane posts ko thoda "freshen" karke dobara queue me daal dete
hain — taaki client ka content-calendar kabhi khali na rahe (GHL "evergreen
recycling" / Buffer re-queue jaisa, 100% free stack).

  recyclable_items(client_id, older_than_days, limit) -> list
    auto_content.list_queue se woh items jo posted/approved hain AUR N din se
    purane hain (re-share ke best candidates).
  recycle_for_client(client, business_name, niche) -> list
    1-2 recyclable items uthao, halka sa freshen karo (free_ai se caption
    variation, warna "Phir se yaad dila rahe hain: …" template tweak), aur naye
    DRAFTS (type "recycle") banakar queue me append karo. Kuch recycle karne
    layak nahi to no-op (empty list).

run_daily_content() me wire hota hai: kisi client ke aaj 0 naye items bane
(dedupe ne sab block kiya) to recycle_for_client fallback — queue hamesha
non-empty. Guarded optional-import; KABHI raise nahi karta.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# auto_content se queue helpers (import-safe — na mile to module no-op).
try:
    from app.marketing import auto_content  # type: ignore
except Exception:  # pragma: no cover
    auto_content = None  # type: ignore

# free_ai optional — caption variation ke liye; na ho to template tweak.
try:
    from app.voice_agent import free_ai  # type: ignore
except Exception:  # pragma: no cover
    free_ai = None  # type: ignore

# Recycle ke liye eligible statuses (jo client ko pasand aaye / chal chuke).
_RECYCLE_STATUSES = {"posted", "approved"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_days(created_at: str) -> float:
    """ISO timestamp ka age in days. Parse fail => 0 (eligible nahi)."""
    s = (created_at or "").strip()
    if not s:
        return 0.0
    try:
        # tolerate trailing 'Z'
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except Exception:
        return 0.0


def recyclable_items(
    client_id: str, older_than_days: int = 21, limit: int = 5
) -> list[dict[str, Any]]:
    """Posted/approved items jo `older_than_days` se purane hain (re-share candidates).

    Newest-eligible pehle. Recycle-output (type "recycle") ko dobara recycle
    nahi karte (loop avoid). KABHI raise nahi karta."""
    out: list[dict[str, Any]] = []
    if auto_content is None or not client_id:
        return out
    try:
        thr = max(0, int(older_than_days))
    except Exception:
        thr = 21
    try:
        lim = max(1, min(int(limit), 50))
    except Exception:
        lim = 5
    try:
        for it in auto_content.list_queue(client_id, limit=500):
            if str(it.get("status") or "").lower() not in _RECYCLE_STATUSES:
                continue
            if str(it.get("type") or "") == "recycle":
                continue  # already a recycle — don't re-recycle
            # caption-based items hi recycle layak (poster/svg re-share generic nahi).
            if not str(it.get("caption") or "").strip():
                continue
            if _age_days(str(it.get("created_at") or "")) < thr:
                continue
            out.append(it)
            if len(out) >= lim:
                break
    except Exception as e:  # pragma: no cover
        logger.debug(f"[evergreen] recyclable_items skip: {e}")
    return out


async def _freshen_caption(old_caption: str, business_name: str, niche: str) -> str:
    """Purane caption ka halka variation. free_ai-first, template tweak fallback.

    KABHI empty/raise nahi — fallback hamesha kuch deta hai."""
    base = (old_caption or "").strip()
    # Template tweak (never-empty fallback) — re-share framing.
    tweak = (
        "\U0001f501 Phir se yaad dila rahe hain:\n" + base
        if base
        else (
            f"\U0001f501 {business_name or 'Hum'} aapke liye phir hazir — aaj hi judiye! \U0001f4de"
        )
    )

    if free_ai is None or not base:
        return tweak[:600]

    try:
        system = (
            "Tu ek Indian local-business social-media assistant hai. Niche ek "
            "purana post-caption diya jayega — usi message ko FRESH, thoda alag "
            "shabdon me Hinglish (Roman script) me dobara likh, same offer/idea, "
            "2-3 chhoti lines + 1-2 emoji. Sirf naya caption de, koi commentary nahi."
        )
        user = (
            f"Business: {business_name or 'Business'} ({niche or 'general'}).\n"
            f"Purana caption:\n{base[:500]}\n\nIsko fresh dobara likho."
        )
        text, _p = await free_ai.chat(
            system,
            [{"role": "user", "content": user}],
            max_tokens=200,
            temperature=0.85,
        )
        if text and text.strip():
            return text.strip()[:600]
    except Exception as e:  # free_ai.chat khud raise nahi karta, par safety
        logger.debug(f"[evergreen] freshen LLM skip: {e}")
    return tweak[:600]


async def recycle_for_client(
    client: dict[str, Any] | None,
    business_name: str = "",
    niche: str = "",
) -> list[dict[str, Any]]:
    """1-2 purane top items ko freshen karke naye 'recycle' drafts banao + queue
    me append karo. Kuch recycle layak nahi => no-op ([]).

    `client` dict (id/business_name/niche/hashtags) ya alag args dono chalte hain.
    KABHI raise nahi karta. Returns appended items (added)."""
    appended: list[dict[str, Any]] = []
    if auto_content is None:
        return appended
    try:
        c = client if isinstance(client, dict) else {}
        cid = str(c.get("id") or "").strip()
        if not cid:
            return appended
        biz = (business_name or str(c.get("business_name") or "")).strip() or "Aapka Business"
        nch = (niche or str(c.get("niche") or "")).strip() or "general"

        cands = recyclable_items(cid, older_than_days=21, limit=2)
        if not cands:
            return appended

        today_s = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_items: list[dict[str, Any]] = []
        for src in cands:
            fresh = await _freshen_caption(str(src.get("caption") or ""), biz, nch)
            new_items.append(
                {
                    "id": uuid.uuid4().hex[:12],
                    "client_id": cid,
                    "date": today_s,
                    "type": "recycle",
                    "title": "Evergreen Re-share",
                    "caption": fresh,
                    "hashtags": list(src.get("hashtags") or []),
                    "recycled_from": str(src.get("id") or ""),
                    "status": "draft",
                    "created_at": _now(),
                }
            )

        # append (date+type dedupe — ek din ek hi recycle item).
        try:
            added = auto_content._append_items(cid, new_items)  # type: ignore[attr-defined]
        except Exception as e:  # pragma: no cover
            logger.debug(f"[evergreen] append skip: {e}")
            added = 0

        if added:
            # jitne actually-dedupe-pass hue utne hi return karo (best-effort: prefix).
            appended = new_items[:added]
            _log_isha("evergreen_recycled", f"{biz}: {added} purane post re-share queue me")
    except Exception as e:  # pragma: no cover
        logger.warning(f"[evergreen] recycle_for_client failed: {e}")
    return appended


def _log_isha(action: str, detail: str, status: str = "ok") -> None:
    """Team activity log (best-effort, import-safe)."""
    try:
        from app.platform.team import log_event

        log_event("isha", action, detail, status=status)
    except Exception:
        pass


__all__ = ["recyclable_items", "recycle_for_client"]
