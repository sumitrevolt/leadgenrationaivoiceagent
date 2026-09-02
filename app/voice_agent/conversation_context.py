"""Bounded structured conversation context for Swara (tenant-isolated).

Versioned schema. Masks phones. Never includes raw recordings.
Server owns pricing/rules — model cannot overwrite approved facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CONTEXT_SCHEMA_VERSION = "swara_ctx_v1"
_MAX_TURNS = 10
_PHONE_RE = re.compile(r"(?:\+?91[\s-]?)?[6-9]\d{9}")


def mask_phones(text: str) -> str:
    def _sub(m: re.Match[str]) -> str:
        raw = re.sub(r"\D", "", m.group(0))
        if len(raw) >= 10:
            return f"***{raw[-4:]}"
        return "***"

    try:
        return _PHONE_RE.sub(_sub, text or "")
    except Exception:
        return text or ""


@dataclass
class ConversationContext:
    schema_version: str = CONTEXT_SCHEMA_VERSION
    tenant_id: str = ""
    business_name: str = ""
    campaign_id: str = ""
    lead_id: str = ""
    niche: str = ""
    stage: str = "opening"
    facts: dict[str, str] = field(default_factory=dict)
    approved_pricing: dict[str, Any] = field(default_factory=dict)
    approved_services: list[str] = field(default_factory=list)
    opt_out: bool = False
    tools_called: list[str] = field(default_factory=list)
    recent_turns: list[dict[str, str]] = field(default_factory=list)
    older_summary: str = ""
    active_route: str = ""
    active_model: str = ""

    def add_turn(self, role: str, content: str) -> None:
        role = role if role in ("user", "assistant", "system") else "user"
        text = mask_phones((content or "").strip())
        if not text:
            return
        self.recent_turns.append({"role": role, "content": text})
        # Keep last N; summarize overflow into older_summary (bounded).
        while len(self.recent_turns) > _MAX_TURNS:
            old = self.recent_turns.pop(0)
            snippet = f"{old.get('role')}: {(old.get('content') or '')[:80]}"
            if self.older_summary:
                self.older_summary = (self.older_summary + " | " + snippet)[-400:]
            else:
                self.older_summary = snippet[:400]

    def set_fact(self, key: str, value: str, *, server_owned: bool = False) -> None:
        """Model-suggested facts are soft; server_owned pricing keys are protected."""
        k = (key or "").strip().lower()[:40]
        if not k:
            return
        if k.startswith("price") or k in ("pricing", "plan", "mrp", "offer"):
            if not server_owned:
                return  # model cannot overwrite pricing
        self.facts[k] = mask_phones(str(value or ""))[:120]

    def load_server_pricing(self) -> None:
        """Pull approved public packages — server authority."""
        try:
            from app.marketing.packages import get_public_packages

            pkgs = get_public_packages() or []
            approved: dict[str, Any] = {}
            services: list[str] = []
            for p in pkgs:
                if not isinstance(p, dict):
                    continue
                pid = str(p.get("id") or p.get("key") or "").strip()
                name = str(p.get("name") or pid).strip()
                price = p.get("price_inr") or p.get("price") or p.get("monthly_price")
                if pid:
                    approved[pid] = {"name": name, "price_inr": price}
                if name:
                    services.append(name)
            self.approved_pricing = approved
            self.approved_services = services[:12]
        except Exception:
            # Hard-coded fail-safe from product charter (Marketing Main / Combo).
            self.approved_pricing = {
                "main": {"name": "AI Automated Marketing Main", "price_inr": 1999},
                "combo": {"name": "AI Automated Marketing Combo/Advanced", "price_inr": 5999},
            }
            self.approved_services = [
                "AI Automated Marketing",
                "AI Voice Calling Agent (standalone)",
            ]

    def prompt_block(self) -> str:
        """Compact system inject — no raw recordings, phones masked."""
        lines = [
            f"[CTX {self.schema_version} tenant={self.tenant_id or 'n/a'}]",
            f"business={self.business_name or 'LeadsGen AI'} niche={self.niche} stage={self.stage}",
        ]
        if self.approved_pricing:
            price_bits = []
            for k, v in list(self.approved_pricing.items())[:6]:
                if isinstance(v, dict):
                    price_bits.append(f"{v.get('name', k)}:₹{v.get('price_inr', '?')}")
                else:
                    price_bits.append(f"{k}:{v}")
            lines.append("APPROVED_PRICING (server-owned, do not invent): " + "; ".join(price_bits))
        if self.facts:
            fact_s = "; ".join(f"{k}={v}" for k, v in list(self.facts.items())[:8])
            lines.append("facts: " + fact_s)
        if self.tools_called:
            lines.append("tools_called: " + ",".join(self.tools_called[-6:]))
        if self.opt_out:
            lines.append("OPT_OUT=true — do not sell; confirm suppression and end.")
        if self.older_summary:
            lines.append("earlier: " + self.older_summary[:300])
        if self.active_route:
            lines.append(f"route={self.active_route} model={self.active_model}")
        lines.append(
            "RULES: short Hindi/Hinglish, one question, no markdown; "
            "pricing only from APPROVED_PRICING; never claim booking without tool."
        )
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tenant_id": self.tenant_id,
            "business_name": self.business_name,
            "campaign_id": self.campaign_id,
            "lead_id": self.lead_id,
            "niche": self.niche,
            "stage": self.stage,
            "facts": dict(self.facts),
            "approved_pricing": dict(self.approved_pricing),
            "approved_services": list(self.approved_services),
            "opt_out": self.opt_out,
            "tools_called": list(self.tools_called),
            "recent_turns": list(self.recent_turns),
            "older_summary": self.older_summary,
            "active_route": self.active_route,
            "active_model": self.active_model,
        }


def build_context(
    *,
    tenant_id: str = "",
    business_name: str = "",
    niche: str = "",
    campaign_id: str = "",
    lead_id: str = "",
    history: list[dict[str, str]] | None = None,
) -> ConversationContext:
    ctx = ConversationContext(
        tenant_id=tenant_id or "",
        business_name=business_name or "",
        niche=niche or "",
        campaign_id=campaign_id or "",
        lead_id=lead_id or "",
    )
    ctx.load_server_pricing()
    for m in history or []:
        if isinstance(m, dict):
            ctx.add_turn(str(m.get("role") or "user"), str(m.get("content") or ""))
    return ctx
