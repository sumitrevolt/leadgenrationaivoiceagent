"""Sprint actions for the self-improve loop (teach-agent-loop 2026-07-31).

Teeno actions GTM mid-funnel / reliability pe kaam karte hain aur sab "auto-safe
ya draft-only" risk tier me hain — koi side-effect send nahi:

  dialer_sprint_prep : untapped prospect phones (ready + phone + not-yet-dialed)
                       ke human-dialer prep briefs (read-only, LLM fallback static).
  hot_wa_draft       : Hot Queue warm leads (interested/question) ke liye WhatsApp
                       reply drafts (draft-only — kabhi auto-send nahi, WHATSAPP_AUTO_SEND
                       untouched). Ban-safe 1-click human send waala pattern.
  job_heal_sweep     : stale scheduled-job heartbeats ko detect karke bounded
                       re-dispatch (scheduler_config.run_due — RUN_DUE_EXCLUDE honored).

Saari functions import-safe (lazy imports), bounded, aur kabhi raise nahi karti
— fail-open {"ok": False, "detail": ...} pattern. self_improve._execute inhe
dispatch karta hai; coordinator/staff bhi reuse kar sakte hain.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# dialer_sprint_prep
# ---------------------------------------------------------------------------
async def dialer_sprint_prep(limit: int = 3) -> dict[str, Any]:
    """Untapped prospect phones ke human-dialer prep briefs.

    Ready prospects (score >= 50) jinke paas valid phone hai aur jo abhi tak
    dialer log me nahi hai → top-N ko call_prep.prep_brief (LLM 25s cap + static
    fallback, kabhi empty nahi). Read-only — koi call/message nahi. Never raises.
    """
    try:
        from app.platform import call_prep, prospect_lists

        rows = prospect_lists.search(status="ready", min_score=50, limit=40)
        dialed: set[str] = set()
        try:
            from app.platform import dialer_log

            for rec in dialer_log._read_logs():
                d = str(rec.get("phone") or "")
                if d:
                    dialed.add(d)
        except Exception:
            pass

        briefs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for r in rows:
            if len(briefs) >= max(1, min(int(limit or 3), 5)):
                break
            ph = str(r.get("phone") or "").strip()
            try:
                from app.platform.memory_vault import phone10

                ph10 = phone10(ph)
            except Exception:
                ph10 = ""
            if not ph10 or ph10 in seen:
                continue
            seen.add(ph10)
            if ph10 in dialed:
                continue
            try:
                b = await call_prep.prep_brief(phone=ph10)
            except Exception as e:
                logger.debug("[sprint_prep] prep err %s", e)
                b = {"ok": False, "error": str(e)[:120]}
            briefs.append(
                {
                    "phone": ph10,
                    "business_name": str(r.get("business_name") or ""),
                    "niche": str(r.get("niche") or ""),
                    "city": str(r.get("city") or ""),
                    "score": r.get("score"),
                    "ok": bool(b.get("ok")),
                    "error": b.get("error"),
                    "provider": b.get("provider") or "fallback",
                    "brief": b.get("brief") or {},
                }
            )
        return {
            "ok": len(briefs) > 0,
            "detail": f"{len(briefs)} dialer prep briefs (untapped phones)",
            "briefs": briefs,
            "prepped": len(briefs),
        }
    except Exception as e:
        logger.debug("[sprint_prep] failed %s", e)
        return {"ok": False, "detail": f"dialer_sprint_prep: {str(e)[:200]}"}


# ---------------------------------------------------------------------------
# hot_wa_draft
# ---------------------------------------------------------------------------
async def hot_wa_draft(limit: int = 5) -> dict[str, Any]:
    """Hot Queue warm leads ke WhatsApp reply drafts (draft-only, ban-safe).

    ``reply_agent.hot_queue(scope="boss")`` se warm rows lo; sirf un rows ke
    liye WA draft banao jinke paas abhi koi usable draft NAHI hai (LLM-down
    gap-fill). Draft row channel="whatsapp" + from=phone ke saath save hoti hai
    → hot_queue agle pass me wa_link ke saath dikhti hai, human 1-click send
    karta hai. Idempotent: already-drafted rows skip. Kabhi raise nahi.
    """
    try:
        from app.platform import reply_agent

        rows = reply_agent.hot_queue(limit=max(1, min(int(limit or 5), 10)), scope="boss")
        drafted = skipped = 0
        for r in rows:
            phone = str(r.get("phone") or "").strip()
            if not phone:
                skipped += 1
                continue
            if str(r.get("draft") or "").strip():
                skipped += 1
                continue
            # dedupe: is phone ke liye already ek WA draft row hai?
            if _has_wa_draft(reply_agent, phone):
                skipped += 1
                continue
            text = await _wa_draft_text(
                biz=str(r.get("business_name") or ""),
                niche=str(r.get("niche") or "general"),
                intent=str(r.get("intent") or "interested"),
                subject=str(r.get("subject") or ""),
                body=str(r.get("content") or r.get("body") or ""),
            )
            if not text:
                skipped += 1
                continue
            from datetime import datetime, timezone

            rec = {
                "from": phone,
                "subject": str(r.get("subject") or ""),
                "intent": str(r.get("intent") or "interested"),
                "draft": text,
                "draft_source": "hot_wa_draft",
                "channel": "whatsapp",
                "at": datetime.now(timezone.utc).isoformat(),
            }
            if reply_agent._save_draft(rec):
                drafted += 1
            else:
                skipped += 1
        return {
            "ok": drafted > 0,
            "detail": f"{drafted} WA drafts, {skipped} skipped (draft-only, no auto-send)",
            "drafted": drafted,
            "skipped": skipped,
        }
    except Exception as e:
        logger.debug("[hot_wa_draft] failed %s", e)
        return {"ok": False, "detail": f"hot_wa_draft: {str(e)[:200]}"}


def _has_wa_draft(reply_agent: Any, phone: str) -> bool:
    """Recent drafts me is phone ka non-empty whatsapp draft already hai kya."""
    try:
        for d in reply_agent.list_drafts(limit=300):
            if (
                d.get("channel") == "whatsapp"
                and str(d.get("from") or "") == phone
                and str(d.get("draft") or "").strip()
            ):
                return True
    except Exception:
        pass
    return False


async def _wa_draft_text(biz: str, niche: str, intent: str, subject: str, body: str) -> str:
    """WA-specific short Hinglish draft — free_ai with deterministic fallback.

    Email replies ki tarah pricing append NAHI karta (WA pe pushy lagta hai);
    warm follow-up + free audit/demo CTA hi. LLM down = static fallback."""
    try:
        import asyncio

        from app.voice_agent import free_ai

        sys_prompt = (
            "Tu LeadGen AI ka sales rep hai. Ye warm lead ne interested/question "
            "dikhaya hai. Iska chhota, friendly, professional Hinglish WhatsApp "
            "message likh (max 3 lines, WA-appropriate — emoji optional). Free "
            "Google audit ya demo offer karo, pushy mat ban. Sirf message text de."
        )
        user_content = (
            f"Business: {biz}\nNiche: {niche}\nIntent: {intent}\n"
            f"Subject: {subject}\n\n{(body or '')[:800]}"
        )
        reply, _ = await asyncio.wait_for(
            free_ai.chat(
                sys_prompt,
                [{"role": "user", "content": user_content}],
                max_tokens=140,
                temperature=0.5,
            ),
            timeout=20,
        )
        text = (reply or "").strip()
        if text:
            return text
    except Exception as e:
        logger.debug("[hot_wa_draft] llm skip %s", e)
    # deterministic fallback (never-empty)
    return (
        "Namaste! Aapke interest ke liye dhanyavaad. "
        "Aap LeadGen AI ka free Google audit aur demo yahan dekh sakte hain: "
        "https://leadsgenai.in/demo"
    )


# ---------------------------------------------------------------------------
# job_heal_sweep
# ---------------------------------------------------------------------------
async def job_heal_sweep(max_jobs: int = 3) -> dict[str, Any]:
    """Stale scheduled-job heartbeats detect + bounded re-dispatch.

    ``team_scheduler._recover_due_jobs`` → ``scheduler_config.run_due(max_jobs=3)``
    wrap karta hai: overdue/never_ran (enabled + RUN_DUE_EXCLUDE me nahi) jobs ko
    re-dispatch karta hai. Idempotent-ish (heartbeat update + Celery idempotent).
    Bounded, ban-safe exclusions honored. Never raises.
    """
    try:
        from app.platform import automation_health, team_scheduler

        h = automation_health.health() or {}
        res = team_scheduler._recover_due_jobs() or {}
        started = res.get("started") or {}
        ok_keys = [k for k, v in started.items() if v not in ("error", "fail")]
        return {
            "ok": True,
            "detail": (
                f"overdue={len(h.get('overdue') or [])} never_ran={len(h.get('never_ran') or [])} "
                f"started={len(ok_keys)} excluded={len(res.get('skipped_excluded') or [])}"
            ),
            "overdue": h.get("overdue") or [],
            "never_ran": h.get("never_ran") or [],
            "started": started,
            "skipped_excluded": res.get("skipped_excluded") or [],
        }
    except Exception as e:
        logger.debug("[job_heal_sweep] failed %s", e)
        return {"ok": False, "detail": f"job_heal_sweep: {str(e)[:200]}"}


__all__ = ["dialer_sprint_prep", "hot_wa_draft", "job_heal_sweep"]
