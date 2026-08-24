"""
monthly_report.py — client ke liye "Is Mahine Ka Kaam" HTML report (free stack).
=================================================================================

team.recent_events() se member/action counts nikaal kar ek self-contained,
brand-violet styled HTML report banata hai (WhatsApp/email me bhejne layak):
  Sections: Is Mahine Ka Kaam / Numbers / AI Suggestions / Next Month Plan.

LLM (free_ai) se 3-line Hinglish summary — fail par template. DB/events na hon
to bhi report banti hai (zeros + starter suggestions). KABHI empty, KABHI raise
nahi.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

try:
    from app.voice_agent import free_ai  # type: ignore
except Exception:  # pragma: no cover - free_ai khud import-safe hai
    free_ai = None  # type: ignore

_IST = timezone(timedelta(hours=5, minutes=30))

# Dashboard-highlight buckets: action -> bucket (team events se).
_ACTION_BUCKETS: dict[str, tuple] = {
    "posts": ("post_generated", "festival_posts_generated", "calendar_generated"),
    "posters": ("poster_generated",),
    "calls": ("call_placed", "call_finished", "web_demo", "stream_call"),
    "reviews": ("review_reply_generated", "review_kit_generated"),
    "audits": ("gbp_audit_scored",),
    "whatsapp": ("whatsapp_pack_generated", "reactivation_generated", "drip_generated"),
}

_BUCKET_LABELS = {
    "posts": "📝 Posts/Calendars",
    "posters": "🖼️ Posters",
    "calls": "📞 Calls/Demos",
    "reviews": "⭐ Review Kaam",
    "audits": "🔍 GBP Audits",
    "whatsapp": "💬 WhatsApp Campaigns",
}


def _zero_stats() -> dict[str, Any]:
    """Empty stats block — client-scoped report jahan global team numbers galat
    honge (agent_events me client_id column nahi → platform-wide counts kisi ek
    client ke naam dikhana MISLEADING). Zeros = "Numbers" section honestly
    'abhi per-client tracking nahi' path pe chala jaata hai."""
    return {
        "total_actions": 0,
        "by_member": {},
        "by_action": {},
        "member_names": {},
        "highlights": dict.fromkeys(_ACTION_BUCKETS, 0),
        "events_analyzed": 0,
        "scoped": True,
    }


def _collect_stats() -> dict[str, Any]:
    """team.recent_events(300) → counts. DB na ho to zeros (kabhi raise nahi).

    NOTE: yeh PLATFORM-WIDE team events hain (sab staff/clients ka mila-jula).
    Ek specific client ki report ke liye yeh numbers GALAT hain — isliye
    build_report(client_id=...) diya ho to _zero_stats() use hoti hai."""
    events: list[dict[str, Any]] = []
    staff: dict[str, Any] = {}
    try:
        from app.platform.team import STAFF, recent_events

        staff = STAFF
        events = recent_events(300) or []
    except Exception as e:
        logger.debug(f"[report] events fetch skipped: {e}")

    by_member: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for ev in events:
        m = str(ev.get("member") or "system")
        a = str(ev.get("action") or "event")
        by_member[m] = by_member.get(m, 0) + 1
        by_action[a] = by_action.get(a, 0) + 1

    highlights = {
        bucket: sum(by_action.get(a, 0) for a in actions)
        for bucket, actions in _ACTION_BUCKETS.items()
    }
    member_names = {
        m: f"{(staff.get(m) or {}).get('emoji', '🤖')} {(staff.get(m) or {}).get('name', m.title())}"
        for m in by_member
    }
    return {
        "total_actions": len(events),
        "by_member": by_member,
        "by_action": by_action,
        "member_names": member_names,
        "highlights": highlights,
        "events_analyzed": len(events),
    }


def _template_summary(stats: dict[str, Any]) -> list[str]:
    h = stats["highlights"]
    total = stats["total_actions"]
    if total == 0:
        return [
            "Is mahine system setup phase me raha — agle mahine se numbers dikhne lagenge.",
            "Pehla kadam: GBP audit + har hafte 2 posts se shuruaat karein.",
            "Khush customers ko review QR/link bhejna shuru karein — 5 naye reviews ka target.",
        ]
    return [
        f"Is mahine total {total} marketing actions hue — system active hai.",
        (
            f"Content: {h['posts']} posts + {h['posters']} posters bane; "
            f"calls/demos: {h['calls']}, review kaam: {h['reviews']}."
        ),
        "Agle mahine review collection + drip follow-ups par focus karein — conversion wahin se badhti hai.",
    ]


def _default_plan() -> list[str]:
    plan = [
        "Har hafte 2 posts + 1 poster publish karein (festival templates ready hain).",
        "Har khush customer ko review QR/link bhejein — mahine me 8-10 naye reviews ka target.",
        "Purane customers par ek reactivation campaign chalayein (50 tak ek baar me).",
        "Har nayi inquiry par 4-step drip follow-up ON rakhein — koi lead thandi na ho.",
    ]
    try:  # nearest festival hook (best-effort)
        from app.marketing import festivals

        up = festivals.upcoming(60)
        if up:
            f0 = up[0]
            plan.insert(
                0,
                f"{f0['name']} ({f0['date']}) aa raha hai — poster + offer post abhi schedule karein.",
            )
    except Exception:
        pass
    return plan[:5]


def _build_html(
    client: str, month: str, stats: dict[str, Any], summary: list[str], plan: list[str]
) -> str:
    e = lambda s: escape(str(s or ""), quote=True)  # noqa: E731
    chips = "".join(
        f'<div class="chip"><div class="num">{stats["highlights"][b]}</div>'
        f'<div class="lbl">{e(_BUCKET_LABELS[b])}</div></div>'
        for b in _ACTION_BUCKETS
    )
    rows = (
        "".join(
            f'<tr><td>{e(stats["member_names"].get(m, m))}</td><td class="r">{n}</td></tr>'
            for m, n in sorted(stats["by_member"].items(), key=lambda kv: -kv[1])
        )
        or '<tr><td>Abhi events record nahi hue</td><td class="r">0</td></tr>'
    )
    rows += (
        f'<tr class="tot"><td>Total actions</td><td class="r">{stats["total_actions"]}</td></tr>'
    )
    sugg = "".join(f"<li>{e(s)}</li>" for s in summary)
    plan_html = "".join(f"<li>{e(p)}</li>" for p in plan)
    return (
        '<!DOCTYPE html><html lang="hi"><head><meta charset="utf-8">'
        f"<title>Marketing Report — {e(client)}</title><style>"
        "body{font-family:'Segoe UI',Arial,sans-serif;background:#f5f3ff;margin:0;"
        "padding:24px;color:#1f2937}"
        ".card{max-width:760px;margin:0 auto;background:#fff;border-radius:16px;"
        "overflow:hidden;box-shadow:0 4px 24px rgba(124,58,237,.18)}"
        ".head{background:linear-gradient(135deg,#7c3aed,#5b21b6);color:#fff;padding:28px 32px}"
        ".head h1{margin:0;font-size:24px}.head p{margin:6px 0 0;color:#e9d5ff}"
        ".sec{padding:20px 32px;border-bottom:1px solid #ede9fe}"
        ".sec h2{font-size:17px;color:#5b21b6;margin:0 0 14px}"
        ".chips{display:flex;flex-wrap:wrap;gap:10px}"
        ".chip{background:#f5f3ff;border:1px solid #ddd6fe;border-radius:12px;"
        "padding:10px 14px;min-width:96px;text-align:center}"
        ".chip .num{font-size:22px;font-weight:700;color:#7c3aed}"
        ".chip .lbl{font-size:12px;color:#6b7280;margin-top:2px}"
        "table{width:100%;border-collapse:collapse;font-size:14px}"
        "td{padding:8px 6px;border-bottom:1px solid #f3f4f6}.r{text-align:right;font-weight:600}"
        ".tot td{border-top:2px solid #ddd6fe;font-weight:700;color:#5b21b6}"
        "ul,ol{margin:0;padding-left:20px}li{margin:6px 0;font-size:14px}"
        ".foot{padding:16px 32px;font-size:12px;color:#8b8fa3;text-align:center}"
        "</style></head><body><div class='card'>"
        f"<div class='head'><h1>📊 Monthly Marketing Report — {e(month)}</h1>"
        f"<p>{e(client)}</p></div>"
        f"<div class='sec'><h2>Is Mahine Ka Kaam</h2><div class='chips'>{chips}</div></div>"
        f"<div class='sec'><h2>Numbers</h2><table>{rows}</table></div>"
        f"<div class='sec'><h2>AI Suggestions</h2><ul>{sugg}</ul></div>"
        f"<div class='sec'><h2>Next Month Plan</h2><ol>{plan_html}</ol></div>"
        "<div class='foot'>Generated by LeadGen AI — leadsgenai.in</div>"
        "</div></body></html>"
    )


async def build_report(
    client_name: str = "", month: str | None = None, client_id: str = ""
) -> dict[str, Any]:
    """Monthly marketing report (HTML + stats). KABHI empty nahi, KABHI raise nahi.

    client_id diya ho (ek SPECIFIC paying client ki report) to global team-event
    numbers OMIT hote hain — agent_events store me client_id column nahi, isliye
    platform-wide counts kisi ek client ke naam dikhana galat/misleading hai
    (billing-truth jaisa hi honesty issue). Un cases me "Numbers" section zeros
    dikhata + honest starter-guidance summary. client_id KHALI (agency/platform
    overview) = purana behavior byte-identical (global team numbers dikhte).

    Returns: {"html", "stats", "summary"[3], "plan", "month", "client_name",
              "provider", "scoped"}.
    """
    client = (client_name or "").strip() or "Aapka Business"
    month_label = (str(month).strip() if month else "") or datetime.now(_IST).strftime("%B %Y")
    scoped = bool(str(client_id or "").strip())

    try:
        # Scoped (per-client) report: global team numbers galat honge → omit.
        stats = _zero_stats() if scoped else _collect_stats()
    except Exception as e:  # pragma: no cover - _collect_stats khud guarded hai
        logger.warning(f"build_report stats failed: {e}")
        stats = _zero_stats()

    summary: list[str] = []
    provider = "template"
    if free_ai is not None:
        try:
            system = (
                "Tu ek Indian digital-marketing agency ka account manager hai. Client "
                "ki monthly report ke liye EXACTLY 3 alag lines Hinglish (Roman "
                "script) me likh — har line ek nayi line par, positive par honest, "
                "numbers ka use kar, koi extra commentary/heading nahi."
            )
            h = stats["highlights"]
            user = (
                f"Client: {client}. Mahina: {month_label}. "
                f"Total actions: {stats['total_actions']}, posts: {h['posts']}, "
                f"posters: {h['posters']}, calls/demos: {h['calls']}, "
                f"review kaam: {h['reviews']}, audits: {h['audits']}, "
                f"whatsapp campaigns: {h['whatsapp']}. 3-line summary likho."
            )
            text, p = await free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=220,
                temperature=0.6,
            )
            lines = [ln.strip(" -•*") for ln in (text or "").splitlines() if ln.strip()]
            if len(lines) >= 2:
                summary = lines[:3]
                provider = p or "llm"
        except Exception as e:  # free_ai.chat khud nahi raise karta, par safety
            logger.warning(f"build_report LLM summary failed, using template: {e}")

    if not summary:
        summary = _template_summary(stats)
        provider = "template"

    plan = _default_plan()
    stats_out = dict(stats)
    stats_out["month"] = month_label
    stats_out["client_name"] = client
    stats_out["scoped"] = scoped
    return {
        "html": _build_html(client, month_label, stats, summary, plan),
        "stats": stats_out,
        "summary": summary,
        "plan": plan,
        "month": month_label,
        "client_name": client,
        "provider": provider,
        "scoped": scoped,
    }
