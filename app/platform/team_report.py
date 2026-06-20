"""team_report.py — "aapki AI team ne is hafte yeh kiya" client-facing weekly story.

HubSpot-Breeze-style packaging: team.recent_events (7 din) ko categorize karke
Hinglish NARRATIVE HTML banata hai — staff names ke saath ("Isha ne 12 posts
banaye, Rohan ne 25 emails bheje..."). client_report.py (monthly white-label
STATS report) se ALAG — yeh weekly AI-STAFF story hai (retention/wow factor).

free_ai se 2-3 line polish intro (1 call, deterministic fallback). Weekly sweep
`run_weekly_if_enabled()` GATED `TEAM_REPORT=1` (default OFF) → file
data/team_reports/<id>.html + optional client email (flag-on + email ho tabhi).
NEVER raises, sab imports lazy.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_OUT_DIR = os.path.join("data", "team_reports")

# action keyword → (category, Hinglish line template "{n}" ke saath)
_CATEGORIES: list[tuple[tuple[str, ...], str, str]] = [
    (
        ("content", "post", "blog", "repurpose", "month_plan", "reel", "carousel"),
        "content",
        "📣 Isha ne {n} content pieces banaye (posts/calendars/reels drafts)",
    ),
    (
        ("lead", "score", "prospect", "scrape", "harvest"),
        "leads",
        "🎯 Dev & Rohan ne {n} lead actions kiye (scrape, scoring, research)",
    ),
    (
        ("review", "brand_pulse", "sentiment"),
        "reviews",
        "⭐ Reviews/reputation pe {n} kaam hue (drafts, monitoring)",
    ),
    (
        ("call", "qualif", "voice", "telephony"),
        "calls",
        "📞 Swara/Tara ne {n} call-side actions kiye (calls, qualification, readiness)",
    ),
    (
        ("email", "outreach", "reply", "followup", "nurture", "dunning"),
        "emails",
        "✉️ Rohan/Nikhil ne {n} email/outreach actions kiye",
    ),
    (
        ("ops", "health", "pulse", "qa", "train", "watchdog"),
        "ops",
        "🛡️ Kavya/Arjun ne {n} baar system health/QA check kiya",
    ),
]


def _categorize(events: list[dict[str, Any]], since: datetime) -> dict[str, int]:
    counts: dict[str, int] = {c[1]: 0 for c in _CATEGORIES}
    counts["other"] = 0
    for ev in events or []:
        try:
            at = ev.get("at")
            if at:
                dt = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < since:
                    continue
            action = str(ev.get("action") or "").lower()
            hit = False
            for keys, cat, _tpl in _CATEGORIES:
                if any(k in action for k in keys):
                    counts[cat] += 1
                    hit = True
                    break
            if not hit:
                counts["other"] += 1
        except Exception:
            continue
    return counts


def _lines(counts: dict[str, int]) -> list[str]:
    out = []
    for _keys, cat, tpl in _CATEGORIES:
        n = counts.get(cat, 0)
        if n > 0:
            out.append(tpl.format(n=n))
    if not out:
        out.append(
            "🤖 Team standby pe rahi — naye kaam ke liye taiyaar (KB, scripts, monitors sab ready)."
        )
    return out


async def _polish_intro(business: str, total: int) -> str:
    """free_ai 2-line Hinglish intro (deterministic fallback)."""
    fallback = (
        f"Namaste! Yeh raha {business} ke liye is hafte ka AI-team report — "
        f"total {total} kaam aapke business ke liye automatically hue. 🚀"
    )
    try:
        from app.voice_agent import free_ai

        text, _p = await free_ai.chat(
            "Tu friendly Hinglish copywriter hai. 2 line ka warm weekly-report intro likh "
            "(client ko 'aapki AI team' ka kaam dikhana hai). Sirf intro, koi list nahi.",
            [
                {
                    "role": "user",
                    "content": f"Business: {business}. Is hafte total {total} automated actions.",
                }
            ],
            max_tokens=90,
            temperature=0.7,
        )
        if text and text.strip():
            return text.strip()[:400]
    except Exception as e:
        logger.debug(f"[team_report] intro llm skip: {e}")
    return fallback


def _render_html(business: str, primary: str, intro: str, lines: list[str], period: str) -> str:
    lis = "".join(
        f"<li style='padding:8px 0;border-bottom:1px solid #eee;font-size:15px'>{ln}</li>"
        for ln in lines
    )
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;background:#f6f7fb;margin:0;padding:24px">
<div style="max-width:560px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.07)">
<div style="background:{primary};color:#fff;padding:22px 24px">
<h2 style="margin:0">🤖 Aapki AI Team — Weekly Report</h2>
<div style="opacity:.9">{business} · {period}</div></div>
<div style="padding:18px 24px;color:#333;font-size:15px">{intro}</div>
<ul style="list-style:none;margin:0;padding:0 24px 12px">{lis}</ul>
<div style="padding:14px 24px 20px;color:#555;font-size:13px">Yeh sab aapki AI staff (Isha, Rohan, Swara & team)
ne automatically kiya — aap business pe focus karo, marketing hum sambhalte hain. 💪<br><br>
— Team LeadsGenAI · leadsgenai.in</div></div></body></html>"""


async def weekly_narrative(client_id: str | None = None) -> dict[str, Any]:
    """7-din ka AI-staff narrative. client_id ho to brand color + business name."""
    try:
        business = "Aapka Business"
        primary = "#2563eb"
        client: dict[str, Any] | None = None
        if client_id:
            try:
                from app.marketing import clients_store

                client = clients_store.get_client(str(client_id))
                if client:
                    business = str(client.get("business_name") or business)
                    brand = client.get("brand") if isinstance(client.get("brand"), dict) else {}
                    primary = str(brand.get("primary") or primary)
            except Exception:
                pass

        since = datetime.now(timezone.utc) - timedelta(days=7)
        events: list[dict[str, Any]] = []
        try:
            from app.platform import team

            events = team.recent_events(limit=300) or []
        except Exception as e:
            logger.debug(f"[team_report] events skip: {e}")

        counts = _categorize(events, since)
        total = sum(counts.values())
        lines = _lines(counts)

        # best-effort extra: is hafte ki inquiries (client-linked ho to filter)
        try:
            import json as _json

            wk = time.strftime("%Y-%m-%d", time.localtime(time.time() - 7 * 86400))
            slug = str((client or {}).get("slug") or "")
            n_inq = 0
            with open(os.path.join("data", "inquiries.jsonl"), encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    r = _json.loads(line)
                    ts = str(r.get("ts") or r.get("created_at") or "")[:10]
                    if ts >= wk and (not slug or r.get("source_slug") == slug):
                        n_inq += 1
            if n_inq:
                lines.insert(0, f"📥 {n_inq} nayi inquiries/leads capture hui is hafte")
                counts["inquiries"] = n_inq
        except Exception:
            pass

        intro = await _polish_intro(business, total)
        period = f"{since.strftime('%d %b')} – {datetime.now(timezone.utc).strftime('%d %b %Y')}"
        html = _render_html(business, primary, intro, lines, period)
        return {
            "ok": True,
            "client_id": client_id or "",
            "business_name": business,
            "period": period,
            "counts": counts,
            "lines": lines,
            "html": html,
        }
    except Exception as e:  # NEVER raise
        logger.info(f"[team_report] narrative err: {e}")
        return {"ok": False, "error": str(e)[:160]}


def _flag_on() -> bool:
    return (os.getenv("TEAM_REPORT") or "").strip().lower() in ("1", "true", "yes", "on")


async def run_weekly_if_enabled(max_clients: int = 20, send: bool | None = None) -> dict[str, Any]:
    """GATED TEAM_REPORT=1: active clients ke weekly reports file me (+email best-effort)."""
    if not _flag_on():
        return {"ok": False, "reason": "flag_off", "hint": "TEAM_REPORT=1 to enable"}
    out: dict[str, Any] = {"ok": True, "built": 0, "emailed": 0}
    try:
        os.makedirs(_OUT_DIR, exist_ok=True)
        from app.marketing import clients_store

        clients = clients_store.list_clients(status="active") or clients_store.list_clients()
        for c in (clients or [])[: max(1, max_clients)]:
            try:
                cid = str(c.get("id") or "")
                r = await weekly_narrative(cid)
                if not r.get("ok"):
                    continue
                path = os.path.join(_OUT_DIR, f"{cid}.html")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(r["html"])
                out["built"] += 1
                to = str(c.get("email") or "").strip()
                do_send = _flag_on() if send is None else bool(send)
                if do_send and to:
                    try:
                        from app.integrations.email_sender import email_sender

                        if await email_sender.send_email(
                            [to],
                            f"🤖 {r.get('business_name')} — AI Team Weekly Report",
                            r["html"],
                        ):
                            out["emailed"] += 1
                    except Exception as e:
                        logger.debug(f"[team_report] email skip: {e}")
            except Exception as e:
                logger.debug(f"[team_report] client skip: {e}")
        try:
            from app.platform.team import log_event

            log_event(
                "isha",
                "team_report",
                f"{out['built']} weekly reports built, {out['emailed']} emailed",
            )
        except Exception:
            pass
    except Exception as e:
        logger.info(f"[team_report] run err: {e}")
        out["ok"] = False
        out["error"] = str(e)[:160]
    return out


__all__ = ["weekly_narrative", "run_weekly_if_enabled"]
