"""Page-Agent admin copilot (alibaba/page-agent) — in-page GUI agent for admin UI.

Kya hai: admin pages (Mission Control / dashboard / growth-tools / marketing / office)
me natural-language UI control — "clients tab kholo", "campaign form bhar do" type.
Script = alibaba/page-agent IIFE build (CDN pinned @1.10.0, MIT), jo apna UI khud
render karta hai. Humara kaam = key-safe LLM proxy + flag-gated boot loader.

KEY-SAFETY (ai-image-proxy pattern): LLM key KABHI browser me nahi jaati.
page-agent ka `apiKey` = admin JWT (localStorage.accessToken) hota hai; yeh proxy
usse require_admin se verify karke SERVER-side Mistral/Groq key ke saath upstream
OpenAI-compatible /chat/completions ko forward karta hai (stream pass-through).

Flag: PAGE_AGENT (default OFF = fully inert; config enabled:false, chat 503).
Env knobs: PAGE_AGENT_MODEL (default mistral-small-latest),
PAGE_AGENT_SCRIPT_URL (default = pinned jsDelivr; self-host karne pe override).

Routes (mounted at /api in main.py — duplicate-route grep done, koi /page-agent nahi):
  GET  /api/page-agent/boot.js              — public loader JS (self-gates: token+config)
  GET  /api/page-agent/config               — admin: enabled + script_url + model
  POST /api/page-agent/v1/chat/completions  — admin: OpenAI-compat LLM proxy
"""

import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/page-agent", tags=["Page Agent"])

_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

# Pinned CDN build (README: sirf IIFE demo build self-contained hai; ?autoInit=false
# = demo LLM auto-init NAHI hota, hum apne config se new PageAgent() banate).
# SRI hash = data.jsdelivr.com se (sha256, version-pinned = stable).
_DEFAULT_SCRIPT_URL = (
    "https://cdn.jsdelivr.net/npm/page-agent@1.10.0/dist/iife/page-agent.demo.js?autoInit=false"
)
_DEFAULT_SCRIPT_SRI = (
    "sha256-noeu3GDBmE6HTbB1d/RHK3hKHPqbeKaOawqWEROWy0I="  # pragma: allowlist secret
)

# SELF-HOSTED vendored copy (PREFERRED when present) — 2026-07-03 finding: user ke
# ISP se cdn.jsdelivr.net BLOCKED tha (India me common). File = same pinned 1.10.0
# build, sha256 == upar wala SRI (repo me commit se pehle verify kiya). Same-origin
# serve = koi CDN/ISP dependency nahi, SRI zaroori nahi.
_VENDOR_FILE = _FRONTEND_DIR / "vendor" / "page-agent.demo.js"
_VENDOR_URL = "/api/page-agent/vendor.js?autoInit=false"

# provider -> (settings attr, upstream chat URL, enforced model env-default)
_PROVIDERS: list[tuple[str, str, str, str]] = [
    (
        "mistral",
        "mistral_api_key",
        "https://api.mistral.ai/v1/chat/completions",
        "mistral-small-latest",
    ),
    (
        "groq",
        "groq_api_key",
        "https://api.groq.com/openai/v1/chat/completions",
        "openai/gpt-oss-20b",
    ),
]

_MAX_BODY_BYTES = 1_000_000  # DOM serialization badi ho sakti — 1MB cap (abuse guard)


def _flag_on() -> bool:
    return (os.environ.get("PAGE_AGENT") or "").strip().lower() in ("1", "true", "yes", "on")


def _script_url() -> str:
    env = (os.environ.get("PAGE_AGENT_SCRIPT_URL") or "").strip()
    if env:
        return env
    if _VENDOR_FILE.exists():  # self-hosted first (ISP-block-proof)
        return _VENDOR_URL
    return _DEFAULT_SCRIPT_URL


def _model_for(provider_default: str) -> str:
    return (os.environ.get("PAGE_AGENT_MODEL") or "").strip() or provider_default


def _key(attr: str) -> str:
    try:
        from app.config import settings

        return (getattr(settings, attr, "") or "").strip()
    except Exception:
        return ""


@router.get("/boot.js", include_in_schema=False)
async def page_agent_boot_js():
    """Public loader — no secrets; bina admin-token/flag ke silently no-op."""
    p = _FRONTEND_DIR / "page_agent_boot.js"
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(
        str(p), media_type="application/javascript", headers={"Cache-Control": "no-cache"}
    )


@router.get("/vendor.js", include_in_schema=False)
async def page_agent_vendor_js():
    """Self-hosted page-agent bundle (pinned 1.10.0, sha256-verified) — public,
    version-pinned isliye long cache theek hai."""
    if not _VENDOR_FILE.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(
        str(_VENDOR_FILE),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/config")
async def page_agent_config(user=Depends(require_admin)):
    """Admin: boot loader isse poochta hai ki copilot enable hai ya nahi."""
    if not _flag_on():
        return {"enabled": False}
    url = _script_url()
    return {
        "enabled": True,
        "script_url": url,
        # SRI sirf default pinned URL pe (override pe hash match nahi karega)
        "integrity": _DEFAULT_SCRIPT_SRI if url == _DEFAULT_SCRIPT_URL else "",
        "model": _model_for(_PROVIDERS[0][3]),
    }


@router.post(
    "/v1/chat/completions",
    dependencies=[Depends(rate_limit("pageagent", 60, 60))],
)
async def page_agent_chat(request: Request, user=Depends(require_admin)):
    """OpenAI-compatible proxy — page-agent isko baseURL banata hai.

    Server-side key inject (Mistral primary -> Groq fallback), model ENFORCED
    server pe (client jo bhi bheje). Stream + non-stream dono raw pass-through.
    """
    if not _flag_on():
        raise HTTPException(status_code=503, detail="PAGE_AGENT flag off")

    raw = await request.body()
    if len(raw) > _MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="request too large")
    try:
        import json

        payload: dict[str, Any] = json.loads(raw or b"{}")
        assert isinstance(payload, dict)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    last_err = "no provider key configured"
    for name, attr, url, default_model in _PROVIDERS:
        key = _key(attr)
        if not key:
            continue
        body = dict(payload)
        body["model"] = _model_for(default_model) if name == "mistral" else default_model
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        client = httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0))
        try:
            req = client.build_request("POST", url, headers=headers, json=body)
            resp = await client.send(req, stream=True)
            if resp.status_code >= 400:
                detail = (await resp.aread())[:300]
                await resp.aclose()
                await client.aclose()
                last_err = f"{name} HTTP {resp.status_code}"
                logger.warning(f"[page_agent] {name} upstream {resp.status_code}: {detail!r}")
                continue  # 429/5xx -> next provider

            async def _relay(r=resp, c=client):
                try:
                    async for chunk in r.aiter_raw():
                        yield chunk
                finally:
                    await r.aclose()
                    await c.aclose()

            return StreamingResponse(
                _relay(),
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "application/json"),
            )
        except httpx.HTTPError as e:
            await client.aclose()
            last_err = f"{name}: {type(e).__name__}"
            logger.warning(f"[page_agent] {name} upstream error: {e}")
            continue

    raise HTTPException(status_code=502, detail=f"LLM upstream unavailable ({last_err})")
