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
empty (har piece ka fallback hai). Test-monkeypatch: `_QUEUE_DIR` (call-time
resolver — return a tmp dir string).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _QUEUE_DIR() -> str:
    """Per-tenant content queue directory — resolved per call, never frozen at import."""
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="content.queue",
            legacy_path=Path("data") / "content_queue",
            target_segments=("content", "queue"),
        )
    )


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
    return os.path.join(_QUEUE_DIR(), _safe_id(client_id) + ".jsonl")


def _social_prefs(client_id: str) -> dict[str, Any]:
    """Configured Social Setup Wizard prefs. Kill-switch: SOCIAL_PREFS_HONOR=0.

    Empty dict means preserve old daily content behavior. Never raises.
    """
    try:
        if os.environ.get("SOCIAL_PREFS_HONOR", "0").strip().lower() not in ("1", "true", "yes"):
            return {}
        from app.social_engine import client_config

        cfg = client_config.get(str(client_id or ""))
        return cfg if cfg.get("configured") else {}
    except Exception as e:  # pragma: no cover
        logger.debug(f"[auto_content] social prefs skip: {e}")
        return {}


def _cadence_due(cadence: str, d: date) -> bool:
    """Whether content should be generated on date d for a saved cadence."""
    c = str(cadence or "").strip().lower()
    if c == "off":
        return False
    if c == "weekly":
        return d.weekday() == 0
    if c == "3x_week":
        return d.weekday() in (0, 2, 4)
    return True


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
    phone = _safe_client_phone(client)
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


_PLACEHOLDER_PHONE_TAILS = frozenset(
    {
        "9876543210",  # common demo/fixture — never print on customer creatives
        "1234567890",
        "0000000000",
        "1111111111",
    }
)


def _safe_client_phone(client: dict[str, Any]) -> str:
    """Real customer phone only — refuse known placeholder/fixture numbers.

    Empty string → posters.py falls back to 'Call / WhatsApp karein' (not a fake number).
    """
    raw = str(client.get("phone") or client.get("whatsapp_phone") or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    tail = digits[-10:] if len(digits) >= 10 else digits
    if not tail or tail in _PLACEHOLDER_PHONE_TAILS:
        return ""
    return raw


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

        # --- nearby festival lookup (relative to target `d`, not always "today") --- #
        near_fest: dict[str, Any] | None = None
        try:
            if festivals is not None:
                for f in festivals.upcoming(45) or []:
                    fd = None
                    try:
                        from datetime import datetime as _dt

                        fd = _dt.strptime(str(f.get("date") or ""), "%Y-%m-%d").date()
                    except Exception:
                        fd = None
                    if fd is None:
                        continue
                    delta = (fd - d).days
                    if 0 <= delta <= 2:
                        near_fest = dict(f)
                        near_fest["days_away"] = delta
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
        try:
            channels = _social_prefs(str(client.get("id") or "")).get("channels") or []
            if channels:
                for item in items:
                    item["channels"] = list(channels)
        except Exception as e:  # pragma: no cover
            logger.debug(f"[auto_content] channel stamp skip: {e}")
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


_CAPTION_MIN_LEN = 10
_CAPTION_MAX_LEN = 2200  # Instagram caption hard limit


def _caption_ok(item: dict[str, Any]) -> tuple[bool, str]:
    """W2.1: content draft-queue me jaane se pehle caption validate — banned-phrase
    (staff.BANNED reuse) ya bad-length wale items queue me na aayein. Poster/SVG items
    (no caption) always ok. Fail-open (validate error = allow) — content flow never break."""
    try:
        cap = str(item.get("caption") or "").strip()
        if not cap:
            return True, ""  # poster/svg — koi caption nahi, validate karne ko kuch nahi
        n = len(cap)
        if n < _CAPTION_MIN_LEN:
            return False, f"caption too short ({n} chars)"
        if n > _CAPTION_MAX_LEN:
            return False, f"caption too long ({n} chars)"
        low = cap.lower()
        try:
            from app.agents.staff import BANNED  # lazy — circular import avoid
        except Exception:
            BANNED = []
        for b in BANNED:
            if b and str(b).lower() in low:
                return False, f"banned phrase '{b}'"
        return True, ""
    except Exception:
        return True, ""


def _append_items(client_id: str, items: list[dict[str, Any]]) -> int:
    """Items queue file me append karo (date+type DEDUPE). Added count return."""
    n, _added = _append_items_detailed(client_id, items)
    return n


def _append_items_detailed(
    client_id: str, items: list[dict[str, Any]]
) -> tuple[int, list[dict[str, Any]]]:
    """Like `_append_items` but also returns the rows that were actually written.

    Approval auto-submit must use this list — submitting the full generate()
    output re-enqueues already-queued seed items (Jiya: 12 queue / 24 pending).
    """
    if not items:
        return 0, []
    seen = _existing_keys(client_id)
    added_rows: list[dict[str, Any]] = []
    try:
        # Probe then re-resolve at each I/O site — never bind the resolver
        # result to a local name (scanner allowlist binds on the expression).
        _QUEUE_DIR()
        os.makedirs(os.path.dirname(_queue_path(client_id)) or ".", exist_ok=True)
        with open(_queue_path(client_id), "a", encoding="utf-8") as f:
            for it in items:
                k = f"{it.get('date')}|{it.get('type')}"
                if k in seen:
                    continue
                _ok, _why = _caption_ok(it)  # W2.1: output-validation gate
                if not _ok:
                    logger.warning(f"[auto_content] content rejected (not queued): {_why}")
                    continue
                seen.add(k)
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
                added_rows.append(it)
    except Exception as e:  # pragma: no cover
        from app.platform import runtime_data as _rd

        if isinstance(e, _rd.RuntimeDataError):
            logger.error("[auto_content] content.queue authority UNRESOLVABLE: %s", e)
        else:
            logger.warning(f"[auto_content] append failed: {e}")
    return len(added_rows), added_rows


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
            # Owner OS V1.1: cooperative abort between clients (drain/stop_claims /
            # request_cancel_running). Never force mid-client; never raise.
            try:
                from app.platform import owner_agent_execution as _oae

                if _oae.agent_abort_requested("isha"):
                    logger.info(
                        "[auto_content] cooperative agent abort — stopping between clients "
                        "(clients_done=%s items=%s)",
                        n_clients,
                        total_items,
                    )
                    return {
                        "clients": n_clients,
                        "items": total_items,
                        "stopped": True,
                        "reason": "agent_abort",
                    }
            except Exception:
                pass
            cid = str(client.get("id") or "")
            if not cid:
                continue
            prefs = _social_prefs(cid)
            if prefs and not _cadence_due(str(prefs.get("cadence") or ""), date.today()):
                logger.debug(f"[auto_content] {cid} skip today (cadence={prefs.get('cadence')})")
                continue
            try:
                items = await generate_for_client(client)
                added, added_items = _append_items_detailed(cid, items)
                # Own-brand OR customer explicit approval_mode=auto (prefs honored):
                # skip human backlog — mark approved + enqueue when engine on.
                mode = str(prefs.get("approval_mode") or "").strip().lower()
                hands_free = bool(
                    added and added_items and (cid == _SELF_CLIENT_ID or mode == "auto")
                )
                if hands_free:
                    try:
                        from app.social_engine import engine as _se

                        for it in added_items[:5]:
                            mark_item(cid, str(it.get("id") or ""), "approved")
                            if _se.enabled():
                                caption_text = str(it.get("caption") or it.get("title") or "")
                                if caption_text:
                                    hashtags = " ".join(
                                        f"#{h.lstrip('#')}" for h in (it.get("hashtags") or [])[:5]
                                    )
                                    full_caption = f"{caption_text}\n\n{hashtags}".strip()
                                    _se.enqueue_publish(
                                        cid, caption=full_caption, media_type="image"
                                    )
                    except Exception as e:
                        logger.debug(f"[auto_content] hands-free publish bridge skip: {e}")
                elif added and added_items and mode not in ("draft", "auto"):
                    # review (prefs) OR CONTENT_APPROVAL_AUTO — never draft/auto here.
                    should_submit = (
                        os.environ.get("CONTENT_APPROVAL_AUTO", "0").strip().lower()
                        in ("1", "true", "yes")
                        or mode == "review"
                    )
                    if should_submit:
                        try:
                            from app.marketing import content_approval

                            for it in added_items[:5]:
                                content_approval.submit(cid, it)
                        except Exception as e:
                            logger.debug(f"[auto_content] approval auto-submit skip: {e}")
                if not added:
                    # Aaj ke sab items dedupe ne block kiye (queue dry-ish) —
                    # evergreen recycling se purana top content re-share karo.
                    added = await _recycle_fallback(client)
                    added_items = []
                if added:
                    n_clients += 1
                    total_items += added
                    # Per-customer automation-log row (ADR-065 deeper logs): attribute
                    # today's content generation to THIS client so the admin Automation
                    # Runs "customer" filter works. Never break the loop.
                    try:
                        from app.platform.automation_log_service import log_event as _log_auto

                        _log_auto(
                            client_id=cid,
                            job_type="content",
                            status="success",
                            output_summary="%d content items generated" % int(added),
                            triggered_by="scheduler",
                        )
                    except Exception:
                        pass
                    if self_id and cid == self_id:
                        _log_isha(
                            "self_brand_content", f"LeadGen AI ka apna {added} content items banaye"
                        )
            except Exception as e:  # pragma: no cover
                logger.debug(f"[auto_content] client {cid} skip: {e}")
                try:
                    from app.platform.automation_log_service import log_event as _log_auto

                    _log_auto(
                        client_id=cid,
                        job_type="content",
                        status="failed",
                        error_message=str(e)[:500],
                        triggered_by="scheduler",
                    )
                except Exception:
                    pass

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
    """EK client ka Day-1 Value Delivery Packet generate + queue me append
    (AAJ ka content + 1 WhatsApp promo + 1 local campaign suggestion),
    aur naye items ko content_approval queue me submit karta hai.

    Forward calendar days daily `run_daily_content` bharegi — 7-din pre-fill
    date|type dedupe se roz-job ko block karti thi (audit 2026-07-17 / Jiya).
    KABHI raise nahi karta."""
    try:
        if not isinstance(client, dict):
            return 0
        cid = str(client.get("id") or "")
        if not cid:
            return 0

        import uuid
        from datetime import date

        from app.marketing import content_approval, delivery_ledger
        from app.marketing.whatsapp_pack import broadcast_pack

        try:
            from app.voice_agent import free_ai
        except Exception:
            free_ai = None

        # 1. Generate TODAY only (forward days = daily scheduler)
        all_items = []
        day_items = await generate_for_client(client, day=date.today())
        if day_items:
            all_items.extend(day_items)

        # 2. Generate 1 WhatsApp promo message
        try:
            pack = await broadcast_pack(
                business_name=client.get("business_name") or "Aapka Business",
                niche=client.get("niche") or "general",
                offer=client.get("services") or "",
            )
            broadcast_msg = pack["broadcast"][0] if pack.get("broadcast") else ""
        except Exception as we:
            logger.debug(f"[auto_content] WhatsApp pack generation skip: {we}")
            broadcast_msg = ""

        if not broadcast_msg:
            biz_name = client.get("business_name") or "Aapka Business"
            services = client.get("services") or "Special Offer"
            broadcast_msg = f"Namaste! 🎉 *{biz_name}* laya hai aapke liye special services: {services}. Abhi reply karein aur exciting details payein! 📞"

        whatsapp_item = {
            "id": uuid.uuid4().hex[:12],
            "client_id": cid,
            "date": date.today().strftime("%Y-%m-%d"),
            "type": "whatsapp",
            "title": "WhatsApp Promo Message",
            "caption": broadcast_msg,
            "hashtags": [],
            "status": "draft",
            "created_at": _now(),
        }
        all_items.append(whatsapp_item)

        # 3. Generate 1 Local Campaign Suggestion
        campaign_suggestion = ""
        if free_ai is not None:
            try:
                sys_prompt = (
                    "Tu local business growth expert hai. Small businesses ke liye unique, "
                    "actionable marketing campaigns suggest karta hai. Ek specific local campaign suggestion de "
                    "(like refer-a-friend, festival discount, local partnership). Hinglish me likh, "
                    "concise, 2-3 lines max. Format: Title: <title>\\nSuggestion: <details>"
                )
                usr_prompt = (
                    f"Business: {client.get('business_name')}\n"
                    f"Niche: {client.get('niche')}\n"
                    f"City: {client.get('city')}\n"
                    f"Services: {client.get('services') or 'services'}\n"
                    f"IMPORTANT: Campaign MUST be for city '{client.get('city') or 'local area'}' only — "
                    f"kisi aur sheher (Mumbai/Delhi/etc.) ka zikr mat karo."
                )
                text, _ = await free_ai.chat(
                    sys_prompt,
                    [{"role": "user", "content": usr_prompt}],
                    max_tokens=200,
                    temperature=0.7,
                )
                campaign_suggestion = text.strip()
            except Exception as ce:
                logger.debug(f"[auto_content] campaign generation fail: {ce}")

        if not campaign_suggestion:
            city = str(client.get("city") or "local area").strip() or "local area"
            campaign_suggestion = (
                f"Title: Refer a Friend Campaign ({city})\n"
                f"Suggestion: {city} ke existing customers ko WhatsApp par message bhejein: "
                "'Apne kisi friend ko humare yahan refer karein, aur aap dono ko milega 20% off next service par!' "
                "Isse local area me word-of-mouth marketing badhegi."
            )

        campaign_item = {
            "id": uuid.uuid4().hex[:12],
            "client_id": cid,
            "date": date.today().strftime("%Y-%m-%d"),
            "type": "campaign",
            "title": "Local Offer Campaign Suggestion",
            "caption": campaign_suggestion,
            "hashtags": [],
            "status": "draft",
            "created_at": _now(),
        }
        all_items.append(campaign_item)

        # 4. Append to content queue (idempotent via date+type dedupe)
        added, added_items = _append_items_detailed(cid, all_items)
        if not added:
            # Fallback recycle
            added = await _recycle_fallback(client)
            added_items = []

        # 5. Automatically submit ONLY newly added items to the approvals queue
        if added_items:
            try:
                for it in added_items:
                    content_approval.submit(cid, it)
            except Exception as ae:
                logger.debug(f"[auto_content] Day-1 approvals submission fail: {ae}")

        # 6. Log to delivery ledger
        if added:
            try:
                delivery_ledger.log_event(cid, "marketing_calendar_generated")
                delivery_ledger.log_event(
                    cid,
                    "post_draft_created",
                    detail=f"{added} drafts/suggestions setup kiya",
                    meta={"count": added},
                )
            except Exception as le:  # pragma: no cover
                logger.debug(f"[auto_content] ledger log skip: {le}")
            try:
                from app.marketing import product_one_delivery

                product_one_delivery.sync_customer_deliverable_status(
                    cid,
                    "social_posts",
                    "pending_approval",
                    evidence_payload={"generated_count": added},
                    note=f"{added} drafts/suggestions setup kiya",
                    owner="AI",
                )
                product_one_delivery.sync_customer_deliverable_status(
                    cid,
                    "branded_posters",
                    "pending_approval",
                    evidence_payload={"generated_count": added},
                    note="Creative drafts generated with the monthly content pack.",
                    owner="AI",
                )
            except Exception as de:  # pragma: no cover
                logger.debug(f"[auto_content] deliverable db sync skip: {de}")

        # 7. Monthly deliverables the daily/post pipeline doesn't cover: GBP
        # suggestions + review-reply drafts. Self-guarding (skip if already
        # present this cycle). Without these two, the gbp_suggestions /
        # review_replies deliverables never flipped to "done" (audit 2026-07-19,
        # Jiya stuck at 60% — plan promises both).
        try:
            added += await generate_gbp_pack(client)
        except Exception as ge:  # pragma: no cover
            logger.debug(f"[auto_content] gbp pack skip: {ge}")
        try:
            added += await generate_review_reply_pack(client)
        except Exception as rre:  # pragma: no cover
            logger.debug(f"[auto_content] review pack skip: {rre}")
        try:
            added += await generate_poster_pack(client)
        except Exception as pe:  # pragma: no cover
            logger.debug(f"[auto_content] poster pack skip: {pe}")

        return added
    except Exception as e:  # pragma: no cover
        logger.debug(f"[auto_content] seed_client_content skip: {e}")
        return 0


def _gbp_suggestions_caption(client: dict[str, Any]) -> str:
    """Ek rich GBP-suggestions draft (top prioritised profile fixes) — heuristic
    audit se, curated deterministic fallback ke saath. KABHI empty nahi."""
    biz = str((client or {}).get("business_name") or "Aapka Business").strip()
    lines: list[str] = []
    try:
        from app.marketing import gbp_audit

        sug = gbp_audit.heuristic_suggest(client)
        scored = gbp_audit.score_audit((sug or {}).get("answers") or {})
        for f in (scored.get("top_fixes") or [])[:5]:
            fix = (
                str(f.get("fix") or f.get("action") or f.get("text") or "").strip()
                if isinstance(f, dict)
                else str(f or "").strip()
            )
            if fix:
                lines.append(f"• {fix}")
        if not lines:
            for area in ("posts", "photos", "reviews_count", "review_replies", "qna"):
                fix = (getattr(gbp_audit, "_FIXES", {}) or {}).get(area)
                if fix:
                    lines.append(f"• {fix}")
    except Exception:
        lines = []
    if not lines:
        lines = [
            "• Har Somvaar ek GBP post daalo (offer/update + photo) — freshness signal.",
            "• Is hafte 5 naye photos add karo (kaam, team, before/after).",
            "• Har khush customer se turant Google review maango (counter par QR).",
            "• Sab reviews ka 24-ghante me reply karo (negative pehle).",
        ]
    head = f"Google Business Profile — is mahine ke top sudhaar ({biz}):"
    return (head + "\n" + "\n".join(lines))[:2100]


async def generate_gbp_pack(client: dict[str, Any]) -> int:
    """GBP suggestions deliverable ko REAL banata hai: ek `gbp` content item
    (prioritised profile fixes) queue me + approval submit + ledger + deliverable
    sync. Self-guarding — client ke queue me pehle se koi gbp item ho to skip
    (monthly deliverable, roz regenerate nahi). KABHI raise nahi karta."""
    try:
        if not isinstance(client, dict):
            return 0
        cid = str(client.get("id") or "").strip()
        if not cid:
            return 0
        for it in list_queue(cid, limit=500):
            if str(it.get("type") or "").lower() in ("gbp", "gbp_post"):
                return 0  # already delivered this cycle

        import uuid
        from datetime import date

        from app.marketing import content_approval, delivery_ledger

        item = {
            "id": uuid.uuid4().hex[:12],
            "client_id": cid,
            "date": date.today().strftime("%Y-%m-%d"),
            "type": "gbp",
            "title": "Google Business Profile — Suggestions",
            "caption": _gbp_suggestions_caption(client),
            "hashtags": [],
            "status": "draft",
            "created_at": _now(),
        }
        added, added_items = _append_items_detailed(cid, [item])
        if added_items:
            try:
                for it in added_items:
                    content_approval.submit(cid, it)
            except Exception as ae:  # pragma: no cover
                logger.debug(f"[auto_content] gbp approval submit skip: {ae}")
            try:
                delivery_ledger.log_event(
                    cid,
                    "gbp_suggestions_generated",
                    detail="GBP profile suggestions draft ready",
                )
            except Exception:  # pragma: no cover
                pass
            try:
                from app.marketing import product_one_delivery

                product_one_delivery.sync_customer_deliverable_status(
                    cid,
                    "gbp_suggestions",
                    "pending_approval",
                    note="GBP suggestions draft generated.",
                    owner="AI",
                )
            except Exception as de:  # pragma: no cover
                logger.debug(f"[auto_content] gbp deliverable sync skip: {de}")
        return added
    except Exception as e:  # pragma: no cover
        logger.debug(f"[auto_content] generate_gbp_pack skip: {e}")
        return 0


async def _review_reply_caption(client: dict[str, Any]) -> str:
    """3 review-reply drafts (5-star / mixed / negative) — free-AI first,
    deterministic Hinglish fallback. KABHI empty nahi."""
    biz = str((client or {}).get("business_name") or "Aapka Business").strip()
    niche = str((client or {}).get("niche") or "business").strip()
    out: list[str] = []
    try:
        from app.voice_agent import free_ai  # optional
    except Exception:
        free_ai = None  # type: ignore
    if free_ai is not None:
        try:
            sys_prompt = (
                "Tu local business owner ka assistant hai jo Google review ke professional, warm "
                "Hinglish REPLY drafts likhta hai. Business ka naam use kar. TEEN reply de, har 2-3 "
                "line. Format EXACT:\nSTAR5: <reply>\nMIXED: <reply>\nNEG: <reply>"
            )
            usr_prompt = (
                f"Business: {biz}\nNiche: {niche}\nCity: {(client or {}).get('city') or ''}"
            )
            text, _ = await free_ai.chat(
                sys_prompt,
                [{"role": "user", "content": usr_prompt}],
                max_tokens=400,
                temperature=0.6,
            )
            import re as _re

            for tag, label in (
                ("STAR5", "5-star khush review"),
                ("MIXED", "Mixed / minor complaint"),
                ("NEG", "Naaraz customer"),
            ):
                m = _re.search(rf"(?im)^{tag}\s*:\s*(.+)$", text or "")
                if m and m.group(1).strip():
                    out.append(f"[{label}]\n{m.group(1).strip()}")
        except Exception:
            out = []
    if not out:
        out = [
            f"[5-star khush review]\nBahut bahut shukriya! 🙏 {biz} par aapko accha laga jaan kar "
            "dil khush ho gaya. Aise hi pyaar banaye rakhein — jald phir milte hain!",
            f"[Mixed / minor complaint]\nAapke feedback ke liye dhanyavaad. {biz} me hum har baar "
            "behtar karne ki koshish karte hain — aapki baat note kar li, agli visit aur acchi hogi. 🙏",
            f"[Naaraz customer]\nHumein khed hai ki experience accha nahi raha. {biz} ki taraf se "
            "maafi — please humein call/DM karein taaki hum turant sahi kar sakein. Aapki santushti zaroori hai.",
        ]
    return ("Review reply drafts (copy-paste ready):\n\n" + "\n\n".join(out))[:2100]


async def generate_review_reply_pack(client: dict[str, Any]) -> int:
    """review_replies deliverable ko REAL banata hai: ek `review_reply` content
    item (3 reply drafts) queue me + approval + ledger + deliverable sync.
    Self-guarding. KABHI raise nahi karta."""
    try:
        if not isinstance(client, dict):
            return 0
        cid = str(client.get("id") or "").strip()
        if not cid:
            return 0
        for it in list_queue(cid, limit=500):
            if str(it.get("type") or "").lower() == "review_reply":
                return 0

        import uuid
        from datetime import date

        from app.marketing import content_approval, delivery_ledger

        item = {
            "id": uuid.uuid4().hex[:12],
            "client_id": cid,
            "date": date.today().strftime("%Y-%m-%d"),
            "type": "review_reply",
            "title": "Review Reply Drafts",
            "caption": await _review_reply_caption(client),
            "hashtags": [],
            "status": "draft",
            "created_at": _now(),
        }
        added, added_items = _append_items_detailed(cid, [item])
        if added_items:
            try:
                for it in added_items:
                    content_approval.submit(cid, it)
            except Exception as ae:  # pragma: no cover
                logger.debug(f"[auto_content] review approval submit skip: {ae}")
            try:
                delivery_ledger.log_event(
                    cid,
                    "review_replies_generated",
                    detail="Review reply drafts ready",
                )
            except Exception:  # pragma: no cover
                pass
            try:
                from app.marketing import product_one_delivery

                product_one_delivery.sync_customer_deliverable_status(
                    cid,
                    "review_replies",
                    "pending_approval",
                    note="Review reply drafts generated.",
                    owner="AI",
                )
            except Exception as de:  # pragma: no cover
                logger.debug(f"[auto_content] review deliverable sync skip: {de}")
        return added
    except Exception as e:  # pragma: no cover
        logger.debug(f"[auto_content] generate_review_reply_pack skip: {e}")
        return 0


async def generate_poster_pack(client: dict[str, Any], target: int = 4) -> int:
    """branded_posters deliverable ko REAL banata hai: queue me kam-se-kam
    `target` (default 4) real branded SVG posters ensure karta hai. Existing
    posters count karke sirf kami (target - existing) generate karta hai
    (self-guarding, idempotent). Har naya poster distinct date pe (date|type
    dedup bachne ke liye), sirf non-empty SVG wale count hote (empty = skip,
    koi fake poster nahi). KABHI raise nahi karta."""
    try:
        if not isinstance(client, dict):
            return 0
        cid = str(client.get("id") or "").strip()
        if not cid:
            return 0
        existing = [
            it for it in list_queue(cid, limit=500) if str(it.get("type") or "").lower() == "poster"
        ]
        need = max(0, int(target) - len(existing))
        if need <= 0:
            return 0

        from datetime import date, timedelta

        from app.marketing import content_approval, delivery_ledger

        # Varied real templates + niche-aware Hinglish offers (generate_poster
        # unknown id => clean-pro fallback, kabhi empty nahi).
        combos = [
            ("offer-burst", "Is hafte ka special offer — abhi book karein!"),
            ("generic-sale", "Seasonal glow package — limited slots!"),
            ("clean-pro", "Naya look, naya confidence — aaj hi aayein."),
            ("offer-burst", "Bridal & party makeup — advance booking khuli hai!"),
        ]
        used_dates = {str(it.get("date")) for it in existing}
        items: list[dict[str, Any]] = []
        base = date.today()
        offset = 0
        made = 0
        while made < need and offset < 60:
            d = (base + timedelta(days=offset)).strftime("%Y-%m-%d")
            offset += 1
            if d in used_dates:
                continue  # date|type poster dedup bachao
            tpl, offer = combos[made % len(combos)]
            item = _make_poster_item(
                client, d, template_id=tpl, title="Branded Poster", offer=offer
            )
            if not str(item.get("svg") or "").strip():
                continue  # real SVG only — no empty/fake poster
            items.append(item)
            used_dates.add(d)
            made += 1
        if not items:
            return 0
        added, added_items = _append_items_detailed(cid, items)
        if added_items:
            try:
                for it in added_items:
                    content_approval.submit(cid, it)
            except Exception as ae:  # pragma: no cover
                logger.debug(f"[auto_content] poster approval submit skip: {ae}")
            try:
                delivery_ledger.log_event(
                    cid,
                    "poster_generated",
                    detail=f"{len(added_items)} branded poster(s) ready",
                    meta={"count": len(added_items)},
                )
            except Exception:  # pragma: no cover
                pass
            try:
                from app.marketing import product_one_delivery

                product_one_delivery.sync_customer_deliverable_status(
                    cid,
                    "branded_posters",
                    "pending_approval",
                    note=f"{len(added_items)} branded posters generated.",
                    owner="AI",
                )
            except Exception as de:  # pragma: no cover
                logger.debug(f"[auto_content] poster deliverable sync skip: {de}")
        return added
    except Exception as e:  # pragma: no cover
        logger.debug(f"[auto_content] generate_poster_pack skip: {e}")
        return 0


def list_queue(client_id: str, status: str | None = None, limit: int = 60) -> list[dict[str, Any]]:
    """Client ka content queue (newest first, optional status filter). Kabhi
    raise nahi karta. Unresolvable authority → empty + ERROR (degrade, never silent)."""
    rows: list[dict[str, Any]] = []
    try:
        _QUEUE_DIR()
        if not os.path.isfile(_queue_path(client_id)):
            return rows
        with open(_queue_path(client_id), encoding="utf-8") as f:
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
        from app.platform import runtime_data as _rd

        if isinstance(e, _rd.RuntimeDataError):
            logger.error("[auto_content] content.queue authority UNRESOLVABLE: %s", e)
        else:
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


def upcoming_item_count(client_id: str) -> int:
    """Aaj ya aage ki date ke kitne non-skipped items queue me hain — customer ke
    "pehla 7-din plan banao" trigger ka idempotency guard (upcoming plan hote hue
    seed dubara chalana = content_approval me duplicate submissions, isliye guard
    yahan single-source hai: endpoint + worker task dono isi se poochhte).
    KABHI raise nahi karta."""
    try:
        today_s = date.today().strftime("%Y-%m-%d")
        n = 0
        for it in list_queue(client_id, limit=500):
            if str(it.get("date") or "") >= today_s and str(it.get("status") or "") != "skipped":
                n += 1
        return n
    except Exception:  # pragma: no cover
        return 0


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
        # Use engine.enabled() (env OR data/social_engine.json) — env-only guard used to
        # block admin JSON-file activation (audit 2026-07-17 F3).
        if added:
            try:
                from app.social_engine import engine as _se

                if _se.enabled():
                    caption_text = item.get("caption") or item.get("title") or ""
                    if caption_text:
                        hashtags = " ".join(
                            f"#{h.lstrip('#')}" for h in (item.get("hashtags") or [])[:5]
                        )
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
    try:
        _QUEUE_DIR()
        if not os.path.isfile(_queue_path(client_id)):
            return False
        rows: list[dict[str, Any]] = []
        found = False
        matched_title = ""
        with open(_queue_path(client_id), encoding="utf-8") as f:
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
                    # Publish-outcome item pe hi land ho (CDOS spec: published_at)
                    # — pehle yeh sirf delivery_ledger event me tha, item record
                    # khud kabhi nahi batata tha ki post kab gaya.
                    if st == "posted" and not rec.get("published_at"):
                        rec["published_at"] = rec["updated_at"]
                    found = True
                    matched_title = str(rec.get("title") or "")
                rows.append(rec)
        if not found:
            return False
        tmp = _queue_path(client_id) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, _queue_path(client_id))
        # Delivery ledger — post_approved/post_published for Command Center +
        # customer "what AI did for you" timeline (draft/skip intentionally
        # not logged as separate events; drafts already fire post_draft_created).
        if st in ("approved", "posted"):
            try:
                from app.marketing import delivery_ledger

                event = "post_approved" if st == "approved" else "post_published"
                delivery_ledger.log_event(str(client_id), event, detail=matched_title)
            except Exception as le:
                logger.debug(f"[auto_content] mark_item ledger log skip: {le}")
            try:
                from app.marketing import product_one_delivery

                if st == "approved":
                    product_one_delivery.sync_customer_deliverable_status(
                        str(client_id),
                        "social_posts",
                        "approved",
                        evidence_payload={"item_id": item_id, "title": matched_title},
                        note=matched_title,
                        owner="Customer/Admin",
                    )
                else:
                    product_one_delivery.sync_customer_deliverable_status(
                        str(client_id),
                        "proof",
                        "delivered",
                        evidence_payload={"item_id": item_id, "title": matched_title, "status": st},
                        note=matched_title,
                        owner="Ops",
                    )
            except Exception as de:
                logger.debug(f"[auto_content] mark_item deliverable db sync skip: {de}")
        return True
    except Exception as e:  # pragma: no cover
        from app.platform import runtime_data as _rd

        if isinstance(e, _rd.RuntimeDataError):
            logger.error("[auto_content] content.queue authority UNRESOLVABLE: %s", e)
        else:
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
