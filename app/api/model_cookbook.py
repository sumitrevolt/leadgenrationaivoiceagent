"""Model Cookbook — free-tier LLM catalog + niche-aware recommendations.

Odysseus-inspired pattern (clean-room reimplement, AGPL-safe): "hardware-aware
model recommendations." LeadGen SaaS pe koi hardware nahi — customer-hardware
irrelevant. Isliye pattern ko naye axis pe map kiya:

  Odysseus  → "aap ki GPU/RAM ke liye best local model kaunsa?"
  LeadGen   → "aap ke niche / task / speed-vs-quality tradeoff ke liye
              hamare 8+ free-tier providers me se best kaunsa?"

Content-driven (data, koi external call nahi). Admin + customer dono ko
selectable — customer ko show karke apnе marketing product ki technical
depth demonstrate hoti (upsell surface).

Flag: `MODEL_COOKBOOK_ENABLED=1` warna 503 (INERT default).

Reuses: `free_ai._provider_flags()` for live "configured" status.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger
from app.voice_agent import free_ai

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/cookbook", tags=["Model Cookbook"])


_FLAG_ENV = "MODEL_COOKBOOK_ENABLED"


def _enabled() -> bool:
    return (os.getenv(_FLAG_ENV, "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(
            status_code=503,
            detail=f"Model Cookbook disabled ({_FLAG_ENV}=0).",
        )


# --------------------------- catalog --------------------------- #
# Static catalog — hand-curated from `free_ai.py` provider chain + public
# rate-limit docs (as of 2026-Q3). Update when models/limits change.
#
# Fields:
#   provider     : matches free_ai _PROVIDER_CFG key
#   model        : default model id (env-overridable in free_ai)
#   speed        : latency band ('fast', 'medium', 'slow')
#   quality      : answer quality band ('excellent', 'good', 'fair')
#   multilingual : Hinglish/Hindi handling ('excellent', 'good', 'fair')
#   rate_limit   : short human-readable RPM/RPD
#   cost         : 'free-unlimited', 'free-tier', 'free+metered'
#   best_for     : niche / task tags (voice_reply, content_gen, planning, ...)
#   notes        : caveats (rate 429, small context, etc.)

_CATALOG: list[dict[str, Any]] = [
    {
        "provider": "mistral",
        "model": "mistral-small-latest",
        "speed": "fast",
        "quality": "good",
        "multilingual": "excellent",
        "rate_limit": "free tier: 1 RPS bursty",
        "cost": "free-tier",
        "best_for": ["voice_reply", "hinglish", "customer_chat"],
        "notes": "Voice pipeline ka primary — Hinglish tonality best.",
    },
    {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "speed": "fast",
        "quality": "good",
        "multilingual": "good",
        "rate_limit": "free/developer tier (see Groq console)",
        "cost": "free-unlimited (soft cap)",
        "best_for": ["voice_reply", "planning", "quick_summary"],
        "notes": "Official replacement for llama-3.1-8b-instant (decommissions 2026-08-16).",
    },
    {
        "provider": "cerebras",
        "model": "gpt-oss-120b",
        "speed": "fast",
        "quality": "excellent",
        "multilingual": "good",
        "rate_limit": "free tier: varies",
        "cost": "free-tier",
        "best_for": ["content_gen", "bulk_writing", "planning", "reasoning"],
        "notes": "120B free — quality lead. 429-prone peak hours pe.",
    },
    {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "speed": "medium",
        "quality": "excellent",
        "multilingual": "excellent",
        "rate_limit": "free tier: 15 RPM per key (9-key pool)",
        "cost": "free-tier",
        "best_for": ["voice_reply", "long_context", "audio_stt", "vision"],
        "notes": "Voice-scoped primary (VOICE_GEMINI_PRIMARY=1). 9-key rotation.",
    },
    {
        "provider": "sambanova",
        "model": "Meta-Llama-3.3-70B-Instruct",
        "speed": "fast",
        "quality": "excellent",
        "multilingual": "good",
        "rate_limit": "free — no card required",
        "cost": "free-unlimited (soft cap)",
        "best_for": ["content_gen", "bulk_writing", "reasoning"],
        "notes": "70B free, custom SN10 chip — fast quality inference.",
    },
    {
        "provider": "nvidia",
        "model": "meta/llama-3.3-70b-instruct",
        "speed": "medium",
        "quality": "excellent",
        "multilingual": "good",
        "rate_limit": "40 RPM + ~5k lifetime credits",
        "cost": "free+metered",
        "best_for": ["deep_tail_fallback", "high_stakes"],
        "notes": "Deep-tail hi rakho — lifetime credits khatam ho jate.",
    },
    {
        "provider": "openrouter",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "speed": "medium",
        "quality": "excellent",
        "multilingual": "good",
        "rate_limit": "free tier: shared quota",
        "cost": "free-tier",
        "best_for": ["deep_tail_fallback", "quality_fallback"],
        "notes": "4-key rotation (OPENROUTER_API_KEY_2/3/4) for burst.",
    },
]


# Task → recommended chain (curated, order = try_first, try_next, ...)
_TASK_RECIPES: dict[str, list[str]] = {
    "voice_reply": ["mistral", "groq", "gemini", "cerebras"],
    "content_gen": ["cerebras", "sambanova", "openrouter", "groq"],
    "bulk_writing": ["cerebras", "sambanova", "openrouter"],
    "planning": ["cerebras", "groq", "gemini"],
    "quick_summary": ["groq", "mistral", "gemini"],
    "reasoning": ["cerebras", "sambanova", "gemini"],
    "hinglish": ["mistral", "gemini", "groq"],
    "high_stakes": ["gemini", "nvidia", "cerebras"],
    "deep_tail_fallback": ["openrouter", "nvidia", "sambanova"],
    "long_context": ["gemini", "cerebras"],
    "audio_stt": ["groq", "gemini"],
    "customer_chat": ["mistral", "groq", "gemini"],
}


# Niche → task-mix (LeadGen sells to Indian small businesses; niches shape
# the LLM answer patterns needed).
_NICHE_TASK_HINTS: dict[str, list[str]] = {
    "salon": ["voice_reply", "hinglish", "customer_chat"],
    "restaurant": ["voice_reply", "hinglish", "customer_chat"],
    "clinic": ["voice_reply", "hinglish", "quick_summary"],
    "gym": ["voice_reply", "hinglish", "content_gen"],
    "spa": ["voice_reply", "hinglish", "content_gen"],
    "boutique": ["content_gen", "hinglish", "customer_chat"],
    "real_estate": ["voice_reply", "planning", "reasoning"],
    "coaching": ["content_gen", "planning", "reasoning"],
    "solar": ["voice_reply", "planning", "customer_chat"],
    "makeover": ["voice_reply", "content_gen", "hinglish"],
    "generic": ["voice_reply", "content_gen", "hinglish"],
}


def _live_flags() -> dict[str, bool]:
    try:
        return free_ai._provider_flags()
    except Exception:
        return getattr(free_ai, "PROVIDERS_AVAILABLE", {}) or {}


def _augment(row: dict[str, Any], live: dict[str, bool]) -> dict[str, Any]:
    r = dict(row)
    r["configured"] = bool(live.get(row["provider"], False))
    return r


class RecommendIn(BaseModel):
    niche: str = Field(default="generic", max_length=60)
    task: str = Field(default="", max_length=60)
    prefer_speed: bool = Field(default=False)
    prefer_quality: bool = Field(default=False)


@router.get("/models")
async def list_models(_user=Depends(require_admin)) -> dict:
    _require_enabled()
    live = _live_flags()
    return {
        "count": len(_CATALOG),
        "models": [_augment(r, live) for r in _CATALOG],
        "configured_count": sum(1 for r in _CATALOG if live.get(r["provider"])),
    }


@router.get("/tasks")
async def list_tasks(_user=Depends(require_admin)) -> dict:
    _require_enabled()
    return {"tasks": sorted(_TASK_RECIPES.keys()), "niches": sorted(_NICHE_TASK_HINTS.keys())}


@router.post("/recommend")
async def recommend(payload: RecommendIn, _user=Depends(require_admin)) -> dict:
    _require_enabled()
    live = _live_flags()
    niche = (payload.niche or "generic").lower().strip()
    task = (payload.task or "").lower().strip()

    if task and task in _TASK_RECIPES:
        tasks_chosen = [task]
    else:
        tasks_chosen = _NICHE_TASK_HINTS.get(niche, _NICHE_TASK_HINTS["generic"])

    # Union chain preserving order
    chain: list[str] = []
    for t in tasks_chosen:
        for p in _TASK_RECIPES.get(t, []):
            if p not in chain:
                chain.append(p)

    # Apply speed/quality preference re-sort
    if payload.prefer_speed:
        chain.sort(key=lambda p: 0 if _by_provider(p).get("speed") == "fast" else 1)
    if payload.prefer_quality:
        chain.sort(key=lambda p: 0 if _by_provider(p).get("quality") == "excellent" else 1)

    # Drop unconfigured for the "recommended_live" chain (falls back to full if none live)
    live_chain = [p for p in chain if live.get(p, False)]

    reason = (
        f"niche='{niche}' matched tasks={tasks_chosen}" if not task else f"explicit task='{task}'"
    )

    return {
        "niche": niche,
        "task": task or None,
        "matched_tasks": tasks_chosen,
        "recommended_full_chain": chain,
        "recommended_live_chain": live_chain or chain,
        "reason": reason,
        "prefer_speed": payload.prefer_speed,
        "prefer_quality": payload.prefer_quality,
        "top_pick": (live_chain or chain or [None])[0],
    }


def _by_provider(provider: str) -> dict[str, Any]:
    for row in _CATALOG:
        if row["provider"] == provider:
            return row
    return {}


@router.get("/status")
async def status() -> dict:
    """Public status — flag + counts."""
    live = _live_flags()
    return {
        "enabled": _enabled(),
        "flag_env": _FLAG_ENV,
        "model_count": len(_CATALOG),
        "configured_count": sum(1 for r in _CATALOG if live.get(r["provider"])),
    }


_PAGE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Model Cookbook — LeadGen</title>
<style>
 body{font-family:system-ui,Segoe UI,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}
 .wrap{max-width:1200px;margin:0 auto;padding:24px}
 h1{margin:0 0 6px 0;font-size:22px}
 .sub{color:#94a3b8;margin-bottom:20px;font-size:13px}
 .card{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:16px;margin-bottom:16px}
 label{display:block;font-size:12px;color:#94a3b8;margin:8px 0 4px}
 input,select,textarea{width:100%;background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:8px;border-radius:6px;box-sizing:border-box}
 button{background:#3b82f6;color:#fff;border:0;padding:10px 16px;border-radius:6px;cursor:pointer;font-weight:600}
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{padding:8px 10px;border-bottom:1px solid #334155;text-align:left;vertical-align:top}
 th{color:#94a3b8}
 .pill{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;background:#334155;margin-right:4px}
 .pill.fast{background:#065f46;color:#a7f3d0}
 .pill.excellent{background:#1e40af;color:#bfdbfe}
 .pill.free{background:#065f46;color:#a7f3d0}
 .pill.metered{background:#7c2d12;color:#fed7aa}
 .badge{display:inline-block;padding:3px 8px;border-radius:4px;font-size:11px;font-weight:700;background:#065f46;color:#a7f3d0;margin-left:8px}
 .badge.off{background:#7f1d1d;color:#fecaca}
 .row{display:flex;gap:12px;flex-wrap:wrap}
 .row > *{flex:1;min-width:200px}
 .chain{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
 .chain .step{background:#0f172a;border:1px solid #334155;padding:6px 12px;border-radius:6px;font-family:ui-monospace,Menlo,monospace}
 .chain .step.live{border-color:#3b82f6;color:#3b82f6}
</style></head>
<body><div class="wrap">
 <h1>Model Cookbook · Niche → LLM Recipe</h1>
 <div class="sub">Free-tier providers ka catalog + kaunsa niche/task pe kaun best.</div>

 <div class="card">
  <h3 style="margin:0 0 12px 0;font-size:14px">Recommend a chain</h3>
  <div class="row">
   <div><label>Niche</label><select id="niche"></select></div>
   <div><label>Task (optional)</label><select id="task"><option value="">(auto from niche)</option></select></div>
   <div><label>Prefer</label><select id="pref">
    <option value="">balanced</option>
    <option value="speed">speed</option>
    <option value="quality">quality</option>
   </select></div>
   <div style="align-self:end"><button id="reco">Recommend</button></div>
  </div>
  <div id="reco_out" style="margin-top:14px"></div>
 </div>

 <div class="card">
  <h3 style="margin:0 0 12px 0;font-size:14px">Full catalog</h3>
  <table id="cat"><thead><tr>
   <th>Provider</th><th>Model</th><th>Speed</th><th>Quality</th><th>Multi-lang</th>
   <th>Cost</th><th>Rate limit</th><th>Best for</th><th>Status</th>
  </tr></thead><tbody></tbody></table>
 </div>
</div>
<script>
async function api(path, opts={}){ const r = await fetch('/api/cookbook'+path,{...opts,credentials:'include',
 headers:{'Content-Type':'application/json',...(opts.headers||{})}}); if(!r.ok) throw new Error(r.status);
 return r.json(); }

async function loadCatalog(){
  const j = await api('/models');
  document.querySelector('#cat tbody').innerHTML = j.models.map(m=>`
    <tr>
     <td><strong>${m.provider}</strong></td>
     <td style="font-family:ui-monospace,Menlo,monospace;font-size:12px;color:#94a3b8">${m.model}</td>
     <td><span class="pill ${m.speed}">${m.speed}</span></td>
     <td><span class="pill ${m.quality}">${m.quality}</span></td>
     <td><span class="pill">${m.multilingual}</span></td>
     <td><span class="pill ${m.cost.includes('free-un')?'free':(m.cost.includes('metered')?'metered':'')}">${m.cost}</span></td>
     <td style="font-size:12px;color:#94a3b8">${m.rate_limit}</td>
     <td style="font-size:12px">${(m.best_for||[]).map(t=>'<span class="pill">'+t+'</span>').join('')}</td>
     <td>${m.configured?'<span class="badge">CONFIGURED</span>':'<span class="badge off">no key</span>'}</td>
    </tr>`).join('');
}

async function loadTasks(){
  const j = await api('/tasks');
  document.getElementById('niche').innerHTML = j.niches.map(n=>`<option value="${n}">${n}</option>`).join('');
  document.getElementById('task').innerHTML = '<option value="">(auto from niche)</option>' +
    j.tasks.map(t=>`<option value="${t}">${t}</option>`).join('');
  document.getElementById('niche').value = 'generic';
}

document.getElementById('reco').onclick = async () => {
  const pref = document.getElementById('pref').value;
  const j = await api('/recommend', {method:'POST', body: JSON.stringify({
    niche: document.getElementById('niche').value,
    task: document.getElementById('task').value,
    prefer_speed: pref==='speed', prefer_quality: pref==='quality',
  })});
  document.getElementById('reco_out').innerHTML = `
    <div><strong>Top pick:</strong> <span class="badge">${j.top_pick||'—'}</span></div>
    <div style="margin-top:8px;font-size:12px;color:#94a3b8">${j.reason}</div>
    <div style="margin-top:12px"><strong>Live chain (only configured):</strong>
     <div class="chain">${j.recommended_live_chain.map(p=>'<span class="step live">'+p+'</span>').join('')}</div>
    </div>
    <div style="margin-top:12px"><strong>Full chain (curated):</strong>
     <div class="chain">${j.recommended_full_chain.map(p=>'<span class="step">'+p+'</span>').join('')}</div>
    </div>`;
};

loadTasks(); loadCatalog();
</script></body></html>
"""


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def cookbook_ui(_user=Depends(require_admin)) -> HTMLResponse:
    _require_enabled()
    return HTMLResponse(_PAGE_HTML)


__all__ = ["router"]
