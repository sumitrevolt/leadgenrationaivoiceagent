"""Daily social + video posting automation — 3x daily within 9am–7pm TRAI window.

Runs as Celery beat entries:
- staff-daily-social-post-morning (9:30 IST)
- staff-daily-social-post-midday (13:00 IST)
- staff-daily-social-post-evening (16:00 IST)

Each run:
1. Generates videos for own brand + active clients
2. Posts via Postiz to configured channels
3. Logs results, notifies owner via ntfy
4. Respects all compliance gates
"""

import datetime
import json
import os
from typing import Any

from app.integrations.postiz import (
    effective_integration_ids,
    integrations_source,
    plan_publish_channels,
    publish_video,
)
from app.integrations.postiz import (
    enabled as postiz_enabled,
)
from app.platform.hot_queue_owner_pack import check_gates
from app.tasks.video_generator import sync_generate_daily_videos
from app.utils.logger import setup_logger
from app.worker import celery_app

logger = setup_logger(__name__)
status = "GREEN"
capacity = 1  # Single run per beat

# --- Stale-sweep markers (Redis; fail-open if Redis unavailable) ---
# 2026-09-05: run_daily_social_post was previously NEVER registered as a Celery
# task (plain function) — the 3x daily beat entries sent a name the worker
# rejected as unregistered, so the daily social job silently never ran. The
# sweep (SOCIAL_STALE_SWEEP, INERT default) re-fires the job once/day when no
# successful post marker exists yet.
SWEEP_SUCCESS_KEY = "social_post:last_success_ymd"
SWEEP_FIRED_KEY = "social_post:sweep_fired_ymd"
SWEEP_SUCCESS_TTL_S = 8 * 86400   # a week of silence stays detectable
SWEEP_FIRED_TTL_S = 36 * 3600     # one sweep attempt per IST-day (idempotency)


def _redis_client():
    try:
        import redis as _redis

        from app.config import settings

        return _redis.Redis.from_url(str(settings.redis_url), socket_timeout=2)
    except Exception:
        return None


def _redis_value(val: Any) -> str:
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except Exception:
            return ""
    return str(val or "")


def _mark_success_if_any(result: dict) -> None:
    """Set today's success marker when at least one post actually went out."""
    try:
        own_posted = bool((result.get("own_brand") or {}).get("posted"))
        any_client = any(bool(c.get("posted")) for c in result.get("clients") or [])
        if not (own_posted or any_client):
            return
        r = _redis_client()
        if r is None:
            return
        ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        r.set(SWEEP_SUCCESS_KEY, datetime.datetime.now(ist).strftime("%Y-%m-%d"), ex=SWEEP_SUCCESS_TTL_S)
    except Exception as e:
        logger.debug(f"[daily_social] success-marker set failed: {e}")


@celery_app.task(name="app.tasks.daily_social_post.run_daily_social_post")
def run_daily_social_post():
    """Execute the daily social + video posting cycle.

    Called by Celery beat 3x daily (9:30, 13:00, 16:00 IST).
    """
    # 1. Compliance gate check
    gates = check_gates()
    open_gates = [k for k, v in gates.items() if v != "pass"]
    if open_gates:
        logger.info(f"Daily social post skipped — open compliance gates: {open_gates}")
        return {"status": "skipped", "reason": "open_compliance_gates", "gates": gates}

    # 2. Verify within TRAI window (9am–7pm IST)
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_ist = datetime.datetime.now(ist)
    if now_ist.hour < 9 or now_ist.hour >= 19:  # 9am–7pm inclusive
        logger.info(f"Outside TRAI window (hour={now_ist.hour}) — skipping social post")
        return {"status": "skipped", "reason": "outside_trai_window", "hour": now_ist.hour}

    # 3. Generate videos first (heavy CPU — already in worker)
    logger.info("[daily_social] Generating videos...")
    video_results = sync_generate_daily_videos()

    own_video = video_results.get("own_brand")
    client_videos = video_results.get("clients", [])

    logger.info(f"[daily_social] Videos ready: own={bool(own_video)}, clients={len(client_videos)}")

    result = {
        "timestamp": now_ist.isoformat(),
        "own_brand": {"posted": False, "channels": 0, "reason": None, "video_path": own_video},
        "clients": [],
    }

    # 4. Own-brand posting
    if postiz_enabled() and own_video:
        own_result = _post_own_brand(own_video, now_ist)
        result["own_brand"] = {**result["own_brand"], **own_result}
    elif not postiz_enabled():
        result["own_brand"]["reason"] = "POSTIZ_API_KEY not set"
    elif not own_video:
        result["own_brand"]["reason"] = "video generation failed"

    # 5. Client posting
    result["clients"] = _post_client_videos(client_videos, now_ist)

    # 5.5 Success marker for the stale-sweep (any successful post = healthy day)
    _mark_success_if_any(result)

    # 6. Log + ntfy summary to owner
    _log_and_notify(result, now_ist)

    return result


@celery_app.task(name="app.tasks.daily_social_post.run_social_stale_sweep")
def run_social_stale_sweep(now_ist: "datetime.datetime | None" = None):
    """Late-morning sweep: re-fire the daily social job when today had no success.

    Backlog 2026-07-18 (deferred-retry gap): a lost/failed 9:30 beat run left
    zero posts for the day with no recovery until the next slot (or forever,
    pre-2026-09-05, when the task name wasn't even registered). Sweep fires
    AT MOST once per IST-day (Redis fired-marker = idempotency) and only when
    no success marker exists for today. INERT until SOCIAL_STALE_SWEEP=1.
    """
    if os.getenv("SOCIAL_STALE_SWEEP", "0").strip().lower() not in ("1", "true", "yes"):
        return {"status": "inert", "reason": "SOCIAL_STALE_SWEEP off"}

    gates = check_gates()
    open_gates = [k for k, v in gates.items() if v != "pass"]
    if open_gates:
        return {"status": "skipped", "reason": "open_compliance_gates", "gates": gates}

    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    if now_ist is None:
        now_ist = datetime.datetime.now(ist)
    if now_ist.hour < 9 or now_ist.hour >= 19:
        return {"status": "skipped", "reason": "outside_trai_window", "hour": now_ist.hour}

    r = _redis_client()
    if r is None:
        return {"status": "skipped", "reason": "redis_unavailable"}

    today = now_ist.strftime("%Y-%m-%d")
    try:
        if _redis_value(r.get(SWEEP_SUCCESS_KEY)) == today:
            return {"status": "healthy", "last_success": today}
        if _redis_value(r.get(SWEEP_FIRED_KEY)) == today:
            return {"status": "already_swept", "last_success": _redis_value(r.get(SWEEP_SUCCESS_KEY)) or "unknown"}
        r.set(SWEEP_FIRED_KEY, today, ex=SWEEP_FIRED_TTL_S)
        run_daily_social_post.delay()
        logger.info("[daily_social] stale sweep re-fired daily social post (no success marker for %s)", today)
        return {"status": "rescheduled", "date": today}
    except Exception as e:
        logger.warning(f"[daily_social] stale sweep error: {e}")
        return {"status": "error", "reason": str(e)[:150]}


def _post_own_brand(video_path: str, now_ist: datetime.datetime):
    """Post own-brand video to connected Postiz channels."""
    try:
        # Own brand integrations from env
        raw = os.getenv("POSTIZ_INTEGRATIONS") or ""
        ids = [x.strip() for x in raw.split(",") if x.strip()] if raw else []

        if not ids:
            return {"posted": False, "channels": 0, "reason": "own-brand ids not configured"}

        client = {"id": "leadgenai-self", "business_name": "LeadGen AI"}

        # Plan channels (dry-run)
        plan = plan_publish_channels(client, has_media=True)
        selected = plan["selection"].get("ok", False) and plan["selection"].get("channels", [])

        if not selected:
            return {"posted": False, "channels": 0, "reason": "no eligible channels after plan"}

        # Publish video
        caption = (
            f"🤖 LeadGen AI Daily Update — {now_ist.strftime('%d %B %Y')}\n\n"
            "AI voice agent + automated marketing for local businesses — "
            "₹1,999/mo marketing + ₹4,999/₹9,999/₹19,999 voice calling.\n\n"
            "Free demo + audit available → leadsgenai.in\n\n"
            "#AI #Marketing #LocalBusiness #VoiceAI #SmallBusiness"
        )

        publish_result = publish_video(
            client=client,
            caption=caption,
            video_path=video_path,
            filename=f"leadgen_daily_{now_ist.strftime('%Y%m%d_%H%M')}.mp4",
        )

        return {
            "posted": publish_result.get("sent", False),
            "channels": len(selected),
            "post_id": publish_result.get("post_id", ""),
            "reason": publish_result.get("reason"),
            "outcome": publish_result.get("outcome"),
        }
    except Exception as e:
        logger.warning(f"[daily_social] own-brand post error: {e}")
        return {"posted": False, "channels": 0, "reason": str(e)[:150]}


def _post_client_videos(client_videos: list, now_ist: datetime.datetime):
    """Post videos for active marketing clients."""
    results = []

    # Check VIDEO_AD_CYCLE gate
    if os.getenv("VIDEO_AD_CYCLE", "0").strip().lower() not in ("1", "true", "yes"):
        for cv in client_videos:
            results.append({
                "client": cv.get("business_name"),
                "posted": False,
                "reason": "VIDEO_AD_CYCLE gate not enabled (set=1 for auto-post)",
            })
        return results

    for cv in client_videos:
        if not cv.get("video_path"):
            results.append({
                "client": cv.get("business_name"),
                "posted": False,
                "reason": "video generation failed",
            })
            continue

        client = {"id": cv["client_id"], "business_name": cv["business_name"]}

        # Check integrations
        ids = effective_integration_ids(client)
        if not ids:
            results.append({
                "client": cv["business_name"],
                "posted": False,
                "reason": "no postiz_integrations configured for client",
            })
            continue

        # Build niche-aware caption
        caption = f"💡 {cv['business_name']}: Daily update from your AI assistant\n\n"

        if "solar" in cv.get("business_name", "").lower():
            caption += "☀️ Solar savings tips + AI voice updates — call for free survey\n\n#Solar #AI #SmallBusiness"
        elif "renov" in cv.get("business_name", "").lower():
            caption += "🏠 Renovation tips + AI updates — free estimate + 3D design\n\n#Renovation #AI #HomeImprovement"
        else:
            caption += "Call ya WhatsApp karo — turant response milega\n\n#LocalBusiness #AI"

        filename = f"client_{cv['client_id']}_{now_ist.strftime('%Y%m%d_%H%M')}.mp4"

        publish_result = publish_video(
            client=client,
            caption=caption,
            video_path=cv["video_path"],
            filename=filename,
        )

        results.append({
            "client": cv["business_name"],
            "client_id": cv["client_id"],
            "posted": publish_result.get("sent", False),
            "channels": len(ids),
            "post_id": publish_result.get("post_id", ""),
            "reason": publish_result.get("reason"),
            "outcome": publish_result.get("outcome"),
            "video_path": cv["video_path"],
        })

    return results


def _log_and_notify(result, now_ist: datetime.datetime):
    """Log the daily results and push summary to owner via ntfy."""
    own = result["own_brand"]

    summary = f"""📱 DAILY SOCIAL POST — {now_ist.strftime('%d %B %Y, %H:%M IST')}

🏢 Own Brand:
- Posted: {'YES ✅' if own['posted'] else 'NO ❌'}
- Channels: {own['channels']}
- Reason: {own.get('reason', 'N/A')}
- Video: {os.path.basename(own.get('video_path', '')) if own.get('video_path') else 'N/A'}

👥 Clients ({len(result['clients'])}):
"""
    for c in result["clients"]:
        status_icon = "✅" if c.get("posted") else "❌"
        summary += f"- {c.get('client')} ({c.get('client_id', '')}): {status_icon} ({c.get('reason', 'N/A')})\n"

    total_posted = (1 if own['posted'] else 0) + sum(1 for c in result['clients'] if c.get('posted'))
    total_attempted = 1 + len(result['clients'])

    summary += f"""
📊 Batch: {total_posted}/{total_attempted} posted
🕐 Next run: {'13:00 IST' if now_ist.hour < 13 else '16:00 IST' if now_ist.hour < 16 else '9:30 IST (tomorrow)'}

🛡️ All actions gated — TRAI 9am-7pm, DND fail-closed, Postiz own-brand/client-separated.
"""

    # Push to ntfy (if topic configured)
    topic = os.getenv("NTFY_OWNER_TOPIC", "leadgen-owner")
    logger.info(f"[daily_social] Summary for ntfy topic '{topic}': {summary[:300]}...")

    # In production: use ntfy_utils.push(topic, summary)
    # For now: just log
    logger.info(summary)

    return summary


__all__ = ["status", "capacity", "run_daily_social_post"]
