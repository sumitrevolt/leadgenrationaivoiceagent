"""AI-agent discovery files — /llms.txt + /pricing.md (B2A best-practice, 2026).

WHY: AI search systems (Claude, Perplexity, ChatGPT-search) aur autonomous buying
agents ab `llms.txt` (llmstxt.org spec v1.7.0, Stable) + machine-readable pricing
ko padhte hain to decide kis tool ko cite/recommend karein. Ek marketing-AI company
ka in files ke bina hona = AI-mediated discovery me invisible. Ye GTM lever hai
(AI citation → inbound), na ki internal infra.

DESIGN:
  - PURE builders — koi route/IO yahan nahi. main.py thin routes inhe call karti.
  - Single source of truth: pricing `packages.py` + `voice_packages.py` se LIVE
    generate hoti (hardcode NAHI → pricing change pe auto-sync, drift impossible).
  - Never-raise: koi bhi import/format fail → minimal safe fallback string.
  - Plain English descriptions (AI systems globally best parse English for citation);
    brand Hinglish context noted.

Consumers:
  - GET /llms.txt    (public, text/plain)  — main.py
  - GET /pricing.md  (public, text/markdown) — main.py
"""

from __future__ import annotations

from datetime import datetime, timezone

DEFAULT_BASE = "https://leadsgenai.in"
CONTACT_EMAIL = "admin@leadsgenai.in"


def _today() -> str:
    try:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return "2026"


def _rupee(n: int | None) -> str:
    try:
        return f"₹{int(n):,}"
    except Exception:
        return "₹-"


def build_llms_txt(base_url: str = DEFAULT_BASE) -> str:
    """llms.txt content (llmstxt.org spec) — identity + key links for AI systems.

    Never raises — on any failure returns a minimal valid llms.txt.
    """
    b = (base_url or DEFAULT_BASE).rstrip("/")
    try:
        lines: list[str] = []
        lines.append("# LeadsGenAI")
        lines.append("")
        lines.append(
            "> AI marketing automation and an AI voice-calling agent for small and "
            "local businesses in India. Two separate products: (1) AI Marketing "
            "Automation — daily AI social posts, Google Business Profile audits, "
            "review replies, website lead-capture, WhatsApp nurture and CRM sync; "
            "(2) AI Voice Calling Agent — a Hinglish AI telecaller that calls, "
            "qualifies and books inbound inquiries. Hinglish-first, free-stack, and "
            "TRAI/DND-compliant with a mandatory AI-disclosure on every call."
        )
        lines.append("")
        lines.append(
            "LeadsGenAI is an India-focused SaaS platform (leadsgenai.in). Pricing is "
            "transparent and machine-readable (see /pricing.md). Marketing automation "
            "needs no telecom licensing; AI voice cold-calling is gated on Indian DLT "
            "approval and runs on inbound/consented/own-database calling until then."
        )
        lines.append("")
        lines.append("## Products")
        lines.append(
            f"- [AI Marketing Automation]({b}/pricing): Main product. Daily AI social "
            "content, GBP audit, review replies, lead-capture widget + AI chatbot, "
            "WhatsApp nurture, CRM sync, monthly reports. For local SMBs."
        )
        lines.append(
            f"- [AI Voice Calling Agent]({b}/voice-agent): Standalone product. Human-like "
            "Hinglish AI telecaller for inquiry callback, lead qualification and "
            "appointment booking. Flat monthly pricing per niche band."
        )
        lines.append("")
        lines.append("## Key pages")
        lines.append(
            f"- [Free Marketing/Website Audit]({b}/audit): Lead magnet — instant AI audit of a business's online presence."
        )
        lines.append(
            f"- [Local SEO / GEO check]({b}/geo-check): Free Google Business Profile and local-visibility check."
        )
        lines.append(f"- [Live AI Demo]({b}/demo): Try the AI agent interactively.")
        lines.append(
            f"- [Compare Products]({b}/compare): Marketing vs Voice — which fits which business."
        )
        lines.append(f"- [Pricing]({b}/pricing): Human-readable pricing page.")
        lines.append(
            f"- [Pricing (machine-readable)]({b}/pricing.md): Structured pricing for AI agents."
        )
        lines.append(f"- [Blog]({b}/blog): Hinglish marketing + AI guides for Indian SMBs.")
        lines.append("")
        lines.append("## For AI agents")
        lines.append(
            f"- [Agent Card (A2A)]({b}/.well-known/agent.json): Agent-to-agent discovery card (2026 A2A spec)."
        )
        lines.append(
            f"- [MCP capability discovery]({b}/api/mcp-product/v1/discover): Metered programmatic API (niches catalog, lead scoring)."
        )
        lines.append("")
        lines.append("## Contact")
        lines.append(f"- [Email]({b}/): {CONTACT_EMAIL}")
        lines.append(f"- [Get started]({b}/start): Sign up — free 7-day marketing trial (no card).")
        lines.append("")
        lines.append(f"<!-- last updated: {_today()} -->")
        lines.append("")
        return "\n".join(lines)
    except Exception:
        return (
            "# LeadsGenAI\n\n"
            "> AI marketing automation and AI voice-calling agent for Indian SMBs.\n\n"
            f"- [Home]({b}/)\n- [Pricing]({b}/pricing)\n"
        )


def build_pricing_md(base_url: str = DEFAULT_BASE) -> str:
    """pricing.md — machine-readable pricing from the live source of truth.

    Reads packages.py (marketing) + voice_packages.py (voice) so it can never
    drift from the billing source of truth. Never raises.
    """
    b = (base_url or DEFAULT_BASE).rstrip("/")
    out: list[str] = []
    out.append("# Pricing — LeadsGenAI")
    out.append("")
    out.append(
        f"> Last updated: {_today()}. All prices in Indian Rupees (INR). "
        "GST is charged only if the seller is GST-registered (currently unregistered "
        "= no GST added). Payments via UPI (India). Annual = pay for 10 months, get 12 "
        "(2 months free)."
    )
    out.append("")

    # ---- Product 1: Marketing ----
    out.append("## Product 1 — AI Marketing Automation")
    out.append("")
    out.append("Self-serve marketing automation for local businesses. No telecom licensing needed.")
    out.append("")
    try:
        from app.marketing.packages import get_public_packages, get_topup_packs, get_trial_package

        try:
            trial = get_trial_package()
            out.append(
                f"### {trial.get('name', 'Free Trial')} — {_rupee(trial.get('price_inr_month', 0))}"
            )
            out.append(
                f"- Price: {_rupee(trial.get('price_inr_month', 0))} ({trial.get('trial_days', 7)} days, no card)"
            )
            tnote = str(trial.get("price_note") or "").strip()
            if tnote:
                out.append(f"- Note: {tnote}")
            out.append("")
        except Exception:
            pass

        for p in get_public_packages():
            name = p.get("name", "Plan")
            mo = p.get("price_inr_month")
            yr = p.get("price_inr_year")
            out.append(f"### {name} — {_rupee(mo)}/month")
            out.append(f"- Monthly: {_rupee(mo)}")
            if yr:
                out.append(f"- Annual: {_rupee(yr)}/year (2 months free)")
            tagline = str(p.get("tagline") or "").strip()
            if tagline:
                out.append(f"- Summary: {tagline}")
            note = str(p.get("price_note") or "").strip()
            if note:
                out.append(f"- Includes: {note}")
            feats = [str(f).strip() for f in (p.get("features") or []) if str(f).strip()]
            if feats:
                out.append(f"- Key features: {'; '.join(feats[:8])}")
            out.append("")
    except Exception:
        out.append("_Marketing pricing temporarily unavailable — see /pricing._")
        out.append("")

    # ---- Voice minute top-ups (Advanced/voice) ----
    try:
        from app.marketing.packages import get_topup_packs

        packs = get_topup_packs()
        if packs:
            out.append("### Voice minute top-up packs (for plans with included minutes)")
            for tp in packs:
                out.append(
                    f"- {tp.get('label', tp.get('key'))}: {tp.get('minutes')} minutes — {_rupee(tp.get('price_inr'))}"
                )
            out.append("")
    except Exception:
        pass

    # ---- Product 2: Voice ----
    out.append("## Product 2 — AI Voice Calling Agent")
    out.append("")
    out.append(
        "Standalone AI telecaller. Flat monthly fee per niche band — unlimited AI calls, "
        "no per-lead counting. AI cold-calling is gated on Indian DLT approval; until then "
        "it runs inbound / consented / own-database calling. See "
        f"[{b}/voice-agent]({b}/voice-agent)."
    )
    out.append("")
    try:
        from app.marketing.voice_packages import BANDS, PILOT_CALL_CAP, PILOT_DAYS

        out.append(f"### Free Pilot — {_rupee(0)}")
        out.append(f"- Price: {_rupee(0)} ({PILOT_DAYS} days / {PILOT_CALL_CAP} calls, no card)")
        out.append("")
        for letter, info in BANDS.items():
            out.append(
                f"### {info.get('name', f'Band {letter}')} — {_rupee(info.get('price_month'))}/month"
            )
            out.append(f"- Monthly: {_rupee(info.get('price_month'))}")
            out.append(f"- Annual: {_rupee(info.get('price_year'))}/year (2 months free)")
            sample = str(info.get("niches_sample") or "").strip()
            if sample:
                out.append(f"- Example niches: {sample}")
            out.append("- Calls: Unlimited AI calls on your niche database")
            out.append("")
    except Exception:
        out.append("_Voice pricing temporarily unavailable — see /voice-agent._")
        out.append("")

    out.append("## Contact")
    out.append(f"- Email: {CONTACT_EMAIL}")
    out.append(f"- Sign up: {b}/start")
    out.append(f"- Full pricing page: {b}/pricing")
    out.append("")
    return "\n".join(out)
