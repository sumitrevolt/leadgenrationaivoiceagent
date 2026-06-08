"""Automated client onboarding — client add hote hi poora setup KHUD (done-for-you).

Manual agency onboarding 5-7 din leta hai; yeh minutes me karta hai. Jaise hum apne liye
karte hain, waise client ke liye. Pieces pehle se the (clients_store, content_pack,
mini-site) — yeh unhe ek auto-flow me chain karta hai PLUS naya high-value step:

  **client ki ASLI website se KB auto-seed** (deep_extract/trafilatura → vector KB +
  LightRAG graph, namespace `client:<id>`) — taaki client ka AI agent uske apne business
  (services, USP, area) ko jaane, sirf generic niche facts nahi. Yeh dormant
  web-extraction + RAG tools ko asli value me convert karta hai.

Steps per client: website→KB seed → first content pack (welcome deliverable) → setup_done
mark → welcome event. Sab defensive (step fail → skip, never crash).

OFF by default. Enable `AUTO_ONBOARD=1`. Hourly sweep un-setup active clients ko onboard
karta hai (idempotent — setup_done wale skip).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_PACK_DIR = os.path.join("data", "client_packs")


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _website(client: dict) -> str:
    w = client.get("website") or ""
    if not w:
        w = (client.get("socials") or {}).get("website", "") if isinstance(client.get("socials"), dict) else ""
    return str(w or "").strip()


def _namespace(cid: str) -> str:
    try:
        from app.platform.agent_provisioner import _client_namespace

        return _client_namespace(cid)
    except Exception:
        return f"client:{cid}"


async def _seed_kb_from_website(cid: str, website: str) -> dict:
    """Scrape the client's site → vector KB + (opt-in) knowledge graph. Best-effort."""
    out = {"website": website, "kb_chunks": 0, "graph": False}
    if not website:
        return out
    try:
        from app.lead_scraper.deep_extract import extract_url

        data = await extract_url(website)
        text = (data.get("text") or data.get("markdown") or "").strip()
        if len(text) < 150:
            return out
        ns = _namespace(cid)
        try:
            from app.voice_agent.knowledge_base import get_knowledge_base

            out["kb_chunks"] = get_knowledge_base().add_documents(
                [text[:8000]], source=f"website:{website}", namespace=ns
            )
        except Exception as exc:
            logger.info("onboard kb seed err: %s", exc)
        try:
            from app.voice_agent.graph_rag import get_graph_rag

            out["graph"] = await get_graph_rag().ainsert(text[:8000], namespace=ns)
        except Exception:
            pass
    except Exception as exc:
        logger.info("onboard website extract err: %s", exc)
    return out


async def _first_content_pack(client: dict) -> dict:
    try:
        from app.marketing.content_pack import build_client_pack

        pack = await build_client_pack(
            client.get("business_name", ""),
            client.get("niche", "general"),
            client_id=str(client.get("id", "")),
            phone=str(client.get("phone", "")),
        )
        html = pack.get("html") or ""
        if html:
            os.makedirs(_PACK_DIR, exist_ok=True)
            with open(os.path.join(_PACK_DIR, f"{client.get('id','client')}.html"), "w", encoding="utf-8") as f:
                f.write(html)
        return pack.get("counts", {})
    except Exception as exc:
        logger.info("onboard content pack err: %s", exc)
        return {}


def _log(kind: str, detail: str) -> None:
    try:
        from app.platform.team import log_event

        log_event("dev", kind, detail)
    except Exception:
        pass


async def auto_onboard(cid: str) -> dict[str, Any]:
    """Run the full auto-setup for one client. Never raises."""
    report: dict[str, Any] = {"client_id": cid, "steps": {}}
    try:
        from app.marketing import clients_store

        client = clients_store.get_client(cid)
        if not client:
            return {"error": "client not found", "client_id": cid}
        biz = client.get("business_name", "")

        report["steps"]["kb_website"] = await _seed_kb_from_website(cid, _website(client))
        report["steps"]["content_pack"] = await _first_content_pack(client)

        try:
            clients_store.update_client(
                cid, setup_done=True, setup_at=datetime.now(timezone.utc).isoformat()
            )
        except Exception:
            pass

        kb = report["steps"]["kb_website"].get("kb_chunks", 0)
        _log("client_onboarded", f"{biz}: auto-setup done (website KB {kb} chunks + content pack)")
        report["ok"] = True
        return report
    except Exception as exc:
        logger.info("auto_onboard err: %s", exc)
        return {"error": str(exc), "client_id": cid}


async def run_onboarding_sweep(limit: int = 10) -> dict[str, Any]:
    """Find active clients without setup_done and auto-onboard them. Never raises."""
    if not _flag("AUTO_ONBOARD"):
        return {"skipped": "AUTO_ONBOARD off"}
    res = {"onboarded": 0, "checked": 0}
    try:
        from app.marketing import clients_store

        for c in clients_store.list_clients(status="active"):
            res["checked"] += 1
            if c.get("setup_done"):
                continue
            await auto_onboard(str(c.get("id", "")))
            res["onboarded"] += 1
            if res["onboarded"] >= max(1, limit):
                break
    except Exception as exc:
        logger.info("onboarding sweep err: %s", exc)
        res["error"] = str(exc)
    return res


__all__ = ["auto_onboard", "run_onboarding_sweep"]
