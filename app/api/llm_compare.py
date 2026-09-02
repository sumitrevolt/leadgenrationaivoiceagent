"""LLM Compare — blind side-by-side model arena (admin-only, INERT default).

Kya karta hai
-------------
Odysseus-style "Compare" surface — ek prompt lo, N providers pe parallel run karo,
responses ko BLIND (A/B/C/... labels) admin ko dikhao, admin winner vote kare,
tabhi provider identity reveal ho jaati. Vote Redis me ELO-lite pair counters
me record hota (leaderboard).

Kaha fit hota
-------------
Aap ke 8+ free-LLM chain (free_ai.py — mistral/groq/cerebras/gemini/nvidia/
sambanova/openrouter x4) ke A/B testing ke liye. Objective evidence ki koi
provider "kaunse niche ke reply" pe best hai — chain reorder / model swap
decisions data-backed ho jaate hain.

Additive + INERT
----------------
`LLM_COMPARE_ENABLED=1` set na ho to poora router 503 return karta —
frontend page 404 rehta. Zero blast radius. Free stack only (koi paid AI
add nahi). Reuses free_ai.chat_provider() — koi naya external API call
pattern nahi.

License: LeadGen proprietary. Odysseus (AGPL) se sirf HIGH-LEVEL concept
(blind arena UX) liya hai — code independent. Kabhi Odysseus source me
peek nahi kiya.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger
from app.voice_agent import free_ai

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/llm/compare", tags=["LLM Compare"])

# --------------------------- flag / config --------------------------- #

_FLAG_ENV = "LLM_COMPARE_ENABLED"


def _enabled() -> bool:
    """INERT-default gate — env unset/0/false/no => OFF."""
    return (os.getenv(_FLAG_ENV, "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(
            status_code=503,
            detail=f"LLM Compare disabled ({_FLAG_ENV}=0). Admin ko flag enable karna hoga.",
        )


# --------------------------- provider registry --------------------------- #
# free_ai.py me har provider ka default model already set hai (module const).
# Aab we expose ONLY those that (a) have keys configured and (b) have a
# sensible default model. Admin UI se selectable list.

_DEFAULT_MODELS: dict[str, str] = {
    "cerebras": getattr(free_ai, "_CEREBRAS_LLM_MODEL", "gpt-oss-120b"),
    "groq": getattr(free_ai, "_GROQ_LLM_MODEL", "llama-3.1-8b-instant"),
    "gemini": getattr(free_ai, "_GEMINI_LLM_MODEL", "gemini-2.5-flash"),
    "sambanova": getattr(free_ai, "_SAMBANOVA_LLM_MODEL", "Meta-Llama-3.3-70B-Instruct"),
    "mistral": getattr(free_ai, "_MISTRAL_LLM_MODEL", "mistral-small-latest"),
    "nvidia": getattr(free_ai, "_NVIDIA_LLM_MODEL", "meta/llama-3.3-70b-instruct"),
    "openrouter": getattr(
        free_ai, "_OPENROUTER_LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
    ),
    "openrouter_2": getattr(free_ai, "_OPENROUTER_LLM_MODEL2", "openai/gpt-oss-20b:free"),
    "openrouter_3": getattr(free_ai, "_OPENROUTER_LLM_MODEL3", "google/gemma-4-31b-it:free"),
}


def _list_available_providers() -> list[dict[str, Any]]:
    """Live snapshot — sirf woh providers jinka key + SDK dono hain."""
    try:
        live = free_ai._provider_flags()  # {provider: bool}
    except Exception:
        live = getattr(free_ai, "PROVIDERS_AVAILABLE", {}) or {}
    out: list[dict[str, Any]] = []
    for prov, model in _DEFAULT_MODELS.items():
        ok = bool(live.get(prov))
        out.append({"provider": prov, "model": model, "available": ok})
    # deterministic order — available first, then alpha
    out.sort(key=lambda x: (not x["available"], x["provider"]))
    return out


# --------------------------- redis-lite store --------------------------- #
# Runs (blind-map + prompt + timing) 60min TTL Redis me. Vote karte hi Redis
# HINCRBY se pair counters bump hote. Redis nahi = in-process dict fallback
# (dev only, restart pe khoya, aata rahega).

_RUN_TTL_S = 60 * 60  # 60min
_INMEM: dict[str, dict[str, Any]] = {}
_INMEM_VOTES: dict[str, int] = {}


async def _redis():
    try:
        from app import cache

        return await cache.get_redis_client()
    except Exception:
        return None


async def _save_run(run_id: str, payload: dict[str, Any]) -> None:
    r = await _redis()
    key = f"llm_compare:run:{run_id}"
    blob = json.dumps(payload, default=str)
    if r is not None:
        try:
            await r.set(key, blob, ex=_RUN_TTL_S)
            return
        except Exception as e:
            logger.warning("[llm_compare] redis save failed, in-mem fallback: %s", e)
    _INMEM[run_id] = payload


async def _load_run(run_id: str) -> dict[str, Any] | None:
    r = await _redis()
    key = f"llm_compare:run:{run_id}"
    if r is not None:
        try:
            blob = await r.get(key)
            if blob:
                if isinstance(blob, bytes):
                    blob = blob.decode("utf-8", errors="ignore")
                return json.loads(blob)
        except Exception as e:
            logger.warning("[llm_compare] redis load failed: %s", e)
    return _INMEM.get(run_id)


async def _bump_vote(provider: str) -> int:
    r = await _redis()
    key = f"llm_compare:votes:{provider}"
    if r is not None:
        try:
            return int(await r.incr(key))
        except Exception:
            pass
    _INMEM_VOTES[provider] = _INMEM_VOTES.get(provider, 0) + 1
    return _INMEM_VOTES[provider]


async def _bump_run(provider: str) -> int:
    r = await _redis()
    key = f"llm_compare:runs:{provider}"
    if r is not None:
        try:
            return int(await r.incr(key))
        except Exception:
            pass
    return 0


async def _read_stats() -> list[dict[str, Any]]:
    r = await _redis()
    rows: list[dict[str, Any]] = []
    for prov in _DEFAULT_MODELS.keys():
        wins = 0
        runs = 0
        if r is not None:
            try:
                w = await r.get(f"llm_compare:votes:{prov}")
                if w:
                    wins = int(w if not isinstance(w, bytes) else w.decode())
                s = await r.get(f"llm_compare:runs:{prov}")
                if s:
                    runs = int(s if not isinstance(s, bytes) else s.decode())
            except Exception:
                pass
        if wins == 0 and runs == 0:
            wins = _INMEM_VOTES.get(prov, 0)
        win_rate = (wins / runs) if runs else 0.0
        rows.append(
            {
                "provider": prov,
                "model": _DEFAULT_MODELS[prov],
                "runs": runs,
                "wins": wins,
                "win_rate": round(win_rate, 3),
            }
        )
    rows.sort(key=lambda x: (-x["win_rate"], -x["wins"]))
    return rows


# --------------------------- pydantic models --------------------------- #


class CompareRunIn(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    providers: list[str] = Field(
        default_factory=list, description="Provider IDs; empty = all available"
    )
    system: str = Field(default="", max_length=4000)
    max_tokens: int = Field(default=512, ge=32, le=4096)
    temperature: float = Field(default=0.5, ge=0.0, le=2.0)


class CompareVoteIn(BaseModel):
    run_id: str = Field(..., min_length=8, max_length=64)
    winner_label: str = Field(..., min_length=1, max_length=4, description="Blind label e.g. 'A'")


# --------------------------- endpoints --------------------------- #


@router.get("/providers")
async def list_providers(_user=Depends(require_admin)) -> dict:
    _require_enabled()
    return {"enabled": True, "providers": _list_available_providers()}


@router.get("/stats")
async def stats(_user=Depends(require_admin)) -> dict:
    _require_enabled()
    return {"leaderboard": await _read_stats()}


@router.post("/run")
async def run_compare(payload: CompareRunIn, _user=Depends(require_admin)) -> dict:
    """Parallel fanout — blind labels A/B/C/... map server-side."""
    _require_enabled()

    # 1) filter to configured providers
    live = _list_available_providers()
    available_ids = {p["provider"] for p in live if p["available"]}
    requested = [p for p in payload.providers if p] or sorted(available_ids)
    requested = [p for p in requested if p in available_ids]

    # sane bounds — atleast 2, at most 6 (fanout burn control)
    if len(requested) < 2:
        raise HTTPException(status_code=400, detail="At least 2 available providers required.")
    if len(requested) > 6:
        requested = requested[:6]

    # 2) fanout — chat_provider (no chain fallback, single call per provider)
    msgs = [{"role": "user", "content": payload.prompt}]

    async def _one(prov: str) -> dict[str, Any]:
        t0 = time.monotonic()
        try:
            text, prov_id = await free_ai.chat_provider(
                provider=prov,
                model=_DEFAULT_MODELS.get(prov, ""),
                system=payload.system or "",
                messages=msgs,
                max_tokens=payload.max_tokens,
                temperature=payload.temperature,
                scope="compare",
            )
        except Exception as e:
            logger.warning("[llm_compare] provider %s raised: %s", prov, e)
            text, prov_id = "", prov
        return {
            "provider": prov_id or prov,
            "text": text or "",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    results = await asyncio.gather(*[_one(p) for p in requested], return_exceptions=False)

    # 3) blind labeling
    labels = "ABCDEF"
    entries: list[dict[str, Any]] = []
    blind_map: dict[str, str] = {}
    for i, r in enumerate(results):
        label = labels[i]
        entries.append(
            {
                "label": label,
                "text": r["text"],
                "latency_ms": r["latency_ms"],
                "empty": not bool(r["text"].strip()),
            }
        )
        blind_map[label] = r["provider"]
        try:
            await _bump_run(r["provider"])
        except Exception:
            pass

    run_id = secrets.token_urlsafe(12)
    saved = {
        "prompt": payload.prompt[:2000],
        "system": (payload.system or "")[:1000],
        "blind_map": blind_map,
        "created_at": int(time.time()),
        "voted_label": None,
    }
    await _save_run(run_id, saved)

    return {
        "run_id": run_id,
        "entries": entries,  # NO provider names revealed
        "count": len(entries),
    }


@router.post("/vote")
async def vote(payload: CompareVoteIn, _user=Depends(require_admin)) -> dict:
    """Reveal blind mapping + record winner. Idempotent (double-vote = 400)."""
    _require_enabled()
    run = await _load_run(payload.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found or expired.")
    if run.get("voted_label"):
        raise HTTPException(status_code=400, detail="Already voted for this run.")
    label = payload.winner_label.strip().upper()
    if label not in (run.get("blind_map") or {}):
        raise HTTPException(status_code=400, detail=f"Unknown label '{label}'.")

    winner_provider = run["blind_map"][label]
    await _bump_vote(winner_provider)
    run["voted_label"] = label
    await _save_run(payload.run_id, run)

    return {
        "run_id": payload.run_id,
        "winner_label": label,
        "winner_provider": winner_provider,
        "reveal": run["blind_map"],
    }


@router.get("/status")
async def status(request: Request) -> dict:
    """Public status — flag on/off. No auth so admin dashboard can peek."""
    return {
        "enabled": _enabled(),
        "flag_env": _FLAG_ENV,
        "provider_count": len([p for p in _list_available_providers() if p["available"]]),
    }


# --------------------------- html page --------------------------- #

_PAGE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>LLM Compare — Blind Arena</title>
<style>
 body{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}
 .wrap{max-width:1200px;margin:0 auto;padding:24px}
 h1{margin:0 0 6px 0;font-size:22px}
 .sub{color:#94a3b8;margin-bottom:20px;font-size:13px}
 .card{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:16px;margin-bottom:16px}
 label{display:block;font-size:12px;color:#94a3b8;margin:8px 0 4px}
 textarea,input,select{width:100%;background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:8px;border-radius:6px;font-family:inherit;box-sizing:border-box}
 textarea{min-height:120px;resize:vertical;font-family:ui-monospace,Menlo,monospace}
 button{background:#3b82f6;color:#fff;border:0;padding:10px 16px;border-radius:6px;cursor:pointer;font-weight:600}
 button:disabled{background:#475569;cursor:not-allowed}
 button.ghost{background:transparent;border:1px solid #475569;color:#e2e8f0}
 .row{display:flex;gap:12px;flex-wrap:wrap}
 .col{flex:1;min-width:280px}
 .arena{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:12px}
 .entry{background:#0f172a;border:2px solid #334155;border-radius:8px;padding:12px;display:flex;flex-direction:column}
 .entry .label{font-size:28px;font-weight:800;color:#3b82f6;margin-bottom:6px}
 .entry .meta{font-size:11px;color:#64748b;margin-bottom:8px}
 .entry .text{white-space:pre-wrap;font-size:13px;line-height:1.5;flex:1;overflow:auto;max-height:400px}
 .entry.winner{border-color:#10b981;background:#052e1a}
 .entry .reveal{font-size:12px;color:#10b981;margin-top:8px;font-weight:700}
 .provs{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
 .prov{background:#334155;padding:4px 10px;border-radius:14px;font-size:12px;cursor:pointer;user-select:none}
 .prov.on{background:#3b82f6}
 .prov.off{opacity:.5;text-decoration:line-through;cursor:not-allowed}
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{padding:6px 8px;border-bottom:1px solid #334155;text-align:left}
 th{color:#94a3b8;font-weight:600}
 .warn{background:#7c2d12;color:#fed7aa;padding:8px 12px;border-radius:6px;margin-bottom:12px;font-size:13px}
</style></head>
<body><div class="wrap">
 <h1>LLM Compare · Blind Arena</h1>
 <div class="sub">Same prompt → parallel run across free-tier providers → vote blind → data-backed chain tuning.</div>
 <div id="warn"></div>

 <div class="card">
  <div class="row">
   <div class="col">
    <label>System (optional)</label>
    <textarea id="sys" placeholder="e.g. 'Ek friendly Hinglish sales assistant ho.'"></textarea>
   </div>
   <div class="col">
    <label>Prompt</label>
    <textarea id="prompt" placeholder="Test prompt (e.g. 'Salon owner ko cold-call ka 3-line pitch likh')"></textarea>
   </div>
  </div>
  <label>Providers</label>
  <div id="provs" class="provs"></div>
  <div style="margin-top:12px;display:flex;gap:8px;align-items:center">
   <button id="run">Run Compare</button>
   <button id="refresh" class="ghost">Refresh Stats</button>
   <span id="msg" style="color:#94a3b8;font-size:12px"></span>
  </div>
 </div>

 <div id="arena" class="arena"></div>

 <div class="card">
  <h3 style="margin:0 0 8px 0;font-size:14px;color:#94a3b8">Leaderboard (session-wide, Redis-backed)</h3>
  <table id="board"><thead><tr><th>Provider</th><th>Model</th><th>Runs</th><th>Wins</th><th>Win rate</th></tr></thead><tbody></tbody></table>
 </div>
</div>
<script>
const $ = (id) => document.getElementById(id);
let PROVS = [];
let SEL = new Set();
let CURRENT = null;

async function api(path, opts={}){
  const r = await fetch('/api/llm/compare'+path, {...opts, credentials:'include',
    headers:{'Content-Type':'application/json', ...(opts.headers||{})}});
  if(!r.ok){ const t = await r.text(); throw new Error(r.status+': '+t); }
  return r.json();
}

async function loadProviders(){
  try{
    const j = await api('/providers');
    PROVS = j.providers || [];
    SEL = new Set(PROVS.filter(p=>p.available).slice(0,4).map(p=>p.provider));
    renderProvs();
  }catch(e){
    $('warn').innerHTML = '<div class="warn">Providers load failed: '+e.message+'</div>';
  }
}
function renderProvs(){
  $('provs').innerHTML = PROVS.map(p => {
    const cls = !p.available ? 'prov off' : (SEL.has(p.provider) ? 'prov on' : 'prov');
    return `<span class="${cls}" data-p="${p.provider}" title="${p.model}">${p.provider}</span>`;
  }).join('');
  $('provs').querySelectorAll('.prov').forEach(el=>{
    el.onclick = () => {
      const p = el.dataset.p;
      const meta = PROVS.find(x=>x.provider===p);
      if(!meta || !meta.available) return;
      if(SEL.has(p)) SEL.delete(p); else SEL.add(p);
      renderProvs();
    };
  });
}

$('run').onclick = async () => {
  const prompt = $('prompt').value.trim();
  if(!prompt){ $('msg').textContent = 'Prompt zaroori hai.'; return; }
  if(SEL.size < 2){ $('msg').textContent = 'Kam se kam 2 providers chuno.'; return; }
  $('run').disabled = true;
  $('msg').textContent = 'Running ('+SEL.size+' providers, parallel)...';
  $('arena').innerHTML = '';
  CURRENT = null;
  try{
    const j = await api('/run', {method:'POST', body: JSON.stringify({
      prompt, system: $('sys').value, providers: [...SEL],
      max_tokens: 512, temperature: 0.5
    })});
    CURRENT = j;
    renderArena(j.entries);
    $('msg').textContent = 'Vote karo — winner reveal karega.';
  }catch(e){
    $('msg').textContent = 'Fail: '+e.message;
  }finally{ $('run').disabled = false; }
};

function renderArena(entries){
  $('arena').innerHTML = entries.map(e => `
    <div class="entry" data-label="${e.label}">
      <div class="label">${e.label}</div>
      <div class="meta">${e.latency_ms} ms ${e.empty ? '· <span style="color:#f87171">EMPTY</span>' : ''}</div>
      <div class="text">${(e.text||'(no response)').replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}</div>
      <button class="vote-btn" style="margin-top:10px">Vote ${e.label} as winner</button>
    </div>`).join('');
  $('arena').querySelectorAll('.vote-btn').forEach((btn,i)=>{
    btn.onclick = () => vote(entries[i].label);
  });
}

async function vote(label){
  if(!CURRENT) return;
  try{
    const j = await api('/vote', {method:'POST', body: JSON.stringify({
      run_id: CURRENT.run_id, winner_label: label
    })});
    // reveal
    document.querySelectorAll('.entry').forEach(el=>{
      const lab = el.dataset.label;
      const prov = j.reveal[lab];
      const rev = document.createElement('div');
      rev.className='reveal';
      rev.textContent = (lab===j.winner_label ? '★ WINNER · ' : '') + prov;
      el.appendChild(rev);
      if(lab===j.winner_label) el.classList.add('winner');
      el.querySelector('.vote-btn')?.remove();
    });
    $('msg').textContent = 'Winner: '+j.winner_provider;
    loadStats();
  }catch(e){ $('msg').textContent = 'Vote fail: '+e.message; }
}

async function loadStats(){
  try{
    const j = await api('/stats');
    const tb = $('board').querySelector('tbody');
    tb.innerHTML = (j.leaderboard||[]).map(r=>`
      <tr><td>${r.provider}</td><td style="color:#64748b;font-size:12px">${r.model}</td>
       <td>${r.runs}</td><td>${r.wins}</td><td>${(r.win_rate*100).toFixed(1)}%</td></tr>`).join('');
  }catch(e){}
}
$('refresh').onclick = loadStats;

loadProviders();
loadStats();
</script></body></html>
"""


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def compare_ui(_user=Depends(require_admin)) -> HTMLResponse:
    _require_enabled()
    return HTMLResponse(_PAGE_HTML)


__all__ = ["router"]
