"""video_ad_cycle.py — har N din (default 5) per active marketing client ko 1 AI
video ad: generate -> client approval -> approve hone par multi-channel social
publish. Change-request -> naya (revised) video -> fresh approval (revision loop).

Lifecycle (data/video_ads.jsonl, append-on-update latest-line-wins):
  pending  --client approve-->  approved  --scheduler publish-->  published
           --client "change chahiye" (note)--> changes_requested --regen--> pending(rev+1)
           (max revisions ke baad changes_requested = held, agency ko ping)

Design rules (CLAUDE.md):
  * build_reel HEAVY CPU -> sirf scheduler/worker se (run_cycle); web request me NAHI.
  * approve-hook (web) sirf FAST file-mark karta (on_approved); actual publish
    scheduler `publish_due()` karta -- web process heavy job nahi chalata.
  * GATED `VIDEO_AD_CYCLE=1` (scheduler tick). Manual/admin generate isse alag.
  * Sab additive, free-stack, NEVER raises (error dicts).

Channels: Telegram native (free, sendVideo) + Postiz (FB/IG/YT/LinkedIn, gated
POSTIZ_API_KEY) + hamesha 1-click WA share fallback (content_approval se).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FILE = os.path.join("data", "video_ads.jsonl")
_STATE = os.path.join("data", ".video_ad_cycle.json")


# ------------------------------- config ----------------------------------- #
def enabled() -> bool:
    """Scheduler auto-cycle gate. Manual generate_for_client isse independent."""
    return os.getenv("VIDEO_AD_CYCLE", "0").strip().lower() in ("1", "true", "yes")


def _interval_days() -> int:
    try:
        return max(1, int(os.getenv("VIDEO_AD_INTERVAL_DAYS", "5")))
    except Exception:
        return 5


def _max_revisions() -> int:
    try:
        return max(1, int(os.getenv("VIDEO_AD_MAX_REVISIONS", "3")))
    except Exception:
        return 3


def _max_per_run() -> int:
    try:
        return max(1, int(os.getenv("VIDEO_AD_MAX_PER_RUN", "10")))
    except Exception:
        return 10


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ------------------------------- store ------------------------------------ #
def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_FILE) or ".", exist_ok=True)
        with open(_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[video_ad] append failed: {e}")


def _latest() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
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
                rid = str(rec.get("id") or "")
                if rid:
                    cur = out.get(rid) or {}
                    cur.update(rec)
                    out[rid] = cur
    except Exception as e:
        logger.debug(f"[video_ad] read skip: {e}")
    return out


def _update(rec_id: str, **fields: Any) -> None:
    fields["id"] = rec_id
    _append(fields)


def _load_state() -> dict[str, str]:
    try:
        with open(_STATE, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_state(state: dict[str, str]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE) or ".", exist_ok=True)
        tmp = _STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, _STATE)
    except Exception as e:
        logger.warning(f"[video_ad] state save failed: {e}")


# ------------------------------- helpers ----------------------------------- #
def _eligible_clients() -> list[dict[str, Any]]:
    """Active marketing/combo clients (voice-only skip)."""
    try:
        from app.marketing import clients_store

        rows = clients_store.list_clients(status="active") or []
        out = []
        for c in rows:
            try:
                lane = clients_store.product_lane(c)
            except Exception:
                lane = "marketing"
            if lane in ("marketing", "combo"):
                out.append(c)
        return out
    except Exception as e:
        logger.warning(f"[video_ad] eligible failed: {e}")
        return []


def _channels_for(client: dict[str, Any]) -> list[str]:
    ch: list[str] = []
    if str(client.get("telegram_chat_id") or "").strip():
        ch.append("telegram")
    try:
        from app.marketing import postiz_publish

        if postiz_publish.enabled():
            ch.append("postiz")
    except Exception:
        pass
    ch.append("share")  # hamesha 1-click WA/manual share (FB/IG human post)
    return ch


async def _caption_slides(client: dict[str, Any], note: str = "") -> tuple[str, list[str]]:
    business = str(client.get("business_name") or "Aapka Business")
    niche = str(client.get("niche") or "general")
    offer = str(client.get("offer") or "").strip()
    hint = (offer + (" | " + note if note else "")).strip(" |")
    caption = ""
    try:
        from app.marketing import post_generator

        post = await post_generator.generate_post(business, niche=niche, offer=hint)
        caption = str(post.get("caption") or post.get("post_text") or "").strip()
    except Exception:
        caption = ""
    if not caption:
        caption = f"{business} — {offer or f'aapke area ka bharosemand {niche}'}. Inquiry: WhatsApp/Call."
    slides = [
        business,
        offer or f"Aapke area ka bharosemand {niche} expert",
        "Call ya WhatsApp karo — turant response milega",
    ]
    return caption, slides


# ------------------------------- generate ---------------------------------- #
async def generate_for_client(
    client_id: str, note: str = "", revision: int = 0, supersedes: str = ""
) -> dict[str, Any]:
    """1 video ad banao + client approval me daalo. HEAVY (build_reel) — scheduler/
    worker se call karo. Returns {ok, id, approval, wa_link} ya {ok:False,error}."""
    try:
        from app.marketing import clients_store, content_approval, reel_video

        client = clients_store.get_client(client_id) or {}
        if not client:
            return {"ok": False, "error": "client nahi mila"}
        caption, slides = await _caption_slides(client, note)
        built = await reel_video.build_reel(
            business_name=str(client.get("business_name") or "Aapka Business"),
            niche=str(client.get("niche") or "general"),
            slides=slides,
            offer=str(client.get("offer") or ""),
            client_id=client_id,
        )
        if built.get("error"):
            return {"ok": False, "error": f"video gen fail: {built['error']}", "detail": built}
        video_path = built.get("path") or ""
        channels = _channels_for(client)
        content = {
            "type": "video_ad",
            "title": "Naya video ad",
            "caption": caption,
            "video_path": video_path,
            "channels": channels,
            "revision": revision,
        }
        sub = content_approval.submit(client_id, content)
        if not sub.get("ok"):
            return {"ok": False, "error": sub.get("error") or "approval submit fail"}
        appr = sub.get("approval") or {}
        rid = uuid.uuid4().hex[:12]
        _append(
            {
                "id": rid,
                "client_id": client_id,
                "approval_id": appr.get("id"),
                "token": appr.get("token"),
                "status": "pending",
                "revision": revision,
                "note": note,
                "video_path": video_path,
                "caption": caption,
                "channels": channels,
                "supersedes": supersedes,
                "created_at": _now(),
            }
        )
        if supersedes:
            _update(supersedes, status="superseded", superseded_by=rid)
        st = _load_state()
        st[client_id] = time.strftime("%Y-%m-%d")
        _save_state(st)
        try:
            from app.platform import team

            team.log_event(
                "isha",
                "video_ad_generated",
                f"{client.get('business_name')} ka video ad rev{revision} approval ko bheja",
                meta={"video_ad_id": rid, "approval_id": appr.get("id")},
            )
        except Exception:
            pass
        return {
            "ok": True,
            "id": rid,
            "approval": appr,
            "approve_url": sub.get("approve_url"),
            "reject_url": sub.get("reject_url"),
            "wa_link": sub.get("wa_link"),
            "video_path": video_path,
        }
    except Exception as e:
        logger.warning(f"[video_ad] generate failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


# ------------------------------- approve / change hooks --------------------- #
def on_approved(approval_rec: dict[str, Any]) -> bool:
    """content_approval._decide(approved) se call (FAST, sync). Hamare video_ad rec
    ko approved (pending-publish) mark karta — actual publish scheduler karta."""
    try:
        aid = str(approval_rec.get("id") or "")
        if not aid:
            return False
        for rid, rec in _latest().items():
            if str(rec.get("approval_id") or "") == aid and rec.get("status") == "pending":
                _update(rid, status="approved", decided_at=_now())
                return True
        return False
    except Exception as e:
        logger.debug(f"[video_ad] on_approved skip: {e}")
        return False


def on_changes_requested(approval_rec: dict[str, Any]) -> bool:
    """content_approval._decide(rejected) se call (FAST, sync). Video-ad ko
    changes_requested mark karta — scheduler `_regen_due()` naya version banata.
    (content_approval ne reject already kar diya — yahan sirf state mark.)"""
    try:
        aid = str(approval_rec.get("id") or "")
        if not aid:
            return False
        note = str(approval_rec.get("note") or "")
        for rid, rec in _latest().items():
            if str(rec.get("approval_id") or "") == aid and rec.get("status") == "pending":
                _update(rid, status="changes_requested", note=note, changes_at=_now())
                return True
        return False
    except Exception as e:
        logger.debug(f"[video_ad] on_changes_requested skip: {e}")
        return False


async def request_changes(approval_id: str, note: str = "") -> dict[str, Any]:
    """Admin/support entry: client ne 'change chahiye' bola — reject + changes_requested
    mark. Regeneration scheduler `_regen_due()` karta. Returns {ok, status}."""
    try:
        from app.marketing import content_approval

        target = None
        for rid, rec in _latest().items():
            if str(rec.get("approval_id") or "") == str(approval_id or ""):
                target = (rid, rec)
                break
        if not target:
            return {"ok": False, "error": "video ad nahi mila"}
        rid, rec = target
        tok = str(rec.get("token") or "")
        if tok:
            content_approval.reject(tok, note)
        _update(rid, status="changes_requested", note=note, changes_at=_now())
        try:
            from app.platform import team

            team.log_event(
                "isha",
                "video_ad_changes",
                f"Client ne video ad change maanga — note: {note[:120]}",
                meta={"video_ad_id": rid},
            )
        except Exception:
            pass
        return {"ok": True, "status": "changes_requested", "id": rid}
    except Exception as e:
        logger.warning(f"[video_ad] request_changes failed: {e}")
        return {"ok": False, "error": str(e)[:150]}


# ------------------------------- publish ------------------------------------ #
async def _tg_send_video(chat_id: str, video_path: str, caption: str = "") -> dict[str, Any]:
    """Telegram Bot API sendVideo — self-contained (flaky telegram_publish par
    dependency-free fallback). Gated TELEGRAM_BOT_TOKEN. NEVER raises."""
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return {"sent": False, "reason": "TELEGRAM_BOT_TOKEN unset"}
    if not chat_id or not video_path or not os.path.isfile(video_path):
        return {"sent": False, "reason": "chat_id/video missing"}
    try:
        import httpx

        api = f"https://api.telegram.org/bot{token}/sendVideo"
        with open(video_path, "rb") as fh:
            async with httpx.AsyncClient(timeout=120) as cx:
                r = await cx.post(
                    api,
                    data={"chat_id": chat_id, "caption": (caption or "")[:1024]},
                    files={"video": (os.path.basename(video_path), fh, "video/mp4")},
                )
        ok = r.status_code == 200 and r.json().get("ok")
        return {"sent": bool(ok), **({} if ok else {"reason": r.text[:160]})}
    except Exception as e:
        return {"sent": False, "reason": str(e)[:120]}


async def _publish_one(rec: dict[str, Any]) -> dict[str, Any]:
    from app.marketing import clients_store

    cid = str(rec.get("client_id") or "")
    client = clients_store.get_client(cid) or {}
    caption = str(rec.get("caption") or "")
    video_path = str(rec.get("video_path") or "")
    # SOCIAL_ENGINE on -> durable native engine (Redis/Celery queue + provider adapters)
    # ko handoff; engine khud Telegram/Meta/GBP/LinkedIn/X/YouTube/Postiz pe deliver karta.
    try:
        from app.social_engine import engine as _social_engine

        if _social_engine.enabled():
            ids = _social_engine.enqueue_publish(
                cid, caption=caption, media_path=video_path, media_type="video"
            )
            return {"any_sent": bool(ids), "channels": {"engine": {"queued_jobs": ids}}}
    except Exception as e:
        logger.warning(f"[video_ad] social_engine handoff skip: {e}")
    result: dict[str, Any] = {}
    any_sent = False
    # 1) Telegram native (free) — self-contained sendVideo (telegram_publish optional).
    chat_id = str(client.get("telegram_chat_id") or "").strip()
    if chat_id and video_path:
        try:
            sender = None
            try:
                from app.marketing import telegram_publish

                sender = getattr(telegram_publish, "send_video", None)
            except Exception:
                sender = None
            tg = (
                await sender(chat_id, video_path, caption)
                if sender
                else await _tg_send_video(chat_id, video_path, caption)
            )
            result["telegram"] = tg
            any_sent = any_sent or bool(tg.get("sent"))
        except Exception as e:
            result["telegram"] = {"sent": False, "reason": str(e)[:120]}
    # 2) Postiz (FB/IG/YT/LinkedIn) — gated POSTIZ_API_KEY
    try:
        from app.marketing import postiz_publish

        if postiz_publish.enabled():
            pz = await postiz_publish.publish_video(client, caption, video_path)
            result["postiz"] = pz
            any_sent = any_sent or bool(pz.get("sent"))
    except Exception as e:
        result["postiz"] = {"sent": False, "reason": str(e)[:120]}
    return {"any_sent": any_sent, "channels": result}


async def publish_due(limit: int = 20) -> dict[str, Any]:
    """Approved (pending-publish) video ads ko channels pe bhejo. Scheduler se."""
    published = failed = 0
    try:
        rows = [r for r in _latest().values() if r.get("status") == "approved"]
        rows.sort(key=lambda r: str(r.get("decided_at") or r.get("created_at") or ""))
        for rec in rows[: max(1, int(limit))]:
            rid = str(rec.get("id") or "")
            res = await _publish_one(rec)
            if res.get("any_sent"):
                _update(rid, status="published", published_at=_now(), publish_result=res["channels"])
                published += 1
            else:
                _update(rid, status="publish_failed", publish_result=res["channels"], failed_at=_now())
                failed += 1
        return {"ran": True, "published": published, "failed": failed}
    except Exception as e:
        logger.warning(f"[video_ad] publish_due failed: {e}")
        return {"ran": False, "reason": str(e)[:150]}


async def _regen_due(limit: int = 10) -> int:
    """changes_requested items ko (max-revisions tak) regenerate karo."""
    regen = 0
    try:
        rows = [r for r in _latest().values() if r.get("status") == "changes_requested"]
        for rec in rows[: max(1, int(limit))]:
            rid = str(rec.get("id") or "")
            rev = int(rec.get("revision") or 0)
            if rev + 1 > _max_revisions():
                _update(rid, status="held_max_revisions")
                continue
            r = await generate_for_client(
                str(rec.get("client_id") or ""),
                note=str(rec.get("note") or ""),
                revision=rev + 1,
                supersedes=rid,
            )
            if r.get("ok"):
                regen += 1
        return regen
    except Exception as e:
        logger.warning(f"[video_ad] regen failed: {e}")
        return 0


# ------------------------------- scheduler tick ----------------------------- #
async def run_cycle() -> dict[str, Any]:
    """Scheduler entrypoint (GATED VIDEO_AD_CYCLE). 3 kaam: due clients ke naye ads,
    change-requests regen, approved ads publish. Flag off = inert. NEVER raises."""
    if not enabled():
        return {"ran": False, "reason": "VIDEO_AD_CYCLE off"}
    out: dict[str, Any] = {"ran": True}
    try:
        out["regenerated"] = await _regen_due()
        interval = _interval_days()
        st = _load_state()
        gen = 0
        cap = _max_per_run()
        for c in _eligible_clients():
            if gen >= cap:
                break
            cid = str(c.get("id") or "")
            if not cid:
                continue
            last = st.get(cid)
            due = True
            if last:
                try:
                    last_t = time.mktime(time.strptime(last, "%Y-%m-%d"))
                    due = (time.time() - last_t) >= (interval * 86400 - 3600)
                except Exception:
                    due = True
            if due:
                r = await generate_for_client(cid)
                if r.get("ok"):
                    gen += 1
        out["generated"] = gen
        out["publish"] = await publish_due()
        # durable social-engine queue bhi drain karo (gated SOCIAL_ENGINE; off = inert)
        try:
            from app.social_engine import engine as _social_engine

            out["engine"] = await _social_engine.process_queue()
        except Exception as e:
            logger.debug(f"[video_ad] engine drain skip: {e}")
        return out
    except Exception as e:
        logger.warning(f"[video_ad] run_cycle failed: {e}")
        return {"ran": False, "reason": str(e)[:150]}


# ------------------------------- read API ----------------------------------- #
def list_for_client(client_id: str, limit: int = 50) -> list[dict[str, Any]]:
    cid = str(client_id or "").strip()
    rows = [r for r in _latest().values() if not cid or str(r.get("client_id") or "") == cid]
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows[: max(1, min(int(limit or 50), 200))]


def list_all(limit: int = 100) -> list[dict[str, Any]]:
    return list_for_client("", limit)


__all__ = [
    "enabled",
    "generate_for_client",
    "on_approved",
    "on_changes_requested",
    "request_changes",
    "publish_due",
    "run_cycle",
    "list_for_client",
    "list_all",
]
