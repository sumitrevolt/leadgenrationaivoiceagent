"""sales_team.py — 5-parallel-agent prospect deep-dive (ai-sales-team-claude adapt).

zubair-trabzada/ai-sales-team-claude ka flagship `/sales prospect` pattern —
humare free-stack + Indian-SMB context me: 5 agents PARALLEL (asyncio.gather)
ek prospect pe, Boss aggregate, ready-to-act analysis + drafts.

Agents (sab existing staff personas reuse — naya roster NAHI):
- Riya 🔍 Research      — prospect website fetch+clean (web_extract) → 3-bullet brief
- Veer 📊 Qualify       — BANT (sales_qualify, pure) + grade A-D
- Dev 🥊 Competitive    — niche ke common alternatives + humara differentiation angle
- Isha ✉️ Outreach      — 5-touch Hinglish sequence (hook→value→proof→angle→breakup,
                          email+WhatsApp mix) — ban-safe DRAFTS, auto-send NAHI
- Arjun 🛡️ Objections   — top-5 anticipated objections, LAER-style Hinglish rebuttals

Sab LLM calls free_ai.chat (fallback static templates = LLM-down pe bhi kaam).
Output: dict + markdown report `data/prospect_analyses/<id>.md` + jsonl index.
AUTO-PILOT: `run_auto()` GATED `SALES_TEAM=1` — roz top hot-leads (bina analysis
wale) pe auto deep-dive → drafts taiyaar, Sumit sirf 1-click send kare.
Kabhi raise nahi karta. Side-effect ZERO (sirf files + agent_events log).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DIR = os.path.join("data", "prospect_analyses")
_INDEX = os.path.join(_DIR, "index.jsonl")
_REDO_DAYS = 7  # isse purana analysis = dobara banega


def _enabled() -> bool:
    return os.environ.get("SALES_TEAM", "0").strip().lower() in ("1", "true", "yes")


def _pid(p: dict) -> str:
    raw = p.get("phone") or p.get("email") or p.get("name") or p.get("business_name") or "anon"
    return re.sub(r"[^a-zA-Z0-9]+", "_", str(raw)).strip("_")[:60] or "anon"


def _persona_prefix(topic: str, max_chars: int = 420) -> str:
    """Agency sales-persona pack se guidance prefix (skill_pack.snippet_for).

    LLM ko ek senior sales specialist ka playbook deta — ppc nahi, sales
    personas (account/deal/outbound/coach). Defensive: skill_pack missing ya
    kuch na mile to ""."""
    if not topic:
        return ""
    try:
        from app.platform import skill_pack

        snip = skill_pack.snippet_for(topic, max_chars=max_chars) or ""
        if not snip:
            return ""
        return (
            "Neeche ek senior sales specialist ka internal playbook hai. "
            "Ise APPLY karo (raw text copy mat karo):\n"
            f"{snip}\n\n"
        )
    except Exception:
        return ""


async def _llm(system: str, user: str, max_tokens: int = 350, ground: str = "") -> str:
    try:
        from app.voice_agent import free_ai

        sys2 = (_persona_prefix(ground) + system) if ground else system
        reply, _ = await free_ai.chat(
            sys2, [{"role": "user", "content": user}], max_tokens=max_tokens, temperature=0.5
        )
        return (reply or "").strip()
    except Exception:
        return ""


def _pdesc(p: dict) -> str:
    return (
        f"Business: {p.get('name') or p.get('business_name') or '?'} | "
        f"Niche: {p.get('niche') or '?'} | City: {p.get('city') or '?'} | "
        f"Rating: {p.get('rating') or '?'} ({p.get('reviews') or p.get('user_ratings_total') or 0} reviews) | "
        f"Website: {p.get('website') or 'NAHI'} | Status: {p.get('status') or 'new'}"
    )


# ----------------------------- Agents ----------------------------- #
async def _research(p: dict) -> dict[str, Any]:
    """Riya: website text (agar hai) + record → short brief."""
    site_text = ""
    url = (p.get("website") or "").strip()
    if url:
        try:
            import httpx

            from app.lead_scraper import web_extract

            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as cx:
                r = await cx.get(url if url.startswith("http") else f"https://{url}")
            if r.status_code == 200:
                site_text = (web_extract.clean_text(r.text) or "")[:1500]
        except Exception:
            site_text = ""
    brief = await _llm(
        "Tum Riya ho — sales research analyst. 3 short Hinglish bullets me prospect brief do: "
        "kya bechte hain, kitne serious/established lagte hain, marketing me kya GAP dikhta hai. Sirf bullets.",
        _pdesc(p)
        + (
            f"\n\nWebsite text:\n{site_text}"
            if site_text
            else "\n\n(Website nahi hai / fetch fail)"
        ),
        ground="sales account research prospect discovery qualification",
    )
    if not brief:
        brief = (
            f"- {p.get('niche') or 'local'} business, {p.get('city') or '?'}\n"
            f"- {'Website hai' if url else 'Website NAHI — digital gap'}\n"
            f"- Reviews: {p.get('reviews') or p.get('user_ratings_total') or 0} — Google presence "
            + (
                "theek"
                if int(float(p.get("reviews") or p.get("user_ratings_total") or 0)) >= 10
                else "WEAK"
            )
        )
    return {"agent": "riya", "brief": brief, "website_found": bool(site_text)}


async def _qualify(p: dict) -> dict[str, Any]:
    """Veer: BANT (pure-Python — LLM nahi chahiye)."""
    from app.platform import sales_qualify

    q = sales_qualify.bant_score(p)
    q["agent"] = "veer"
    return q


async def _competitive(p: dict) -> dict[str, Any]:
    """Dev: prospect ke paas abhi kya options hain + humara edge."""
    txt = await _llm(
        "Tum Dev ho — competitive analyst. Is local business ko marketing services bechne ja rahe hain "
        "(AI posts+GBP+reviews+voice callbacks, ₹1,999-5,999/mo). 3 Hinglish bullets: (1) yeh abhi marketing "
        "kaise karta hoga (2) humse pehle kis se compare karega (local agency/Dhanda-type app/khud) "
        "(3) humara 1-line killer differentiation iske liye. Sirf bullets.",
        _pdesc(p),
        ground="sales competitive positioning differentiation deal strategy",
    )
    if not txt:
        txt = (
            "- Abhi: word-of-mouth + kabhi-kabhi boosted post\n"
            "- Compare karega: local agency (₹8-15k/mo) ya DIY apps\n"
            "- Humara edge: agency-level kaam ₹1,999 se + AI callback jo koi nahi deta"
        )
    return {"agent": "dev", "competitive": txt}


def build_sequence_fallback(p: dict) -> list[dict[str, str]]:
    """Pure (testable): 5-touch Hinglish sequence — LLM down ho to bhi drafts bante."""
    nm = p.get("name") or p.get("business_name") or "ji"
    niche = p.get("niche") or "business"
    city = p.get("city") or "aapke area"
    return [
        {
            "day": "1",
            "channel": "email",
            "title": "Hook",
            "draft": f"Namaste {nm}! {city} me aapka {niche} dekha — Google pe aapki listing me kuch quick "
            f"improvements dikhe jo naye customer la sakte hain. 2-min ka FREE audit bhejun? leadsgenai.in/audit",
        },
        {
            "day": "2",
            "channel": "whatsapp",
            "title": "WA nudge",
            "draft": f"Namaste {nm} 🙏 Kal email bheja tha — aapke {niche} ke liye FREE Google audit ready hai. "
            f"Haan bolo to abhi link bhej deta hoon.",
        },
        {
            "day": "7",
            "channel": "email",
            "title": "Social proof",
            "draft": f"{nm}, {city} ke ek {niche} ne humare AI marketing se 30 din me inquiries double ki — "
            f"posts+reviews+missed-call callback sab automatic. ₹1,999/mo se start. Demo: leadsgenai.in/demo",
        },
        {
            "day": "14",
            "channel": "email",
            "title": "Different angle",
            "draft": f"{nm}, ek sawaal — jab koi customer call karta hai aur aap busy ho, woh kahan jata hai? "
            f"Competitor ke paas. Humara AI 2-min me callback karta hai. Dekho: leadsgenai.in/pricing",
        },
        {
            "day": "21",
            "channel": "email",
            "title": "Breakup",
            "draft": f"{nm}, lagta hai abhi sahi time nahi. Koi baat nahi! Yeh FREE audit link rakh lijiye — "
            f"jab bhi marketing badhani ho, 2 minute me report milegi: leadsgenai.in/audit. Shubhkamnayein!",
        },
    ]


async def _outreach(p: dict, qual: dict | None = None) -> dict[str, Any]:
    """Isha: personalized 5-touch sequence (drafts only)."""
    seq = build_sequence_fallback(p)
    hints = ""
    if qual:
        hints = f"\nBANT: grade {qual.get('grade')}, need-reasons: {'; '.join(qual.get('reasons', [])[:3])}"
    raw = await _llm(
        "Tum Isha ho — outreach copywriter. Niche template sequence ko is prospect ke liye PERSONALIZE karo "
        "(unke niche/city/gap reference karo). JSON array lautao, har item {day, channel, title, draft} — "
        "drafts short Hinglish, pushy nahi. Sirf JSON.",
        _pdesc(p) + hints + "\n\nTemplate:\n" + json.dumps(seq, ensure_ascii=False),
        max_tokens=700,
        ground="sales outbound cold email sequence cadence multi-touch",
    )
    try:
        i, j = raw.find("["), raw.rfind("]")
        if i != -1 and j != -1:
            cand = json.loads(raw[i : j + 1])
            if isinstance(cand, list) and len(cand) >= 3 and all(c.get("draft") for c in cand):
                seq = cand[:5]
    except Exception:
        pass
    return {"agent": "isha", "sequence": seq}


OBJECTION_PLAYBOOK = [
    {
        "objection": "Mehenga hai / budget nahi",
        "category": "price",
        "laer": "Acknowledge: bilkul sahi sawaal. Explore: abhi marketing pe mahine ka kitna jata hai? "
        "Respond: ₹1,999 me jo milta hai uska agency rate ₹8-10k hai; ek naya customer bhi aaya to paisa vasool. "
        "Redirect: Starter se shuru karo, kabhi bhi band kar sakte ho.",
    },
    {
        "objection": "Pehle se koi (agency/ladka) sambhal raha hai",
        "category": "competition",
        "laer": "Acknowledge: badhiya, matlab marketing ki value samajhte ho. Explore: results se khush ho? reviews/callback "
        "bhi karta hai? Respond: hum replace nahi, AUTOMATE karte hain — roz ka content+review reply+missed-call "
        "callback 24/7. Redirect: ek mahina saath chala ke compare kar lo.",
    },
    {
        "objection": "Time nahi hai / baad me",
        "category": "timing",
        "laer": "Acknowledge: samajh sakta hoon, dhandha pehle. Explore: kaunsa season busy hai? Respond: isiliye to yeh hai — "
        "setup 10 minute, baaki sab AI khud karta hai; busy season me hi naye customer sabse zyada milte hain. "
        "Redirect: abhi sirf FREE audit dekh lo, 2 minute.",
    },
    {
        "objection": "Khud kar lenge / bhatija kar dega",
        "category": "diy",
        "laer": "Acknowledge: bilkul ho sakta hai. Explore: roz post + har review ka reply + har missed call pe turant "
        "callback — consistently ho pa raha hai? Respond: consistency hi game hai, AI kabhi chutti nahi leta. "
        "Redirect: demo dekho — leadsgenai.in/demo pe apne business ka naam daalo.",
    },
    {
        "objection": "AI pe bharosa nahi / gimmick lagta hai",
        "category": "trust",
        "laer": "Acknowledge: sahi soch, naya hai. Explore: sabse bada dar kya hai — galat post ya paisa waste? "
        "Respond: har post aap approve karte ho (1-click), kuch bhi auto-publish nahi hota; pehla hafta result "
        "khud dekho. Redirect: ₹0 me /demo try karo, card bhi nahi chahiye.",
    },
]


async def _objections(p: dict) -> dict[str, Any]:
    """Arjun: anticipated objections + LAER rebuttals (niche-personalized, fallback static)."""
    out = OBJECTION_PLAYBOOK
    raw = await _llm(
        "Tum Arjun ho — sales objection coach. Is prospect ke liye 5 most-likely objections + LAER "
        "(Listen-Acknowledge-Explore-Respond) Hinglish rebuttals do. JSON array [{objection, category, laer}]. Sirf JSON.",
        _pdesc(p),
        max_tokens=600,
        ground="sales objection handling rebuttal closing coach",
    )
    try:
        i, j = raw.find("["), raw.rfind("]")
        if i != -1 and j != -1:
            cand = json.loads(raw[i : j + 1])
            if isinstance(cand, list) and len(cand) >= 3 and all(c.get("objection") for c in cand):
                out = cand[:5]
    except Exception:
        pass
    return {"agent": "arjun", "playbook": out}


# ----------------------------- Orchestrator ----------------------------- #
def _render_md(p: dict, parts: dict[str, Any]) -> str:
    q = parts.get("qualify", {})
    lines = [
        f"# Prospect Analysis — {p.get('name') or p.get('business_name') or '?'}",
        f"_{_pdesc(p)}_",
        "",
        f"## Score: {q.get('total', 0)}/100 — Grade {q.get('grade', '?')}",
        f"B {q.get('budget', 0)}/25 · A {q.get('authority', 0)}/25 · N {q.get('need', 0)}/25 · T {q.get('timeline', 0)}/25",
        f"**Action:** {q.get('action', '')}",
        "",
        "## 🔍 Research (Riya)",
        parts.get("research", {}).get("brief", ""),
        "",
        "## 🥊 Competitive (Dev)",
        parts.get("competitive", {}).get("competitive", ""),
        "",
        "## ✉️ Outreach sequence (Isha) — drafts, 1-click send",
    ]
    for s in parts.get("outreach", {}).get("sequence", []):
        lines.append(
            f"- **Day {s.get('day')} [{s.get('channel')}] {s.get('title')}**: {s.get('draft')}"
        )
    lines += ["", "## 🛡️ Objection playbook (Arjun)"]
    for o in parts.get("objections", {}).get("playbook", []):
        lines.append(f'- **"{o.get("objection")}"** → {o.get("laer")}')
    if parts.get("boss_summary"):
        lines += ["", "## 🎯 Boss verdict", parts["boss_summary"]]
    return "\n".join(lines)


def _index_rows() -> list[dict]:
    try:
        if not os.path.exists(_INDEX):
            return []
        with open(_INDEX, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except Exception:
        return []


async def analyze(p: dict) -> dict[str, Any]:
    """Ek prospect pe 5-agent parallel deep-dive. Output: analysis dict + saved .md."""
    try:
        qual = await _qualify(p)  # pehle — outreach ko hints milte
        research, competitive, outreach, objections = await asyncio.gather(
            _research(p),
            _competitive(p),
            _outreach(p, qual),
            _objections(p),
            return_exceptions=True,
        )

        def _ok(x, fb):
            return x if isinstance(x, dict) else fb

        parts = {
            "qualify": qual,
            "research": _ok(research, {"brief": ""}),
            "competitive": _ok(competitive, {"competitive": ""}),
            "outreach": _ok(outreach, {"sequence": build_sequence_fallback(p)}),
            "objections": _ok(objections, {"playbook": OBJECTION_PLAYBOOK}),
        }
        boss = await _llm(
            "Tum Boss ho — sales manager. 2-line Hinglish verdict: is prospect pe kitna effort lagana chahiye "
            "aur pehla move kya ho. Direct, no fluff.",
            f"{_pdesc(p)}\nBANT: {qual.get('total')}/100 grade {qual.get('grade')}. "
            f"Reasons: {'; '.join(qual.get('reasons', [])[:4])}",
            max_tokens=120,
        )
        parts["boss_summary"] = boss or f"Grade {qual.get('grade')}: {qual.get('action')}"
        try:
            from app.agents.staff_supervisor import high_stakes_enabled, run_high_stakes

            if high_stakes_enabled():
                hs = run_high_stakes(
                    f"Sales deep-dive synthesis for {p.get('name') or p.get('business_name') or 'prospect'}: "
                    f"BANT {qual.get('total')}/100 grade {qual.get('grade')}. Next best action?"
                )
                if hs.get("ok") and hs.get("reply"):
                    parts["langgraph_synthesis"] = str(hs["reply"])[:500]
        except Exception:
            pass

        pid = _pid(p)
        os.makedirs(_DIR, exist_ok=True)
        md_path = os.path.join(_DIR, f"{pid}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(_render_md(p, parts))
        row = {
            "ts": int(time.time()),
            "pid": pid,
            "name": p.get("name") or p.get("business_name"),
            "phone": p.get("phone"),
            "niche": p.get("niche"),
            "city": p.get("city"),
            "score": qual.get("total"),
            "grade": qual.get("grade"),
            "md": md_path,
        }
        with open(_INDEX, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        try:
            from app.platform import team

            team.log_event(
                "swara",
                "sales_deepdive",
                f"Prospect deep-dive: {row['name']} → {row['score']}/100 (grade {row['grade']})",
            )
        except Exception:
            pass
        logger.info(
            f"[sales-team] analyzed {pid}: {qual.get('total')}/100 grade {qual.get('grade')}"
        )
        return {"ok": True, **row, "analysis": parts}
    except Exception as e:
        logger.warning(f"[sales-team] analyze fail: {e}")
        return {"ok": False, "error": str(e)[:160]}


def list_analyses(limit: int = 20) -> list[dict]:
    return _index_rows()[-limit:][::-1]


def _already_done(phone: str | None, name: str | None) -> bool:
    cutoff = time.time() - _REDO_DAYS * 86400
    for r in _index_rows():
        if r.get("ts", 0) < cutoff:
            continue
        if phone and r.get("phone") == phone:
            return True
        if name and r.get("name") == name:
            return True
    return False


async def run_auto(limit: int = 3) -> dict[str, Any]:
    """AUTO-PILOT (gated SALES_TEAM=1): top hot leads (score>=70) jin pe analysis nahi -- deep-dive.
    Daily content job se chalta. Drafts banata hai, KUCH send nahi karta."""
    if not _enabled():
        return {"ok": False, "skipped": "SALES_TEAM off"}
    try:
        leads: list = []
        try:
            from sqlalchemy import select as _select

            from app.models.base import get_async_session
            from app.models.lead import Lead

            async with get_async_session() as session:
                q = (
                    _select(Lead)
                    .where(Lead.lead_score >= 70)
                    .order_by(Lead.lead_score.desc())
                    .limit(15)
                )
                result = await session.execute(q)
                rows = result.scalars().all()
                leads = [
                    {
                        "phone": r.phone or "",
                        "email": r.email or "",
                        "name": r.company_name or "",
                        "business_name": r.company_name or "",
                        "niche": r.industry or "",
                        "city": r.city or "",
                        "website": r.website or "",
                        "lead_score": r.lead_score or 0,
                        "is_hot_lead": bool(r.is_hot_lead),
                    }
                    for r in rows
                ]
        except Exception as _db_e:
            logger.debug(f"[sales-team] DB query fallback: {_db_e}")
            from app.platform import lead_scoring

            res = await lead_scoring.top_hot_leads(15)
            leads = res.get("leads") if isinstance(res, dict) else (res or [])

        done = 0
        for lead in leads:
            if done >= max(1, min(limit, 5)):
                break
            p = lead if isinstance(lead, dict) else {}
            # Council 2026-07-03: nameless (phone-only) prospects -> BANT on "?" is
            # hallucination fodder + ~6 wasted free-LLM calls each, and every one
            # landed as C-grade junk in the approvals queue. AUTO path skips them;
            # manual analyze(p) stays open as the explicit human override.
            if not (p.get("name") or p.get("business_name")):
                continue
            if _already_done(p.get("phone"), p.get("name") or p.get("business_name")):
                continue
            r = await analyze(p)
            if r.get("ok"):
                done += 1
        return {"ok": True, "analyzed": done, "pool_size": len(leads)}
    except Exception as e:
        logger.warning(f"[sales-team] run_auto fail: {e}")
        return {"ok": False, "error": str(e)[:160]}
