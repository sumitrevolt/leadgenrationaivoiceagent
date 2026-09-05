"""app/api/product_consoles.py — Archify-styled customer consoles (P1 voice + P2 marketing).

Two enterprise consoles, ONE shared design system (frontend/archify_console.css,
derived from tt-a1i/archify DESIGN.md — "The Evidence Console"):

  GET /app/voice-console      -> Product 1: Customer Configuration & Knowledge Panel
  GET /app/marketing-console  -> Product 2: Marketing Product Launch Panel

Both are tenant-scoped by `require_customer` (JWT role=customer -> client_id).

Design contract (matches Archify + project conventions):
  - **Truth before spectacle.** Every count, node state and "connected" claim is
    derived from a real source (clients_store, KB stats, social token vault).
    Nothing is invented. Missing data returns honest zeros, never placeholders.
  - **Never 500.** Every handler is guarded; failures degrade to a partial payload
    with `ok:true` and a `degraded` note, or an explicit 4xx for bad input.
  - **Reuse, don't rebuild.** Social OAuth -> app.api.social_oauth; credential
    store -> app.social_engine.vault (Fernet at-rest); knowledge -> app.voice_agent
    .knowledge_base (namespaced `client:<id>`); client record -> clients_store.

Mounted from app/main.py inside a guarded try (see CHECK-MOUNT comment at EOF).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.customer_auth import require_customer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Product Consoles"])

_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
_CSS_FILE = _FRONTEND_DIR / "archify_console.css"
_JS_FILE = _FRONTEND_DIR / "archify_console.js"
_VOICE_HTML = _FRONTEND_DIR / "voice_console.html"
_MARKETING_HTML = _FRONTEND_DIR / "marketing_console.html"
_ARCHIFY_HOME_HTML = _FRONTEND_DIR / "archify_console_home.html"
_ARCHIFY_MKT_HTML = _FRONTEND_DIR / "archify_marketing.html"
_ARCHIFY_CUST_HTML = _FRONTEND_DIR / "archify_customer.html"
_ARCHIFY_DS_CSS = _FRONTEND_DIR / "archify-design-system.css"
_ARCHIFY_LAYOUT_CSS = _FRONTEND_DIR / "archify-layout.css"
_ARCHIFY_APP_JS = _FRONTEND_DIR / "archify-app.js"
_SEED_CUST_JS = _FRONTEND_DIR / "seed-customer.js"
_SEED_MKT_JS = _FRONTEND_DIR / "seed-marketing.js"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kb_namespace(client_id: str) -> str:
    """Canonical per-tenant KB namespace (matches kb_personalize / chatbot)."""
    return f"client:{(client_id or '').strip()}"


# =========================================================================== #
# Per-tenant console config store  (jsonl, latest-wins, never raises)          #
# =========================================================================== #
def _config_path() -> str:
    """Resolved per call (never frozen at import) so tests can monkeypatch."""
    try:
        from app.platform import runtime_data_authority as _auth

        return str(
            _auth.resolve_store_path(
                store_id="consoles.config",
                legacy_path=Path("data") / "console_configs.jsonl",
                target_segments=("customers", "console_configs.jsonl"),
            )
        )
    except Exception:
        return os.path.join("data", "console_configs.jsonl")


def _read_config(client_id: str) -> dict[str, Any]:
    """Latest record for this client, or {} if none. Never raises."""
    cid = (client_id or "").strip()
    if not cid:
        return {}
    try:
        path = _config_path()
        if not os.path.exists(path):
            return {}
        found: dict[str, Any] = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if str(row.get("client_id")) == cid:
                    found = row
        return found
    except Exception as e:  # pragma: no cover
        logger.warning(f"[consoles] read config failed: {e}")
        return {}


def _write_config(client_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge `patch` into the client's record and append. Returns new record.
    Append-only (jsonl-first) so history is preserved — same contract as
    clients_store / social vault. Never raises (returns best-effort record)."""
    cid = (client_id or "").strip()
    current = _read_config(cid)
    merged = dict(current)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    merged["client_id"] = cid
    merged["updated_at"] = _now_iso()
    try:
        path = _config_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(merged, ensure_ascii=False) + "\n")
    except Exception as e:  # pragma: no cover
        logger.warning(f"[consoles] write config failed: {e}")
    return merged


# =========================================================================== #
# Call-automation template gallery                                            #
# Preview-before-apply. Each `spec` is directly consumable by                  #
# app.voice_agent.flow_builder.build_flow_from_spec().                        #
# =========================================================================== #
CALL_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "inbound_faq",
        "name": "Inbound Enquiry & FAQ",
        "category": "Inbound",
        "description": (
            "Answers incoming calls about pricing, services, timings and location "
            "strictly from your knowledge base, then captures the caller's detail."
        ),
        "channels": ["inbound"],
        "steps": [
            "Greet with business name and offer help",
            "Answer from knowledge base only — no invented facts",
            "Capture name + requirement + preferred callback time",
            "Offer appointment booking if the caller is qualified",
            "Close with summary and next step",
        ],
        "spec": {
            "label": "Inbound Enquiry",
            "entry": "greeting",
            "nodes": [
                {
                    "id": "greeting", "type": "speak",
                    "text": "Namaste, {{business_name}} mein aapka swagat hai. "
                            "Bataiye main kaise madad kar sakta hoon?",
                },
                {
                    "id": "answer", "type": "kb_answer", "kb": True,
                    "fallback": "Main iski confirm karwake aapko wapas call karungi.",
                },
                {"id": "capture", "type": "collect", "fields": ["name", "requirement", "callback_time"]},
                {"id": "qualify", "type": "branch", "on": "interest", "yes": "book", "no": "close"},
                {"id": "book", "type": "book", "calendar": True},
                {"id": "close", "type": "end", "text": "Dhanyavaad. Humari team aapse jaldi sampark karegi."},
            ],
        },
        "dlt_note": "Inbound — no DLT template required. Consent recorded on first call.",
    },
    {
        "id": "lead_qualify",
        "name": "Outbound Lead Qualification",
        "category": "Outbound",
        "description": (
            "Calls fresh leads within minutes of enquiry, qualifies on budget, "
            "timeline and authority, then routes hot leads to you instantly."
        ),
        "channels": ["outbound"],
        "steps": [
            "Reference the source of the enquiry",
            "Confirm identity and consent to continue",
            "Ask budget / timeline / decision-maker questions",
            "Score the lead and route hot ones immediately",
            "Log disposition and schedule follow-up",
        ],
        "spec": {
            "label": "Lead Qualification",
            "entry": "intro",
            "nodes": [
                {
                    "id": "intro", "type": "speak",
                    "text": "Namaste, main {{business_name}} se bol rahi hoon. "
                            "Aapne hamari website par enquiry chhodhi thi.",
                },
                {
                    "id": "consent", "type": "consent",
                    "text": "Kya main 2 minute aapki requirement samajh sakti hoon?",
                },
                {"id": "budget", "type": "ask", "field": "budget"},
                {"id": "timeline", "type": "ask", "field": "timeline"},
                {"id": "authority", "type": "ask", "field": "decision_maker"},
                {
                    "id": "route", "type": "branch", "on": "score",
                    "hot": "transfer", "nurture": "nurture", "cold": "end",
                },
                {"id": "transfer", "type": "transfer", "to": "owner"},
                {"id": "nurture", "type": "schedule", "after_hours": "next_business_day"},
                {"id": "end", "type": "end"},
            ],
        },
        "dlt_note": "Cold outbound requires an approved DLT template + consent trail (TRAI).",
    },
    {
        "id": "appointment_reminder",
        "name": "Appointment Confirmation & Reminder",
        "category": "Retention",
        "description": "Confirms upcoming appointments, handles reschedules, and reduces no-shows.",
        "channels": ["outbound"],
        "steps": [
            "State the appointment date and time",
            "Confirm, reschedule or cancel",
            "Share location or joining instructions",
            "Send a written confirmation",
        ],
        "spec": {
            "label": "Appointment Reminder",
            "entry": "state",
            "nodes": [
                {"id": "state", "type": "speak", "text": "Aapki appointment {{date}} ko {{time}} baje hai."},
                {"id": "confirm", "type": "choice", "options": ["confirm", "reschedule", "cancel"]},
                {"id": "reschedule", "type": "collect", "fields": ["preferred_slot"]},
                {"id": "directions", "type": "speak", "text": "Aapka pata: {{address}}."},
                {"id": "end", "type": "end"},
            ],
        },
        "dlt_note": "Service call — permitted with prior consent on record.",
    },
    {
        "id": "payment_followup",
        "name": "Payment & Invoice Follow-up",
        "category": "Collections",
        "description": "Polite, scripted follow-up on pending invoices with a payment link hand-off.",
        "channels": ["outbound"],
        "steps": [
            "Reference invoice number and outstanding amount",
            "Confirm receipt of the invoice",
            "Offer the payment link and confirm a date",
            "Escalate a promise-to-pay exception to you",
        ],
        "spec": {
            "label": "Payment Follow-up",
            "entry": "reference",
            "nodes": [
                {
                    "id": "reference", "type": "speak",
                    "text": "Invoice {{invoice_no}} ke {{amount}} rupaye pending hain.",
                },
                {"id": "received", "type": "choice", "options": ["received", "not_received"]},
                {"id": "link", "type": "send_link", "kind": "payment"},
                {"id": "promise", "type": "collect", "fields": ["payment_date"]},
                {"id": "end", "type": "end"},
            ],
        },
        "dlt_note": "Transactional — permitted against an existing obligation.",
    },
    {
        "id": "reactivation",
        "name": "Dormant Customer Reactivation",
        "category": "Growth",
        "description": "Re-engages customers who have not purchased recently with a targeted offer.",
        "channels": ["outbound"],
        "steps": [
            "Reference the last interaction warmly",
            "Present the reactivation offer",
            "Handle the two most common objections",
            "Book or transfer on acceptance",
        ],
        "spec": {
            "label": "Reactivation",
            "entry": "warm",
            "nodes": [
                {"id": "warm", "type": "speak", "text": "Kaafi time ho gaya — aapko yaad kar rahe the."},
                {"id": "offer", "type": "speak", "text": "Aaj ke liye hamare paas ek special offer hai."},
                {"id": "objection", "type": "kb_answer", "kb": True},
                {"id": "accept", "type": "branch", "on": "accepted", "yes": "book", "no": "end"},
                {"id": "book", "type": "book", "calendar": True},
                {"id": "end", "type": "end"},
            ],
        },
        "dlt_note": "Cold outbound — DLT template + consent required.",
    },
    {
        "id": "survey_nps",
        "name": "Post-service Feedback (NPS)",
        "category": "Quality",
        "description": "Collects a 0-10 recommendation score plus one verbatim reason after service.",
        "channels": ["outbound"],
        "steps": [
            "Ask permission for a 30-second survey",
            "Capture the 0-10 score",
            "Ask the single most useful follow-up question",
            "Thank and close; flag detractors to you",
        ],
        "spec": {
            "label": "NPS Survey",
            "entry": "permission",
            "nodes": [
                {
                    "id": "permission", "type": "consent",
                    "text": "Kya aap 30 second ka feedback de sakte hain?",
                },
                {"id": "score", "type": "collect", "fields": ["nps_score"], "validate": "0-10"},
                {"id": "reason", "type": "collect", "fields": ["reason"]},
                {
                    "id": "route", "type": "branch", "on": "nps_score",
                    "detractor": "alert", "promoter": "thanks",
                },
                {"id": "alert", "type": "notify", "to": "owner"},
                {"id": "thanks", "type": "end", "text": "Dhanyavaad aapke feedback ke liye."},
            ],
        },
        "dlt_note": "Service/survey call — permitted with prior consent.",
    },
]

_TEMPLATES_BY_ID = {t["id"]: t for t in CALL_TEMPLATES}


# =========================================================================== #
# Call-automation EVENT SLOTS
# Pattern source: Tata Tele Business Services (TTBS) Smartflo — configuration is
# expressed as `event -> asset` rows (incoming-missed-to-agent, answered-to-caller,
# ...) with regulatory status shown inline, NOT as one opaque settings blob.
# Each slot binds a call template to a lifecycle event.
# =========================================================================== #
EVENT_SLOTS: list[dict[str, Any]] = [
    {
        "key": "inbound_answered",
        "label": "Inbound answered",
        "event": "A customer calls and the call is picked up.",
        "channels": ["voice"],
        "requires_dlt": False,
        "recommended": ["inbound_faq"],
    },
    {
        "key": "inbound_missed",
        "label": "Inbound missed",
        "event": "A customer calls and nobody answers.",
        "channels": ["voice", "sms", "whatsapp"],
        "requires_dlt": True,
        "recommended": ["inbound_faq"],
    },
    {
        "key": "lead_created",
        "label": "New lead captured",
        "event": "A lead arrives from the website, mini-site or a campaign.",
        "channels": ["voice"],
        "requires_dlt": False,
        "recommended": ["lead_qualify"],
    },
    {
        "key": "outbound_no_answer",
        "label": "Outbound not answered",
        "event": "We called and the customer did not pick up.",
        "channels": ["sms", "whatsapp"],
        "requires_dlt": True,
        "recommended": ["appointment_reminder"],
    },
    {
        "key": "appointment_due",
        "label": "Appointment upcoming",
        "event": "An appointment is scheduled within the reminder window.",
        "channels": ["voice", "sms"],
        "requires_dlt": False,
        "recommended": ["appointment_reminder"],
    },
    {
        "key": "payment_due",
        "label": "Invoice overdue",
        "event": "An invoice passes its due date.",
        "channels": ["voice", "sms"],
        "requires_dlt": False,
        "recommended": ["payment_followup"],
    },
    {
        "key": "customer_dormant",
        "label": "Customer went dormant",
        "event": "No interaction for the configured inactivity window.",
        "channels": ["voice"],
        "requires_dlt": True,
        "recommended": ["reactivation"],
    },
    {
        "key": "service_completed",
        "label": "Service completed",
        "event": "A job or appointment is marked complete.",
        "channels": ["voice"],
        "requires_dlt": False,
        "recommended": ["survey_nps"],
    },
]

_EVENT_SLOT_KEYS = {s["key"] for s in EVENT_SLOTS}


def _default_bindings() -> list[dict[str, Any]]:
    """Every slot starts unbound. The console shows that honestly — an unbound
    event is inert, it does not silently fall back to a guessed script."""
    return [{"event": s["key"], "template_id": "", "channel": (s["channels"] or ["voice"])[0],
             "enabled": False} for s in EVENT_SLOTS]


def _normalize_bindings(raw: Any) -> list[dict[str, Any]]:
    """Coerce stored bindings onto the current slot manifest. Unknown slots and
    unknown template ids are dropped so a stale record can never reference a
    template that no longer exists."""
    base = {b["event"]: b for b in _default_bindings()}
    for item in (raw or []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("event") or "").strip()
        if key not in base:
            continue
        tid = str(item.get("template_id") or "").strip()
        if tid and tid not in _TEMPLATES_BY_ID:
            tid = ""
        base[key] = {
            "event": key,
            "template_id": tid,
            "channel": str(item.get("channel") or base[key]["channel"]).strip().lower(),
            "enabled": bool(item.get("enabled")) and bool(tid),
        }
    return [base[s["key"]] for s in EVENT_SLOTS]


# =========================================================================== #
# Readiness — derived from real evidence only                                 #
# =========================================================================== #
def _readiness(client: dict[str, Any], cfg: dict[str, Any], kb: dict[str, Any],
               conns: dict[str, Any], product: str) -> dict[str, Any]:
    """Compute the provisioning ladder. Every `done` is backed by real data."""
    business = cfg.get("business") or {}
    auto = cfg.get("automation") or {}
    mk = cfg.get("marketing") or {}

    name_ok = bool(str(business.get("business_name") or client.get("business_name") or "").strip())
    hours_ok = bool(business.get("business_hours"))
    kb_ok = int(kb.get("chunks") or 0) > 0
    conn_ok = int(conns.get("connected") or 0) > 0
    tmpl_ok = bool(str(auto.get("template_id") or "").strip())

    if product == "voice":
        steps = [
            {"id": "business", "title": "Business profile",
             "detail": "Name, hours, services and language the agent will use.",
             "done": name_ok and hours_ok, "target": "business"},
            {"id": "knowledge", "title": "Train your knowledge",
             "detail": "Add FAQs, pricing and policies. The agent answers only from this.",
             "done": kb_ok, "target": "knowledge"},
            {"id": "connections", "title": "Connect a channel",
             "detail": "Link at least one social or messaging account.",
             "done": conn_ok, "target": "connections"},
            {"id": "automation", "title": "Choose a call template",
             "detail": "Pick a scripted flow and activate call automation.",
             "done": tmpl_ok, "target": "automation"},
        ]
    else:
        steps = [
            {"id": "business", "title": "Business profile",
             "detail": "Confirms what the marketing engine promotes.",
             "done": name_ok, "target": "business"},
            {"id": "knowledge", "title": "Brand knowledge",
             "detail": "Gives the content engine accurate material to work from.",
             "done": kb_ok, "target": "knowledge"},
            {"id": "connections", "title": "Connect publishing channels",
             "detail": "At least one channel is required before launch.",
             "done": conn_ok, "target": "connections"},
            {"id": "launch", "title": "Launch the product",
             "detail": "Start automated content and campaign delivery.",
             "done": bool(mk.get("active")), "target": "launch"},
        ]

    done_n = sum(1 for s in steps if s["done"])
    # First incomplete step is "active"; nothing is "blocked" unless a hard gate fails.
    active_set = False
    gates: list[dict[str, str]] = []
    for s in steps:
        if s["done"]:
            s["state"] = "done"
        elif not active_set:
            s["state"] = "active"
            active_set = True
        else:
            s["state"] = "todo"

    if product == "voice" and tmpl_ok and not kb_ok:
        gates.append({
            "severity": "warn",
            "message": "A call template is selected but the knowledge base is empty. "
                       "The agent will fall back to a safe hand-off on every question.",
        })
    if product == "marketing" and bool(mk.get("active")) and not conn_ok:
        gates.append({
            "severity": "error",
            "message": "Marketing is marked active but no channel is connected. "
                       "Nothing can be published until you connect one.",
        })
        for s in steps:
            if s["id"] == "launch":
                s["state"] = "blocked"

    return {
        "steps": steps,
        "done": done_n,
        "total": len(steps),
        "percent": int(round(done_n * 100 / max(1, len(steps)))),
        "gates": gates,
    }


# =========================================================================== #
# Evidence adapters (thin, guarded wrappers over existing modules)            #
# =========================================================================== #
def _kb_evidence(client_id: str, cfg: dict[str, Any]) -> dict[str, Any]:
    ns = _kb_namespace(client_id)
    out: dict[str, Any] = {"namespace": ns, "chunks": 0, "backend": "unavailable",
                           "sources": list(cfg.get("kb_sources") or [])}
    try:
        from app.voice_agent.knowledge_base import get_knowledge_base

        kb = get_knowledge_base()
        st = kb.stats(ns) or {}
        out["chunks"] = int(st.get("chunks") or 0)
        out["backend"] = str(st.get("backend") or "unknown")
    except Exception as e:
        logger.warning(f"[consoles] kb stats unavailable: {e}")
        out["backend"] = "unavailable"
    return out


def _kb_index(client_id: str):
    """Best-effort handle on the tenant's index (for source deletion)."""
    try:
        from app.voice_agent.knowledge_base import get_knowledge_base

        return get_knowledge_base()._get_index(_kb_namespace(client_id))
    except Exception as e:
        logger.warning(f"[consoles] kb index unavailable: {e}")
        return None


def _connections_evidence(client_id: str) -> dict[str, Any]:
    """Merge OAuth readiness (social_oauth) with real vault-backed health
    (platform.integration_status). Never leaks tokens."""
    platforms: list[dict[str, Any]] = []
    try:
        from app.api.social_oauth import (
            _ENV_APPROVED_FLAGS,  # noqa: PLC2701  (intentional: reuse readiness source)
            _OWNER_ACTION_NOTES,
            _REQUIRED_SCOPES,
            _authorize_wired,
            _creds_missing_reason,
            _oauth_approved,
        )

        for platform in _ENV_APPROVED_FLAGS.keys():
            env_ok = bool(_oauth_approved(platform))
            wired = bool(_authorize_wired(platform))
            ready = env_ok and wired
            if ready:
                blocker = ""
            elif env_ok and not wired:
                blocker = _creds_missing_reason(platform)
            else:
                blocker = _OWNER_ACTION_NOTES.get(platform, "")
            platforms.append({
                "platform": platform,
                "oauth_ready": ready,
                "scopes_required": _REQUIRED_SCOPES.get(platform, []),
                "external_blocker": blocker,
                "status": "never_configured",
                "label": "Not connected",
                "action_required": False,
                "recommended_action": "",
            })
    except Exception as e:
        logger.warning(f"[consoles] oauth readiness unavailable: {e}")

    connected = 0
    try:
        from app.platform import integration_status

        for row in integration_status.customer_integration_statuses(client_id) or []:
            disp = str(row.get("integration") or "")
            key = _display_to_key(disp)
            hit = next((p for p in platforms if p["platform"] == key), None)
            if hit is None:
                continue
            hit.update({
                "status": row.get("status"),
                "label": row.get("label"),
                "action_required": bool(row.get("action_required")),
                "recommended_action": row.get("recommended_action"),
            })
            if str(row.get("status")) == "healthy":
                connected += 1
    except Exception as e:
        logger.warning(f"[consoles] integration status unavailable: {e}")

    return {"platforms": platforms, "connected": connected, "total": len(platforms)}


def _display_to_key(display: str) -> str:
    return {
        "Facebook": "facebook",
        "Instagram": "instagram",
        "LinkedIn": "linkedin",
        "Google Business Profile": "gbp",
        "X (Twitter)": "x",
        "YouTube": "youtube",
    }.get(display, display.lower())


# =========================================================================== #
# Static surfaces                                                             #
# =========================================================================== #
@router.get("/static/archify_console.css", include_in_schema=False)
async def console_css():
    """Shared Archify design system. Served from frontend/."""
    if not _CSS_FILE.exists():
        raise HTTPException(status_code=404, detail="design system not found")
    return FileResponse(str(_CSS_FILE), media_type="text/css")


@router.get("/static/archify_console.js", include_in_schema=False)
async def console_js():
    """Shared console runtime (nav, system map, renderers). Served from frontend/."""
    if not _JS_FILE.exists():
        raise HTTPException(status_code=404, detail="console runtime not found")
    return FileResponse(str(_JS_FILE), media_type="application/javascript")


@router.get("/app/voice-console", include_in_schema=False)
async def voice_console_page():
    """Product 1 — Customer Configuration & Knowledge Panel."""
    if not _VOICE_HTML.exists():
        raise HTTPException(status_code=404, detail="voice console not found")
    return FileResponse(str(_VOICE_HTML), media_type="text/html")


@router.get("/app/marketing-console", include_in_schema=False)
async def marketing_console_page():
    """Product 2 — Marketing Product Launch Panel."""
    if not _MARKETING_HTML.exists():
        raise HTTPException(status_code=404, detail="marketing console not found")
    return FileResponse(str(_MARKETING_HTML), media_type="text/html")


@router.get("/app/archify", include_in_schema=False)
async def archify_home_page():
    """Archify Enterprise Console Home."""
    if not _ARCHIFY_HOME_HTML.exists():
        raise HTTPException(status_code=404, detail="archify home not found")
    return FileResponse(str(_ARCHIFY_HOME_HTML), media_type="text/html")


@router.get("/app/archify/marketing", include_in_schema=False)
async def archify_marketing_page():
    """Archify Dashboard 2 — Marketing Product Launch Panel."""
    if not _ARCHIFY_MKT_HTML.exists():
        raise HTTPException(status_code=404, detail="archify marketing not found")
    return FileResponse(str(_ARCHIFY_MKT_HTML), media_type="text/html")


@router.get("/app/archify/customer", include_in_schema=False)
async def archify_customer_page():
    """Archify Dashboard 1 — Customer Configuration & Knowledge Panel."""
    if not _ARCHIFY_CUST_HTML.exists():
        raise HTTPException(status_code=404, detail="archify customer not found")
    return FileResponse(str(_ARCHIFY_CUST_HTML), media_type="text/html")


@router.get("/archify-design-system.css", include_in_schema=False)
async def archify_ds_css():
    if not _ARCHIFY_DS_CSS.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(_ARCHIFY_DS_CSS), media_type="text/css")


@router.get("/archify-layout.css", include_in_schema=False)
async def archify_layout_css():
    if not _ARCHIFY_LAYOUT_CSS.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(_ARCHIFY_LAYOUT_CSS), media_type="text/css")


@router.get("/archify-app.js", include_in_schema=False)
async def archify_app_js():
    if not _ARCHIFY_APP_JS.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(_ARCHIFY_APP_JS), media_type="application/javascript")


@router.get("/seed-customer.js", include_in_schema=False)
async def archify_seed_customer_js():
    if not _SEED_CUST_JS.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(_SEED_CUST_JS), media_type="application/javascript")


@router.get("/seed-marketing.js", include_in_schema=False)
async def archify_seed_marketing_js():
    if not _SEED_MKT_JS.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(_SEED_MKT_JS), media_type="application/javascript")


# =========================================================================== #
# Bootstrap — one call fills the console                                      #
# =========================================================================== #
@router.get("/api/consoles/bootstrap", operation_id="consoles_bootstrap")
async def bootstrap(
    product: str = Query("voice", max_length=20),
    client_id: str = Depends(require_customer),
) -> dict[str, Any]:
    """Everything a console needs on first paint. Degrades, never 500s."""
    if product not in ("voice", "marketing"):
        product = "voice"
    degraded: list[str] = []

    client: dict[str, Any] = {}
    try:
        from app.marketing import clients_store

        client = clients_store.get_client(client_id) or {}
    except Exception as e:
        logger.warning(f"[consoles] client lookup failed: {e}")
        degraded.append("client_record")

    cfg = _read_config(client_id)
    business = {**(cfg.get("business") or {})}
    # Seed from the real client record so the form is never empty-but-unknown.
    business.setdefault("business_name", client.get("business_name") or "")
    business.setdefault("niche", client.get("niche") or "general")
    business.setdefault("city", client.get("city") or "")
    business.setdefault("phone", client.get("phone") or "")
    business.setdefault("email", client.get("email") or "")

    kb = _kb_evidence(client_id, cfg)
    conns = _connections_evidence(client_id)
    readiness = _readiness(client, cfg, kb, conns, product)

    auto = cfg.get("automation") or {}
    mk = cfg.get("marketing") or {}

    return {
        "ok": True,
        "degraded": degraded,
        "client_id": client_id,
        "product": product,
        "generated_at": _now_iso(),
        "business": business,
        "readiness": readiness,
        "knowledge": kb,
        "connections": conns,
        "automation": {
            "templates": [
                {k: v for k, v in t.items() if k != "spec"} for t in CALL_TEMPLATES
            ],
            "event_slots": EVENT_SLOTS,
            "active": {
                "template_id": auto.get("template_id", ""),
                "enabled": bool(auto.get("enabled", False)),
                "schedule": auto.get("schedule") or {
                    "window_start": "10:00",
                    "window_end": "19:00",
                    "timezone": "Asia/Kolkata",
                    "days": ["mon", "tue", "wed", "thu", "fri", "sat"],
                },
                "max_calls_per_day": int(auto.get("max_calls_per_day") or 50),
                "event_bindings": _normalize_bindings(auto.get("event_bindings")),
                "updated_at": auto.get("updated_at", ""),
            },
        },
        "marketing": {
            "active": bool(mk.get("active", False)),
            "launched_at": mk.get("launched_at", ""),
            "channels": mk.get("channels") or [],
            "cadence": mk.get("cadence") or "daily",
        },
    }


# =========================================================================== #
# Business configuration                                                      #
# =========================================================================== #
class BusinessConfigIn(BaseModel):
    business_name: str = Field("", max_length=200)
    niche: str = Field("", max_length=80)
    city: str = Field("", max_length=80)
    phone: str = Field("", max_length=20)
    email: str = Field("", max_length=200)
    website: str = Field("", max_length=300)
    language: str = Field("hinglish", max_length=20)
    timezone: str = Field("Asia/Kolkata", max_length=64)
    business_hours: dict[str, Any] | None = None
    services: list[str] = Field(default_factory=list, max_length=60)
    greeting: str = Field("", max_length=500)
    brand_voice: str = Field("", max_length=2000)


@router.put("/api/consoles/business-config", operation_id="consoles_save_business_config")
async def save_business_config(
    body: BusinessConfigIn,
    client_id: str = Depends(require_customer),
) -> dict[str, Any]:
    # exclude_unset: persist only what the client actually sent. Without it the
    # model defaults (language/timezone) would always look like "changed fields",
    # making the empty-body 400 unreachable and silently overwriting values.
    patch = {
        k: v for k, v in body.model_dump(exclude_unset=True).items()
        if v not in (None, "", [])
    }
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to save")
    rec = _write_config(client_id, {"business": patch})

    # Mirror the canonical identity back into clients_store (best-effort).
    mirrored = False
    try:
        from app.marketing import clients_store

        fields = {k: v for k, v in patch.items()
                  if k in ("business_name", "niche", "city", "phone", "email")}
        if fields:
            clients_store.update_client(client_id, **fields)
            mirrored = True
    except Exception as e:
        logger.warning(f"[consoles] client mirror skipped: {e}")

    return {"ok": True, "saved": sorted(patch.keys()), "mirrored": mirrored,
            "business": rec.get("business") or {}, "updated_at": rec.get("updated_at")}


# =========================================================================== #
# Knowledge (per-tenant, namespaced)                                          #
# =========================================================================== #
class KnowledgeTextIn(BaseModel):
    text: str = Field(..., min_length=10, max_length=50000)
    source: str = Field(..., min_length=1, max_length=120)
    replace: bool = False


@router.post("/api/consoles/knowledge/text", operation_id="consoles_kb_add_text")
async def kb_add_text(
    body: KnowledgeTextIn,
    client_id: str = Depends(require_customer),
) -> dict[str, Any]:
    """Ingest pasted business knowledge into this tenant's namespace."""
    ns = _kb_namespace(client_id)
    try:
        from app.voice_agent.knowledge_base import get_knowledge_base

        added = get_knowledge_base().add_documents(
            [body.text], source=body.source, namespace=ns, replace_source=bool(body.replace)
        )
    except Exception as e:
        logger.error(f"[consoles] kb ingest failed: {e}")
        raise HTTPException(status_code=503, detail="Knowledge store unavailable")

    if added <= 0:
        raise HTTPException(status_code=400, detail="No chunks were produced from this text")

    cfg = _read_config(client_id)
    sources = [s for s in (cfg.get("kb_sources") or []) if s.get("source") != body.source]
    sources.append({
        "source": body.source,
        "kind": "text",
        "chunks": int(added),
        "added_at": _now_iso(),
    })
    _write_config(client_id, {"kb_sources": sources})

    return {"ok": True, "chunks_added": int(added), "source": body.source, "namespace": ns}


class KnowledgeUrlIn(BaseModel):
    url: str = Field(..., min_length=8, max_length=500)


@router.post("/api/consoles/knowledge/url", operation_id="consoles_kb_add_url")
async def kb_add_url(
    body: KnowledgeUrlIn,
    client_id: str = Depends(require_customer),
) -> dict[str, Any]:
    """Crawl one public URL and ingest it as a knowledge source."""
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    ns = _kb_namespace(client_id)
    try:
        from app.voice_agent.kb_loader import load_from_website
        from app.voice_agent.knowledge_base import get_knowledge_base

        kb = get_knowledge_base()
        added = load_from_website(kb, url, namespace=ns)
    except Exception as e:
        logger.error(f"[consoles] website ingest failed: {e}")
        raise HTTPException(status_code=502, detail="Could not fetch or parse that URL")

    if not added:
        raise HTTPException(
            status_code=422,
            detail="That page produced no usable text. Try a page with real content.",
        )

    cfg = _read_config(client_id)
    sources = [s for s in (cfg.get("kb_sources") or []) if s.get("source") != url]
    sources.append({"source": url, "kind": "url", "chunks": int(added), "added_at": _now_iso()})
    _write_config(client_id, {"kb_sources": sources})

    return {"ok": True, "chunks_added": int(added), "source": url, "namespace": ns}


@router.delete("/api/consoles/knowledge/source", operation_id="consoles_kb_delete_source")
async def kb_delete_source(
    source: str = Query(..., min_length=1, max_length=500),
    client_id: str = Depends(require_customer),
) -> dict[str, Any]:
    """Remove one knowledge source from this tenant's namespace."""
    removed = 0
    idx = _kb_index(client_id)
    if idx is not None:
        try:
            removed = int(idx.delete_source(source) or 0)
        except Exception as e:
            logger.warning(f"[consoles] delete_source failed: {e}")

    cfg = _read_config(client_id)
    remaining = [s for s in (cfg.get("kb_sources") or []) if s.get("source") != source]
    _write_config(client_id, {"kb_sources": remaining})
    return {"ok": True, "chunks_removed": removed, "source": source}


class KnowledgeProbeIn(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)


@router.post("/api/consoles/knowledge/probe", operation_id="consoles_kb_probe")
async def kb_probe(
    body: KnowledgeProbeIn,
    client_id: str = Depends(require_customer),
) -> dict[str, Any]:
    """Ask the tenant's KB a question. Returns the grounded answer plus the exact
    evidence it came from — the console never shows an answer without its receipts."""
    ns = _kb_namespace(client_id)
    try:
        from app.voice_agent.knowledge_base import get_knowledge_base

        kb = get_knowledge_base()
        hits = kb.retrieve(body.query, k=3, namespace=ns, rerank=False) or []
        answer = kb.grounded_answer(body.query, namespace=ns, k=3)
    except Exception as e:
        logger.error(f"[consoles] probe failed: {e}")
        raise HTTPException(status_code=503, detail="Knowledge store unavailable")

    return {
        "ok": True,
        "query": body.query,
        "answer": answer,
        "grounded": bool(hits),
        "evidence": [
            {"text": h.get("text", ""), "score": round(float(h.get("score") or 0.0), 4),
             "source": h.get("source", "")}
            for h in hits
        ],
        "namespace": ns,
    }


@router.get("/api/consoles/knowledge", operation_id="consoles_kb_state")
async def kb_state(client_id: str = Depends(require_customer)) -> dict[str, Any]:
    cfg = _read_config(client_id)
    return {"ok": True, **_kb_evidence(client_id, cfg)}


# =========================================================================== #
# Connections / credentials                                                   #
# =========================================================================== #
@router.get("/api/consoles/connections", operation_id="consoles_connections")
async def connections(client_id: str = Depends(require_customer)) -> dict[str, Any]:
    """Read-only connection health. Token values are never returned."""
    return {"ok": True, **_connections_evidence(client_id)}


@router.delete("/api/consoles/connections/{platform}", operation_id="consoles_revoke_connection")
async def revoke_connection(
    platform: str,
    client_id: str = Depends(require_customer),
) -> dict[str, Any]:
    """Revoke stored credentials for one platform from the encrypted vault."""
    plat = (platform or "").strip().lower()
    if plat not in {p["platform"] for p in _connections_evidence(client_id)["platforms"]}:
        raise HTTPException(status_code=404, detail="Unknown platform")
    removed = 0
    try:
        from app.social_engine import vault

        for acc in vault.list_accounts(client_id) or []:
            if str(acc.get("platform")) == plat and not acc.get("deleted"):
                if vault.delete(client_id, plat, str(acc.get("account_ref") or "")):
                    removed += 1
    except Exception as e:
        logger.error(f"[consoles] revoke failed: {e}")
        raise HTTPException(status_code=503, detail="Credential store unavailable")
    return {"ok": True, "platform": plat, "accounts_removed": removed}


# =========================================================================== #
# Call automation                                                             #
# =========================================================================== #
@router.get("/api/consoles/automation/templates", operation_id="consoles_list_templates")
async def list_templates(client_id: str = Depends(require_customer)) -> dict[str, Any]:
    active = (_read_config(client_id).get("automation") or {}).get("template_id", "")
    return {
        "ok": True,
        "active_template_id": active,
        "templates": [{k: v for k, v in t.items() if k != "spec"} for t in CALL_TEMPLATES],
    }


@router.get("/api/consoles/automation/templates/{template_id}", operation_id="consoles_template_detail")
async def template_detail(
    template_id: str,
    client_id: str = Depends(require_customer),
) -> dict[str, Any]:
    """Full template including the flow spec — preview before apply."""
    t = _TEMPLATES_BY_ID.get((template_id or "").strip())
    if not t:
        raise HTTPException(status_code=404, detail="Unknown template")
    return {"ok": True, "template": t}


class AutomationIn(BaseModel):
    template_id: str = Field("", max_length=60)
    enabled: bool = False
    schedule: dict[str, Any] | None = None
    max_calls_per_day: int = Field(50, ge=1, le=5000)
    event_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=64)


@router.put("/api/consoles/automation", operation_id="consoles_save_automation")
async def save_automation(
    body: AutomationIn,
    client_id: str = Depends(require_customer),
) -> dict[str, Any]:
    """Persist call-automation setup.

    Honest contract: this records the configuration and evaluates the real
    readiness gates. It does not fabricate a running campaign — activation is
    only reported as `live` once knowledge, channel and template gates pass.
    """
    tid = (body.template_id or "").strip()
    if tid and tid not in _TEMPLATES_BY_ID:
        raise HTTPException(status_code=400, detail="Unknown template")

    bindings = _normalize_bindings(body.event_bindings)

    patch = {
        "automation": {
            "template_id": tid,
            "enabled": bool(body.enabled),
            "schedule": body.schedule,
            "max_calls_per_day": int(body.max_calls_per_day),
            "event_bindings": bindings,
            "updated_at": _now_iso(),
        }
    }
    rec = _write_config(client_id, patch)

    # Re-evaluate gates against real evidence.
    cfg = rec
    kb = _kb_evidence(client_id, cfg)
    conns = _connections_evidence(client_id)
    gates: list[str] = []
    kb_ok = int(kb.get("chunks") or 0) > 0
    conn_ok = int(conns.get("connected") or 0) > 0
    bound_n = sum(1 for b in bindings if b.get("enabled") and b.get("template_id"))
    if not tid:
        gates.append("No default template selected")
    if not kb_ok:
        gates.append("Knowledge base is empty")
    if not conn_ok:
        gates.append("No channel connected")
    if bound_n == 0:
        gates.append("No event is bound to a template")

    return {
        "ok": True,
        "saved": True,
        # Honest: live requires the master switch, a default template, bound
        # events, and real knowledge + channel evidence.
        "live": bool(body.enabled and tid and bound_n and kb_ok and conn_ok),
        "gates": gates,
        "bound_events": bound_n,
        "automation": (rec.get("automation") or {}),
    }


def _resolve_niche(client_id: str, cfg: dict[str, Any]) -> str:
    """Tenant niche for the voice agent — same precedence the bootstrap uses:
    console-saved business.niche, then the real client record, then "general".
    Never raises, never returns empty (an empty niche degrades the greeting)."""
    try:
        from_cfg = str(((cfg.get("business") or {}).get("niche")) or "").strip()
        if from_cfg:
            return from_cfg
        from app.marketing import clients_store

        rec = clients_store.get_client(client_id) or {}
        from_rec = str(rec.get("niche") or "").strip()
        if from_rec:
            return from_rec
    except Exception as e:  # pragma: no cover
        logger.warning(f"[consoles] niche resolve failed: {e}")
    return "general"


# Persona that speaks each template. `receptionist` is documented inbound-only,
# so it is mapped only to the one template whose own channel is inbound.
# NOTE: read from this map, never from the template `spec` — no template declares
# a role there, so a spec-based lookup silently yields None and leaves the
# voice_role rail (threaded all the way to vobiz_stream) permanently empty.
_TEMPLATE_VOICE_ROLE: dict[str, str] = {
    "inbound_faq": "receptionist",
    "appointment_reminder": "booking_agent",
    "lead_qualify": "telecaller",
    "payment_followup": "telecaller",
    "reactivation": "telecaller",
    "survey_nps": "telecaller",
}


class TestCallIn(BaseModel):
    # `to` is the documented field name; `phone` is kept as an alias because the
    # shipped voice-console UI posts `phone`. Neither is required at the model
    # level — the gate below produces one clear 400 for both.
    to: str = Field("", max_length=32)
    phone: str = Field("", max_length=32)
    template_id: str = Field("", max_length=60)
    dry_run: bool = True


@router.post("/api/consoles/automation/test-call", operation_id="consoles_automation_test_call")
async def automation_test_call(
    body: TestCallIn,
    client_id: str = Depends(require_customer),
) -> dict[str, Any]:
    """Fire ONE governed test call from the console.

    `start_stream_call` is the shared dial helper used by the campaign loop and
    several internal callers. Those callers enforce the launch gates themselves;
    this route is where a tenant presses the button, so the gates are enforced
    HERE — otherwise the console would be a path around every one of them
    (no daily cap, no per-tenant cap, no kill switch, no circuit breaker, no
    lead eligibility). Every gate below is the project's existing one, reused
    via app.telephony.voice_launch; none is re-implemented or weakened.

    Chain runs in order and STOPS AT THE FIRST FAILURE — a later gate must never
    be reached (and never consume a counter slot) once an earlier one has
    refused.

    Honesty contract: `dry_run=True` is the DEFAULT, and in that mode NO CALL IS
    PLACED. `placed=True` then means "the governed chain completed and the
    answer_url was built", NOT "we dialled". The `note` says so in plain words,
    because a dry run misread as a live dial is worse than no test at all.
    """
    steps: list[dict[str, Any]] = []
    dial_result: dict[str, Any] = {}
    tid = ""
    dry = bool(body.dry_run)
    try:
        cfg = _read_config(client_id)
        auto = cfg.get("automation") or {}

        # --- template resolution -------------------------------------------
        # An explicitly requested id is FINAL — we never silently substitute a
        # different script than the tenant asked for. An unknown id is a client
        # error and is refused. Having NO template is NOT an error: this is the
        # tenant's own test call, so it runs the generic agent and says so in
        # `warnings` — a test call you cannot place until the config is perfect
        # is a test call nobody can use.
        req = (body.template_id or "").strip()
        if req:
            tid = req
            if tid not in _TEMPLATES_BY_ID:
                return {
                    "ok": True, "placed": False, "dialed": False, "dry_run": dry,
                    "reason": "unknown_template", "steps": steps,
                    "template_id": tid, "voice_role": None, "governed": True,
                    "knowledge_chunks": 0, "warnings": [], "dial_result": {},
                    "note": f"Unknown call template '{tid}'. Pick one from the gallery.",
                }
        else:
            saved = str(auto.get("template_id") or "").strip()
            tid = saved if saved in _TEMPLATES_BY_ID else ""

        voice_role = _TEMPLATE_VOICE_ROLE.get(tid) if tid else None
        niche = _resolve_niche(client_id, cfg)

        # Missing pieces are REPORTED, never hidden and never a blocker.
        warnings: list[str] = []
        if not tid:
            warnings.append(
                "No call template is bound — this call runs the generic "
                "telecaller, not a scripted flow."
            )
        try:
            kb_chunks = int((_kb_evidence(client_id, cfg) or {}).get("chunks") or 0)
        except Exception as e:
            logger.warning(f"[consoles] kb evidence unavailable for {client_id}: {e}")
            kb_chunks = 0
        if kb_chunks <= 0:
            warnings.append(
                "Your knowledge base is empty — the agent will hand off or "
                "answer generically instead of answering from your own content."
            )

        from app.telephony import voice_launch

        def _fail(step: str, reason: str, detail: str = "") -> dict[str, Any]:
            steps.append({"step": step, "ok": False, "detail": detail or reason})
            return {
                "ok": True, "placed": False, "dialed": False, "dry_run": dry,
                "reason": reason, "steps": steps, "template_id": tid,
                "voice_role": voice_role, "niche": niche,
                "knowledge_chunks": kb_chunks, "warnings": warnings,
                "governed": True, "dial_result": {},
                "note": f"Blocked at '{step}' — no call was placed. {detail or reason}",
            }

        def _pass(step: str, detail: str = "") -> None:
            steps.append({"step": step, "ok": True, "detail": detail})

        # 1) phone sanity — the ONE deliberate HTTPException. A malformed
        # request is a 400, not a silent no-op and not a 500.
        phone = "".join(ch for ch in str(body.to or body.phone or "") if ch.isdigit())
        if not (10 <= len(phone) <= 15):
            raise HTTPException(
                status_code=400,
                detail=f"`to` must be a phone number with 10-15 digits (got {len(phone)}).",
            )
        _pass("phone", f"{len(phone)} digits")

        # 2) admin kill switch — fail-closed if the gate itself cannot be read
        try:
            if voice_launch.admin_kill_engaged():
                return _fail("admin_kill", "admin_kill", "Platform kill switch is engaged")
        except Exception as e:
            return _fail("admin_kill", "admin_kill_unavailable",
                         f"Could not read the kill switch — failing closed: {e}")
        _pass("admin_kill", "clear")

        # 3) circuit breaker
        try:
            if await voice_launch.circuit_open():
                return _fail("circuit", "circuit_open", "Circuit breaker is open")
        except Exception as e:
            return _fail("circuit", "circuit_unavailable",
                         f"Could not read the circuit breaker — failing closed: {e}")
        _pass("circuit", "closed")

        # 4) per-tenant daily cap. tenant_cap clamps the stored value: the
        # console accepts up to 5000, which must not outrank the platform cap.
        try:
            cfg_max = int(auto.get("max_calls_per_day") or 50)
        except Exception:
            cfg_max = 50
        try:
            res = await voice_launch.reserve_tenant_slot(
                client_id, voice_launch.tenant_cap(cfg_max)
            )
        except Exception as e:
            return _fail("tenant_cap", "tenant_cap_unavailable",
                         f"Could not reserve a slot — failing closed: {e}")
        if not res.ok:
            return _fail("tenant_cap", res.reason or "tenant_cap",
                         f"{max(0, int(res.count or 0))}/{res.cap} — your daily limit is reached")
        _pass("tenant_cap", f"{res.count}/{res.cap}")

        # 5) per-lead eligibility (DND / window / consent / opt-out)
        try:
            elig = await voice_launch.is_lead_eligible_for_voice_call(phone, "transactional")
            eligible = bool(getattr(elig, "eligible", False))
            elig_reason = str(getattr(elig, "reason", "") or "")
        except Exception as e:
            return _fail("eligibility", "eligibility_error",
                         f"Compliance check failed — failing closed: {e}")
        if not eligible:
            return _fail("eligibility", elig_reason or "ineligible",
                         f"This number cannot be called right now "
                         f"({elig_reason or 'compliance gate'}).")
        _pass("eligibility", "eligible")

        # 6) dial
        # call_type="transactional" on purpose: a test call goes to a number the
        # tenant typed by hand, which has no verified consent on file. Routing it
        # as "promotional" would fail-closed on DND/DLT and make the demo
        # permanently unreachable — while being no safer, since the same
        # eligibility gate has already run above.
        from app.api.telephony_vobiz import start_stream_call

        dial_result = await start_stream_call(
            to=phone,
            niche=niche,
            client_id=client_id,
            call_type="transactional",
            template_id=tid,
            voice_role=voice_role,
            dry_run=dry,
        ) or {}
        placed = bool(dial_result.get("placed"))
        # `dialed` is the honest flag: a dry run never contacts Vobiz, and a
        # provider rejection is not a dial either. `placed` alone must never be
        # read as "we rang the phone".
        dialed = placed and not dry
        _pass("dial", "dry-run" if dry else ("placed" if placed else "not placed"))

        if not dialed:
            # The slot was reserved so the cap is always exercised, but nothing
            # was dialed — give it back instead of billing the tenant's quota
            # for a dry run or a provider rejection.
            try:
                await voice_launch.release_tenant_slot(client_id)
            except Exception as e:  # pragma: no cover — release never raises
                logger.warning(f"[consoles] tenant slot release failed for {client_id}: {e}")

        if dry:
            note = (
                "DRY RUN — NO CALL WAS PLACED. The governed chain completed and the "
                "answer_url was built, but Vobiz was never contacted. Set "
                "dry_run=false to place a real call."
            )
        elif placed:
            note = "Call placed."
        else:
            note = "Vobiz did not accept the call — see dial_result for the provider response."

        return {
            "ok": True, "placed": placed, "dialed": dialed, "dry_run": dry,
            # A dry run that failed to BUILD is still a failure. `dry` alone must
            # not blank the reason: with Vobiz unconfigured, start_stream_call
            # returns placed=False and the payload would otherwise report a clean
            # run alongside a cheerful DRY RUN note — the exact "green light that
            # means nothing" this console refuses to show.
            "reason": "" if (dialed or (dry and placed)) else (dial_result.get("error") or "not_placed"),
            "steps": steps, "template_id": tid, "voice_role": voice_role,
            "niche": niche, "knowledge_chunks": kb_chunks, "warnings": warnings,
            "governed": True, "dial_result": dial_result, "note": note,
        }
    except HTTPException:
        raise  # the documented 400 must reach FastAPI, not be flattened to a body
    except Exception:
        logger.exception(f"[consoles] test-call failed client={client_id}")
        return {
            "ok": True, "placed": False, "dialed": False, "dry_run": dry,
            "reason": "internal_error", "steps": steps, "template_id": tid,
            "voice_role": None, "knowledge_chunks": 0, "warnings": [],
            "governed": True, "dial_result": {},
            "note": "Internal error — no call was placed.",
        }


# =========================================================================== #
# Marketing launch                                                            #
# =========================================================================== #
class MarketingLaunchIn(BaseModel):
    active: bool = False
    channels: list[str] = Field(default_factory=list, max_length=20)
    cadence: str = Field("daily", max_length=20)


# Content-generation targets the downstream engine actually understands
# (app/social_engine/client_config._VALID_CHANNELS). Deliberately NOT identical
# to the OAuth platform set: `x` is a connectable account but not a content
# target, and `whatsapp` is 1-to-1 owner delivery rather than a social publish.
# Selecting a channel that cannot be published to would be a silent no-op.
_CONTENT_CHANNELS = ("instagram", "facebook", "gbp", "youtube", "linkedin")
_VALID_CADENCE = ("daily", "3x_week", "weekly")


def _publishing_armed() -> dict[str, Any]:
    """Is the publishing pipeline actually able to post, platform-wide?

    Two independent master gates must be on. Without SOCIAL_PREFS_HONOR the
    content engine never reads cadence/approval_mode at all
    (auto_content._social_prefs returns {}); without SOCIAL_ENGINE nothing
    drains the publish queue. Reported to the tenant rather than hidden —
    a "launched" state that cannot publish is worse than an honest one.
    """
    try:
        from app.social_engine import engine as social_engine

        engine_on = bool(social_engine.enabled())
    except Exception as e:  # pragma: no cover
        logger.warning(f"[consoles] social engine state unavailable: {e}")
        engine_on = False
    prefs_on = (os.getenv("SOCIAL_PREFS_HONOR") or "").strip().lower() in ("1", "true", "yes")
    armed = bool(engine_on and prefs_on)
    blockers: list[str] = []
    if not engine_on:
        blockers.append("SOCIAL_ENGINE is off — publish queue is not drained (owner action).")
    if not prefs_on:
        blockers.append("SOCIAL_PREFS_HONOR is off — cadence and channels are not read (owner action).")
    return {"armed": armed, "engine_enabled": engine_on, "prefs_honored": prefs_on, "blockers": blockers}


@router.post("/api/consoles/marketing/launch", operation_id="consoles_marketing_launch")
async def marketing_launch(
    body: MarketingLaunchIn,
    client_id: str = Depends(require_customer),
) -> dict[str, Any]:
    """Start or stop the marketing product for this tenant.

    Writes two stores, and the distinction is the whole point:

      * ``console_configs.jsonl`` — what this console renders. UI state only.
      * ``social_engine.client_config`` — what the content engine actually reads.

    The second write is what makes launch real. Cadence and approval_mode there
    are the engine's genuine on/off switch (``auto_content._cadence_due``), and
    ``approval_mode="auto"`` is its documented hands-free publish path. Before
    this, activation persisted only to the console store, which nothing
    downstream consumes — a launched tenant generated nothing at all.

    Honest contract: activation requires at least one genuinely healthy channel,
    and the response states whether publishing is armed platform-wide rather
    than implying a green switch that posts nothing.
    """
    conns = _connections_evidence(client_id)
    conn_ok = int(conns.get("connected") or 0) > 0
    cfg = _read_config(client_id)
    prev_active = bool((cfg.get("marketing") or {}).get("active"))

    if body.active and not conn_ok:
        return {
            "ok": True,
            "launched": False,
            "blocked": True,
            "reason": "Connect at least one channel before launching.",
            "connected": conns.get("connected"),
        }

    # Only channels that are BOTH healthy here AND real downstream content
    # targets. Anything else would be accepted and then silently do nothing.
    healthy = {
        str(p.get("platform") or "")
        for p in (conns.get("platforms") or [])
        if str(p.get("status")) == "healthy"
    }
    wanted = [c.strip().lower() for c in (body.channels or [])][:20]
    chosen = [c for c in wanted if c in _CONTENT_CHANNELS and c in healthy]
    if body.active and not chosen:
        # Caller named nothing usable — fall back to every healthy content
        # target rather than launching a config that targets zero channels.
        chosen = [c for c in _CONTENT_CHANNELS if c in healthy]
    dropped = sorted({c for c in wanted if c not in chosen})

    cadence = (body.cadence or "daily").strip().lower()
    if cadence not in _VALID_CADENCE:
        cadence = "daily"

    # --- the write that actually drives the engine -------------------------
    prefs_saved = False
    prefs_error = ""
    engine_cfg: dict[str, Any] = {}
    try:
        from app.social_engine import client_config

        if body.active:
            engine_cfg = client_config.save(
                client_id, channels=chosen, cadence=cadence, approval_mode="auto",
            ) or {}
        else:
            # `off` is the engine's real stop signal (_cadence_due -> False);
            # `draft` guarantees nothing publishes even if a batch is in flight.
            engine_cfg = client_config.save(
                client_id, cadence="off", approval_mode="draft",
            ) or {}
        prefs_saved = bool(engine_cfg)
    except Exception as e:
        prefs_error = str(e)
        logger.warning(f"[consoles] marketing launch could not save client_config: {e}")

    # Day-1 packet immediately, so the tenant sees content now rather than
    # waiting for the 07:00 daily pass.
    seeded = 0
    if body.active and not prev_active:
        try:
            from app.marketing import auto_content, clients_store

            client = clients_store.get_client(client_id) or {}
            if client:
                seeded = int(await auto_content.seed_client_content(client) or 0)
        except Exception as e:
            logger.warning(f"[consoles] day-1 content seed failed for {client_id}: {e}")

    patch = {
        "marketing": {
            "active": bool(body.active),
            "channels": chosen,
            "cadence": cadence,
            "launched_at": _now_iso() if (body.active and not prev_active)
                           else (cfg.get("marketing") or {}).get("launched_at", ""),
            "stopped_at": "" if body.active else _now_iso(),
        }
    }
    rec = _write_config(client_id, patch)
    armed = _publishing_armed()

    out: dict[str, Any] = {
        "ok": True,
        "launched": bool(body.active),
        "blocked": False,
        "marketing": rec.get("marketing") or {},
        "connected": conns.get("connected"),
        "channels": chosen,
        "channels_dropped": dropped,
        "prefs_saved": prefs_saved,
        "content_seeded": seeded,
        "publishing_armed": armed["armed"],
    }
    if prefs_error:
        out["prefs_error"] = prefs_error
    # Never let "launched" imply "posting" when the platform gates are shut.
    if body.active and not armed["armed"]:
        out["note"] = (
            "Preferences saved and content will be generated, but publishing is "
            "gated at platform level until the owner enables it."
        )
        out["owner_actions"] = armed["blockers"]
    return out


# CHECK-MOUNT: app/main.py must mount this router inside a guarded try:
#   try:
#       from app.api.product_consoles import router as product_consoles_router
#       app.include_router(product_consoles_router)
#   except Exception as _e:
#       logger.warning(f"Product consoles router not mounted: {_e}")
