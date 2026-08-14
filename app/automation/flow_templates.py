"""Flow Runner starter templates — ready-to-apply SMB automations.

The Flow Runner engine (flow_store / flow_compiler / flow_dispatch) shipped with
an EMPTY canvas: flipping FLOW_RUNNER on gave admins/customers a blank builder.
These niche-friendly starter flows make the moat immediately useful — a 1-click
apply creates a real, compile-valid flow the user can then tweak.

ALL templates use ONLY CUSTOMER_SAFE_ACTIONS (draft-only — no send / scrape /
SSRF) so they validate in BOTH the admin builder and the tenant-scoped customer
portal. Each is a linear chain (single root) ending in an Approval breakpoint to
teach the human-in-the-loop pattern. Edges use the compiler's {f, t} key shape.
Node ids are local to the flow (flow_store.save_flow assigns a fresh flow id on
apply). Import-safe, never-raise.
"""

from __future__ import annotations

import copy

# Source-of-truth templates. Keep actions inside flow_compiler.CUSTOMER_SAFE_ACTIONS
# ({content_pack, social_drafts, seo_blog_draft, brand_pulse, review_scan,
# client_report_draft}) so to_flow() output passes compile_flow(customer_safe=True).
_TEMPLATES: list[dict] = [
    {
        "tid": "daily_content",
        "name": "Roz ka Content Engine",
        "description": "Har din 7 baje AI content pack + social drafts banao, phir aapki approval pe ready.",
        "niche_hint": "all",
        "trigger": {"type": "cron", "cron": "07:00"},
        "nodes": [
            {"id": "n1", "action": "content_pack"},
            {"id": "n2", "action": "social_drafts"},
            {"id": "n3", "kind": "breakpoint"},
        ],
        "edges": [{"f": "n1", "t": "n2"}, {"f": "n2", "t": "n3"}],
    },
    {
        "tid": "weekly_reputation",
        "name": "Hafta Reputation Watch",
        "description": "Har Somwar reviews scan + brand health + client report draft — salon/clinic/restaurant jaise review-heavy niches ke liye.",
        "niche_hint": "salon, clinic, restaurant, gym",
        "trigger": {"type": "cron", "cron": "0 9 * * 1"},
        "nodes": [
            {"id": "n1", "action": "review_scan"},
            {"id": "n2", "action": "brand_pulse"},
            {"id": "n3", "action": "client_report_draft"},
            {"id": "n4", "kind": "breakpoint"},
        ],
        "edges": [{"f": "n1", "t": "n2"}, {"f": "n2", "t": "n3"}, {"f": "n3", "t": "n4"}],
    },
    {
        "tid": "festival_campaign",
        "name": "Festival / Offer Campaign Pack",
        "description": "Manual trigger — tyohar ya sale ke liye content pack + social drafts + brand pulse, ek click me draft.",
        "niche_hint": "retail, all",
        "trigger": {"type": "manual"},
        "nodes": [
            {"id": "n1", "action": "content_pack"},
            {"id": "n2", "action": "social_drafts"},
            {"id": "n3", "action": "brand_pulse"},
            {"id": "n4", "kind": "breakpoint"},
        ],
        "edges": [{"f": "n1", "t": "n2"}, {"f": "n2", "t": "n3"}, {"f": "n3", "t": "n4"}],
    },
]


def list_templates() -> list[dict]:
    """Summaries for a template picker. Source constants never mutated."""
    out: list[dict] = []
    for t in _TEMPLATES:
        out.append(
            {
                "tid": t["tid"],
                "name": t["name"],
                "description": t["description"],
                "niche_hint": t.get("niche_hint", "all"),
                "steps": len([n for n in t["nodes"] if n.get("kind") != "breakpoint"]),
                "trigger": (t.get("trigger") or {}).get("type", "manual"),
            }
        )
    return out


def get_template(tid: str) -> dict | None:
    tid = (tid or "").strip()
    for t in _TEMPLATES:
        if t["tid"] == tid:
            return copy.deepcopy(t)
    return None


def to_flow(tid: str, name_override: str = "") -> dict | None:
    """Build a fresh flow body {name, nodes, edges, trigger} from a template,
    ready for flow_store.save_flow (no id -> fresh id assigned). Deep-copied so
    the template constants are never mutated. Returns None for an unknown tid."""
    t = get_template(tid)
    if not t:
        return None
    return {
        "name": ((name_override or "").strip() or t["name"])[:120],
        "nodes": copy.deepcopy(t["nodes"]),
        "edges": copy.deepcopy(t["edges"]),
        "trigger": copy.deepcopy(t.get("trigger") or {"type": "manual"}),
    }


__all__ = ["list_templates", "get_template", "to_flow"]
