"""
auto_content.py — automated per-client daily social-media content engine.
=========================================================================

Har active marketing client ke liye ROZ ka content auto-generate hota hai —
ek simple weekly plan (weekday) + nearby festival ke hisab se:

  Mon  -> tip post           (gyaan / educational)
  Tue  -> offer post         (deal / discount)
  Wed  -> poster (brand)     (1080x1080 SVG, client ke brand colors)
  Thu  -> reel idea          (short reel concept caption)
  Fri  -> festival-or-fun    (festival pe festive, warna fun engagement)
  Sat  -> product spotlight  (catalog/product highlight post)
  Sun  -> engagement question

Agar 2 din ke andar koi festival ho (festivals.upcoming) → us din EXTRA ek
festival post + festival poster bhi add hota hai.

  generate_for_client(client, day=None) -> list[dict]   (aaj ke items)
  run_daily_content()                   -> {"clients", "items"}  (sab active)
  list_queue(client_id, status, limit)  -> list[dict]   (newest first)
  mark_item(client_id, item_id, status) -> bool

Captions: post_generator.generate_post (LLM-first, template fallback).
Posters:  posters.generate_poster (brand colors client se).
Persistence: data/content_queue/<client_id>.jsonl (DEDUPE by date+type — same
din re-run pe duplicate nahi banta). Sab try/except — KABHI raise nahi, never
empty (har piece ka fallback hai). Test-monkeypatch: `_QUEUE_DIR`.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Tests isse monkeypatch karte hain (tmp dir). Hamesha is const ke through padho.
_QUEUE_DIR = os.path.join("data", "content_queue")

# --- import-safe deps (kuch missing ho to bhi engine chale, fallback se) --- #
try:
    from app.marketing import post_generator  # type: ignore
except Exception:  # pragma: no cover
    post_generator = None  # type: ignore

try:
    from app.marketing import posters  # type: ignore
except Exception:  # pragma: no cover
    posters = None  # type: ignore

try:
    from app.marketing import festivals  # type: ignore
except Exception:  # pragma: no cover
    festivals = None  # type: ignore

try:
    from app.marketing import clients_store  # type: ignore
except Exception:  # pragma: no cover
    clients_store = None  # type: ignore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(client_id: Any) -> str:
    """Path-traversal safe filename stem."""
    import re

    s = re.sub(r"[^A-Za-z0-9_-]", "_", str(client_id or "").strip())[:64]
    return s or "default"


def _queue_path(client_id: Any) -> str:
    return os.path.join(_QUEUE_DIR, _safe_id(client_id) + ".jsonl")


# Weekday → (type, theme-label, occasion-for-LLM)
_WEEKLY_PLAN = {
    0: ("post", "Tip / Gyaan", ""),  # Monday
    1: ("post", "Offer / Deal", ""),  # Tuesday
    2: ("poster", "Brand Poster", ""),  # Wednesday
    3: ("reel", "Reel Idea", ""),  # Thursday
    4: ("post", "Festival / Fun", ""),  # Friday (festival override below)
    5: ("post", "Product Spotlight", ""),  # Saturday
    6: ("post", "Engagement Question", ""),  # Sunday
}

# Per-type offer hint (caption ko thoda direct karta hai — sirf flavor).
_TYPE_OFFER_HINT = {
    "Offer / Deal": "Is hafte ka special offer",
    "Product Spotlight": "Sabse popular service/product",
}


def _brand_colors(client: dict[str, Any]) -> dict[str, str]:
    brand = (client.get("brand") or {}) if isinstance(client, dict) else {}
    return {
        "primary": str(brand.get("primary") or "").strip(),
        "accent": str(brand.get("accent") or "").strip(),
        "tagline": str(brand.get("tagline") or "").strip(),
    }


async def _make_post_item(
    client: dict[str, Any], today_s: str, item_type: str, theme: str, occasion: str = ""
) -> dict[str, Any]:
    """Caption-based item (post/reel/festival) banao — LLM-first, template fallback."""
    name = str(client.get("business_name") or "Aapka Business")
    niche = str(client.get("niche") or "general")
    offer = _TYPE_OFFER_HINT.get(theme, "")
    # Daily read-back: second-brain se is niche/theme ke past decisions/winning-angles
    # le aao (Isha roz brain consult kare, sirf coordinator/council nahi). to_thread
    # (sync vault scan) + 3s deadline + fail-open; "" jab OBSIDIAN_SYNC off.
    brain = ""
    try:
        from app.platform import obsidian_sync as _obs

        brain = await asyncio.wait_for(
            asyncio.to_thread(_obs.brain_context, f"{niche} {theme} {occasion}".strip()),
            timeout=3.0,
        )
    except Exception as e:
        logger.debug(f"[auto_content] brain_context skip: {e}")
        brain = ""
    caption, hashtags = "", []
    try:
        if post_generator is not None:
            res = await post_generator.generate_post(
                business_name=name,
                niche=niche,
                occasion=occasion,
                offer=offer,
                context=brain,
            )
            caption = str((res or {}).get("caption") or "").strip()
            hashtags = list((res or {}).get("hashtags") or [])
    except Exception as e:  # pragma: no cover - generate_post khud raise nahi karta
        logger.debug(f"[auto_content] post gen fallback ({theme}): {e}")

    if not caption:
        # Never-empty deterministic fallback.
        (occasion or theme or "aaj").strip()
        caption = (
            f"✨ {name} — {theme}!\n"
            f"{('🎊 ' + occasion) if occasion else 'Quality service, sahi daam'} — "
            "aaj hi humse judiye. 📞 Call ya WhatsApp karein!"
        )
        if not hashtags:
            hashtags = ["#LocalBusiness", "#SmallBusinessIndia", "#SupportLocal"]

    return {
        "id": uuid.uuid4().hex[:12],
        "client_id": str(client.get("id") or ""),
        "date": today_s,
        "type": item_type,
        "title": theme,
        "caption": caption,
        "hashtags": hashtags,
        "status": "draft",
        "created_at": _now(),
    }


def _make_poster_item(
    client: dict[str, Any],
    today_s: str,
    template_id: str,
    title: str,
    festival: str = "",
    offer: str = "",
) -> dict[str, Any]:
    """SVG poster item (brand colors client se). posters.generate_poster never-raise."""
    name = str(client.get("business_name") or "Aapka Business")
    phone = str(client.get("phone") or "")
    bc = _brand_colors(client)
    svg = ""
    try:
        if posters is not None:
            res = posters.generate_poster(
                template_id=template_id,
                business_name=name,
                tagline=bc.get("tagline", ""),
                offer=offer or "Special Offer — aaj hi poochhein!",
                phone=phone,
                festival=festival,
                brand_primary=bc.get("primary", ""),
                brand_accent=bc.get("accent", ""),
            )
            svg = str((res or {}).get("svg") or "")
    except Exception as e:  # pragma: no cover
        logger.debug(f"[auto_content] poster gen skip: {e}")

    return {
        "id": uuid.uuid4().hex[:12],
        "client_id": str(client.get("id") or ""),
        "date": today_s,
        "type": ("festival" if festival else "poster"),
        "title": title,
        "svg": svg,
        "status": "draft",
        "created_at": _now(),
    }


async def generate_for_client(
    client: dict[str, Any], day: date | None = None
) -> list[dict[str, Any]]:
    """Aaj (ya `day`) ke liye client ke content items banao (weekly plan +
    nearby festival). Har item: {id, client_id, date, type, title, caption?,
    hashtags?, svg?, status:"draft", created_at}. KABHI raise nahi, never empty."""
    items: list[dict[str, Any]] = []
    try:
        if not isinstance(client, dict):
            return items
        d = day or date.today()
        today_s = d.strftime("%Y-%m-%d")
        weekday = d.weekday()
        item_type, theme, occasion = _WEEKLY_PLAN.get(weekday, ("post", "Daily Post", ""))

        # --- nearby festival lookup (within 2 days) --- #
        near_fest: dict[str, Any] | None = None
        try:
            if festivals is not None:
                for f in festivals.upcoming(2) or []:
                    if 0 <= int(f.get("days_away", 99)) <= 2:
                        near_fest = f
                        break
        except Exception as e:  # pragma: no cover
            logger.debug(f"[auto_content] festival lookup skip: {e}")

        # --- main item-of-the-day --- #
        try:
            if item_type == "poster":
                items.append(
                    _make_poster_item(client, today_s, template_id="clean-pro", title=theme)
                )
            else:
                # Friday: festival ho to festive flavor de do.
                occ = occasion
                if weekday == 4 and near_fest:
                    occ = str(near_fest.get("name") or "")
                items.append(await _make_post_item(client, today_s, item_type, theme, occasion=occ))
        except Exception as e:  # pragma: no cover
            logger.debug(f"[auto_content] main item skip: {e}")

        # --- festival bonus (within 2 days) → festival post + festival poster --- #
        if near_fest:
            fest_name = str(near_fest.get("name") or "Festival")
            try:
                items.append(
                    await _make_post_item(
                        client, today_s, "festival", f"{fest_name} Greeting", occasion=fest_name
                    )
                )
            except Exception as e:  # pragma: no cover
                logger.debug(f"[auto_content] festival post skip: {e}")
            try:
                items.append(
                    _make_poster_item(
                        client,
                        today_s,
                        template_id="festival-glow",
                        title=f"{fest_name} Poster",
                        festival=fest_name,
                    )
                )
            except Exception as e:  # pragma: no cover
                logger.debug(f"[auto_content] festival poster skip: {e}")
    except Exception as e:
        logger.warning(f"[auto_content] generate_for_client failed: {e}")

    if items:
        # Funnel event (audit 2026-07-04: content-generated was metric-dark).
        # posthog capture = silent no-op without POSTHOG_API_KEY.
        try:
            from app.analytics import posthog_client as _ph

            _ph.capture(
                str(client.get("id") or ""),
                "content_generated",
                {"items": len(items), "types": [i.get("type") for i in items]},
            )
        except Exception:
            pass
    return items


def _existing_keys(client_id: str) -> set:
    """Pehle se queue me jo (date|type) hain — same-din re-run dedupe ke liye."""
    keys = set()
    try:
        for it in list_queue(client_id, limit=500):
            keys.add(f"{it.get('date')}|{it.get('type')}")
    except Exception:  # pragma: no cover
        pass
    return keys


def _append_items(client_id: str, items: list[dict[str, Any]]) -> int:
    """Items queue file me append karo (date+type DEDUPE). Added count return."""
    if not items:
        return 0
    path = _queue_path(client_id)
    seen = _existing_keys(client_id)
    added = 0
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for it in items:
                k = f"{it.get('date')}|{it.get('type')}"
                if k in seen:
                    continue
                seen.add(k)
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
                added += 1
    except Exception as e:  # pragma: no cover
        logger.warning(f"[auto_content] append failed: {e}")
    return added


async def _recycle_fallback(client: dict[str, Any]) -> int:
    """Aaj naye items 0 bane to evergreen recycling se queue bharo (best-effort).

    Optional import — evergreen module na ho to 0 (no-op). KABHI raise nahi."""
    try:
        from app.marketing import evergreen  # local import (optional dep)

        appended = await evergreen.recycle_for_client(client)
        return len(appended or [])
    except Exception as e:  # pragma: no cover
        logger.debug(f"[auto_content] recycle fallback skip: {e}")
        return 0


# Built-in "self" client — LeadGen AI apni hi social media bhi roz banata hai
# (Sumit 1-click post karke brand grow karta hai). Fixed id = idempotent seed.
_SELF_CLIENT_ID = "leadgenai-self"
# run_daily_content me LeadGen AI ka apna brand auto-seed ho (own marketing).
# Tests ise False karke pure client-loop test karte hain.
AUTO_SEED_SELF = True


def _content_priority_rank(client: dict[str, Any]) -> int:
    """Sort-key: PAYING real client = 0 (pehle process ho), LeadGen AI self /
    no-plan filler = 1 (last). Isse subah content-ready ka promise paying
    customers ko sabse jaldi milta hai. Kabhi raise nahi karta."""
    try:
        if not isinstance(client, dict):
            return 1
        cid = str(client.get("id") or "").strip()
        niche = str(client.get("niche") or "").strip().lower()
        name = str(client.get("business_name") or "").strip().lower()
        # Self-brand (LeadGen AI) = hamesha last.
        if cid == _SELF_CLIENT_ID or niche == "ai_marketing" or name == "leadgen ai":
            return 1
        # Koi bhi real plan (starter/growth/advanced/combo/voice_* etc.) = paying → pehle.
        plan = str(client.get("plan") or "").strip().lower()
        if plan and plan not in ("", "free", "none", "trial"):
            return 0
        # Plan-less real client = self ke baad, par test-friendly stable.
        return 1
    except Exception:  # pragma: no cover
        return 1


def _ensure_self_client() -> str | None:
    """LeadGen AI ka apna marketing-client record ensure karo (idempotent by id).

    Agar clients_store me koi ai_marketing / "LeadGen AI" client nahi hai to
    fixed-id "leadgenai-self" wala seed karo — taaki hamara OWN brand bhi daily
    content queue me aaye. Returns self client id (ya None on failure). KABHI
    raise nahi karta."""
    try:
        if clients_store is None:
            return None
        # Pehle se hai? (fixed id, ya ai_marketing niche, ya naam "LeadGen AI")
        for c in clients_store.list_clients():
            cid = str(c.get("id") or "")
            niche = str(c.get("niche") or "").strip().lower()
            name = str(c.get("business_name") or "").strip().lower()
            if cid == _SELF_CLIENT_ID or niche == "ai_marketing" or name == "leadgen ai":
                return cid or _SELF_CLIENT_ID
        # Seed once. add_client uuid deta hai, isliye direct-append se fixed id.
        rec = {
            "id": _SELF_CLIENT_ID,
            "business_name": "LeadGen AI",
            "niche": "ai_marketing",
            "city": "",
            "phone": "",
            "plan": "growth",
            "status": "active",
            "brand": {
                "primary": "#6d28d9",
                "accent": "",
                "tagline": "AI Marketing + Voice Agent",
                "logo_text": "LeadGen AI",
            },
            "socials": {"instagram": "", "facebook": "", "gbp": ""},
            "created_at": _now(),
        }
        try:
            clients_store._append(rec)  # type: ignore[attr-defined]
        except Exception:
            # Fallback: public API (uuid id banega, par phir bhi self-content milega).
            try:
                created = clients_store.add_client(
                    business_name="LeadGen AI",
                    niche="ai_marketing",
                    plan="growth",
                    brand={
                        "primary": "#6d28d9",
                        "tagline": "AI Marketing + Voice Agent",
                        "logo_text": "LeadGen AI",
                    },
                )
                return str((created or {}).get("id") or "") or None
            except Exception:
                return None
        # brand_kit me bhi mirror (poster auto-brand) — best-effort.
        try:
            from app.marketing import brand_kit

            brand_kit.save_brand(
                _SELF_CLIENT_ID,
                {
                    "business_name": "LeadGen AI",
                    "tagline": "AI Marketing + Voice Agent",
                    "colors": {"primary": "#6d28d9", "accent": ""},
                    "logo_text": "LeadGen AI",
                },
            )
        except Exception:
            pass
        return _SELF_CLIENT_ID
    except Exception as e:  # pragma: no cover
        logger.debug(f"[auto_content] self-client seed skip: {e}")
        return None


async def run_daily_content() -> dict[str, Any]:
    """Sab active clients ke liye aaj ka content generate + queue me append
    (date+type dedupe). isha event log. Returns {"clients", "items"}. KABHI
    raise nahi karta. Pehle apna OWN brand (LeadGen AI) bhi ensure karta hai
    taaki hum khud ki marketing bhi roz karein."""
    n_clients = 0
    total_items = 0
    self_id = None
    try:
        if clients_store is None:
            return {"clients": 0, "items": 0}

        # LeadGen AI khud ka brand bhi roz post kare (idempotent seed).
        # AUTO_SEED_SELF flag se tests pure-loop test kar sakte hain.
        if AUTO_SEED_SELF:
            self_id = _ensure_self_client()

        active = clients_store.list_clients("active")
        # PAYING clients pehle (subah content ready ka promise customers ko sabse
        # jaldi mile), LeadGen AI apna self-brand sabse LAST. Stable sort:
        # rank 0 = paying real client, rank 1 = self / no-plan filler.
        active = sorted(active, key=lambda c: _content_priority_rank(c))
        for client in active:
            cid = str(client.get("id") or "")
            if not cid:
                continue
            try:
                items = await generate_for_client(client)
                added = _append_items(cid, items)
                if added and os.environ.get("CONTENT_APPROVAL_AUTO", "0").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                ):
                    try:
                        from app.marketing import content_approval

                        for it in items[:5]:
                            content_approval.submit(cid, it)
                    except Exception as e:
                        logger.debug(f"[auto_content] approval auto-submit skip: {e}")
                if not added:
                    # Aaj ke sab items dedupe ne block kiye (queue dry-ish) —
                    # evergreen recycling se purana top content re-share karo.
                    added = await _recycle_fallback(client)
                if added:
                    n_clients += 1
                    total_items += added
                    if self_id and cid == self_id:
                        _log_isha(
                            "self_brand_content", f"LeadGen AI ka apna {added} content items banaye"
                        )
            except Exception as e:  # pragma: no cover
                logger.debug(f"[auto_content] client {cid} skip: {e}")

        _log_isha("auto_content", f"{n_clients} clients, {total_items} items generated")
        # P1 #12 (2026-07-05): weekly value digest to delivered paid customers —
        # backs the "har hafte naya content milega" promise. Self-throttling
        # (once/6days per customer) + gated AUTO_DELIVER_VALUE, so daily call is safe.
        try:
            from app.marketing import customer_delivery

            await customer_delivery.run_weekly_digest_sweep()
            # P2 (2026-07-05): monthly ROI receipt (28-day) + testimonial ask (gated
            # AUTO_TESTIMONIAL) — dono self-throttling, daily call safe.
            await customer_delivery.run_monthly_receipt_sweep()
            await customer_delivery.run_testimonial_sweep()
        except Exception as e:
            logger.debug(f"[auto_content] delivery growth sweeps skip: {e}")
    except Exception as e:
        logger.warning(f"[auto_content] run_daily_content failed: {e}")
        _log_isha("auto_content", f"auto-content crash: {e}", status="error")
    return {"clients": n_clients, "items": total_items}


async def seed_client_content(client: dict[str, Any]) -> int:
    """EK client ka aaj ka content ABHI generate + queue me append (onboarding pe
    instant day-1 value — daily 07:00 sweep ka wait nahi). Same generate→append→
    recycle pattern as run_daily_content; date+type DEDUPE = daily job ke saath
    idempotent (double content nahi banega). Added-count return. KABHI raise nahi."""
    try:
        if not isinstance(client, dict):
            return 0
        cid = str(client.get("id") or "")
        if not cid:
            return 0
        items = await generate_for_client(client)
        added = _append_items(cid, items)
        if not added:
            added = await _recycle_fallback(client)
        if added:
            try:
                from app.marketing import delivery_ledger

                delivery_ledger.log_event(cid, "marketing_calendar_generated")
                delivery_ledger.log_event(
                    cid, "post_draft_created", detail=f"{added} drafts", meta={"count": added}
                )
            except Exception as le:  # pragma: no cover
                logger.debug(f"[auto_content] ledger log skip: {le}")
        return added
    except Exception as e:  # pragma: no cover
        logger.debug(f"[auto_content] seed_client_content skip: {e}")
        return 0


def list_queue(client_id: str, status: str | None = None, limit: int = 60) -> list[dict[str, Any]]:
    """Client ka content queue (newest first, optional status filter). Kabhi
    raise nahi karta."""
    rows: list[dict[str, Any]] = []
    path = _queue_path(client_id)
    try:
        if not os.path.isfile(path):
            return rows
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict) and rec.get("id"):
                        rows.append(rec)
                except Exception:
                    continue
    except Exception as e:  # pragma: no cover
        logger.warning(f"[auto_content] list_queue failed: {e}")
        return []

    if status:
        st = status.strip().lower()
        rows = [r for r in rows if str(r.get("status") or "").lower() == st]
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    try:
        limit = max(1, min(int(limit), 500))
    except Exception:
        limit = 60
    return rows[:limit]


_VALID_STATUS = {"draft", "approved", "posted", "skipped"}


def enqueue_approved(client_id: str, content: dict[str, Any], approval_id: str = "") -> bool:
    """Client ne approve kiya content → queue me status=approved (publish-ready)."""
    try:
        client_id = str(client_id or "").strip()
        if not client_id or not isinstance(content, dict):
            return False
        today_s = date.today().strftime("%Y-%m-%d")
        item = {
            "id": str(approval_id or uuid.uuid4().hex[:12])[:16],
            "client_id": client_id,
            "date": today_s,
            "type": str(content.get("kind") or content.get("type") or "branded")[:40],
            "title": str(content.get("title") or content.get("occasion") or "Approved post")[:120],
            "caption": str(content.get("caption") or content.get("text") or "")[:2000],
            "hashtags": content.get("hashtags") or [],
            "svg": content.get("svg") or "",
            "status": "approved",
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "approval_id": approval_id or "",
        }
        added = _append_items(client_id, [item]) > 0
        # H5: approved content → social_engine publish queue (GATED SOCIAL_ENGINE).
        # Text-only bridge: caption posted to configured channels (Telegram/Postiz).
        # Media URL skipped — visual posts (SVG/video) get separate video_ad_cycle path.
        if added and os.environ.get("SOCIAL_ENGINE", "0").strip().lower() in ("1", "true", "yes"):
            try:
                from app.social_engine import engine as _se

                if _se.enabled():
                    caption_text = item.get("caption") or item.get("title") or ""
                    if caption_text:
                        hashtags = " ".join(f"#{h.lstrip('#')}" for h in (item.get("hashtags") or [])[:5])
                        full_caption = f"{caption_text}\n\n{hashtags}".strip()
                        _se.enqueue_publish(client_id, caption=full_caption, media_type="image")
            except Exception as _e:
                logger.debug(f"[auto_content] social_engine bridge skip: {_e}")
        return added
    except Exception as e:
        logger.debug(f"[auto_content] enqueue_approved skip: {e}")
        return False


def mark_item(client_id: str, item_id: str, status: str) -> bool:
    """Queue item ka status badlo (draft→approved→posted, ya skipped). True
    agar update hua. Kabhi raise nahi karta."""
    st = (status or "").strip().lower()
    if st not in _VALID_STATUS:
        return False
    path = _queue_path(client_id)
    try:
        if not os.path.isfile(path):
            return False
        rows: list[dict[str, Any]] = []
        found = False
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict) and str(rec.get("id")) == str(item_id):
                    rec["status"] = st
                    rec["updated_at"] = _now()
                    found = True
                rows.append(rec)
        if not found:
            return False
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
        return True
    except Exception as e:  # pragma: no cover
        logger.warning(f"[auto_content] mark_item failed: {e}")
        return False


def _log_isha(action: str, detail: str, status: str = "ok") -> None:
    """Team activity log (best-effort, import-safe)."""
    try:
        from app.platform.team import log_event

        log_event("isha", action, detail, status=status)
    except Exception:
        pass


__all__ = [
    "generate_for_client",
    "seed_client_content",
    "run_daily_content",
    "list_queue",
    "mark_item",
]
