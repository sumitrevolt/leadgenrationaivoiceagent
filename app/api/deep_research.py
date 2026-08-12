"""Deep Research — multi-step web research with cited synthesis.

Odysseus-inspired pattern (clean-room reimplement, AGPL-safe): "multi-step
web research with source reading and report generation." LeadGen already
runs SearXNG + agents; this module wraps them into a single
admin-callable "deep research" endpoint with a clean UI.

Flow:
    1) LLM plans N=3-5 sub-queries from the topic (free_ai.chat, bulk profile)
    2) Fanout SearXNG search for each sub-query (parallel)
    3) De-dupe + top-K sources
    4) LLM synthesizes a markdown report with numbered citations [1][2]...
    5) Return {report, sources[]}

Dependencies:
    - `app.integrations.searxng` (already ships, SEARXNG_URL gated)
    - `app.voice_agent.free_ai.chat` (existing free-tier chain)

Flag: `DEEP_RESEARCH_ENABLED=1` — INERT default (503 warna).

Budget: each request = ~4 LLM calls (1 plan + 3 sub-search summaries + 1
synthesis) + N SearXNG lookups. `budget_guard` scope="research" enforces.
Admin-only (require_admin) so no customer-triggered burn.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.integrations import searxng
from app.utils.logger import setup_logger
from app.voice_agent import free_ai

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/research/deep", tags=["Deep Research"])


_FLAG_ENV = "DEEP_RESEARCH_ENABLED"


def _enabled() -> bool:
    return (os.getenv(_FLAG_ENV, "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(status_code=503, detail=f"Deep Research disabled ({_FLAG_ENV}=0).")


# --------------------------- planner --------------------------- #


_PLAN_SYS = (
    "You are a research planner. Given a topic, output 3-5 short, specific "
    "web search queries that together answer it. One query per line. No numbering, "
    "no prose. Queries should be diverse (avoid semantic duplicates)."
)


async def _plan_queries(topic: str, max_queries: int = 4) -> list[str]:
    """Ask LLM for sub-queries. Falls back to topic-only on failure."""
    try:
        text, _ = await free_ai.chat(
            system=_PLAN_SYS,
            messages=[{"role": "user", "content": f"Topic: {topic}\nQueries:"}],
            max_tokens=220,
            temperature=0.3,
            scope="research",
            profile="bulk",
        )
    except Exception as e:
        logger.warning("[deep_research] plan LLM failed: %s", e)
        text = ""
    lines = [re.sub(r"^[\d\.\-\)\s]+", "", ln).strip() for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln and 4 <= len(ln) <= 200]
    seen: set[str] = set()
    out: list[str] = []
    for ln in lines:
        key = ln.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(ln)
        if len(out) >= max_queries:
            break
    return out or [topic]


# --------------------------- fetcher --------------------------- #


async def _search_one(q: str, count: int) -> list[dict[str, Any]]:
    try:
        return await searxng.search(q, count=count)
    except Exception as e:
        logger.info("[deep_research] search %r failed: %s", q[:60], e)
        return []


def _dedupe_sources(all_results: list[list[dict[str, Any]]], top_k: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for group in all_results:
        for r in group:
            url = (r.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(r)
            if len(out) >= top_k:
                return out
    return out


# --------------------------- synthesizer --------------------------- #


_SYNTH_SYS = (
    "You are a research analyst. Write a concise, factual markdown report on the "
    "topic using ONLY the numbered sources below. Cite claims inline as [1], [2], "
    "etc. Do NOT fabricate URLs. Use short paragraphs and 2-4 bullet points where "
    "helpful. End with a one-line 'Bottom line:' summary. Keep total under 500 words."
)


def _sources_prompt(sources: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, s in enumerate(sources, 1):
        title = str(s.get("title") or "").strip()[:180]
        url = str(s.get("url") or "").strip()
        content = str(s.get("content") or "").strip()[:400]
        lines.append(f"[{i}] {title}\nURL: {url}\nSnippet: {content}")
    return "\n\n".join(lines)


async def _synthesize(topic: str, sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "_No sources retrieved. SearXNG may be disabled (SEARXNG_URL unset) or unreachable._"
    try:
        text, _ = await free_ai.chat(
            system=_SYNTH_SYS,
            messages=[
                {
                    "role": "user",
                    "content": f"Topic: {topic}\n\nSources:\n{_sources_prompt(sources)}\n\nReport:",
                }
            ],
            max_tokens=900,
            temperature=0.35,
            scope="research",
            profile="bulk",
        )
    except Exception as e:
        logger.warning("[deep_research] synthesize failed: %s", e)
        text = ""
    return (text or "_Synthesis LLM returned empty._").strip()


# --------------------------- api --------------------------- #


class ResearchIn(BaseModel):
    topic: str = Field(..., min_length=3, max_length=400)
    max_queries: int = Field(default=4, ge=1, le=6)
    results_per_query: int = Field(default=6, ge=2, le=12)
    top_sources: int = Field(default=10, ge=3, le=20)


@router.post("/run")
async def run(payload: ResearchIn, _user=Depends(require_admin)) -> dict:
    _require_enabled()
    if not searxng.enabled():
        # Explicit failure so operator knows why report will be empty.
        raise HTTPException(
            status_code=503,
            detail="SearXNG disabled (SEARXNG_URL unset). Deep Research needs a search backend.",
        )
    t0 = time.monotonic()
    queries = await _plan_queries(payload.topic, payload.max_queries)
    # Parallel fanout
    fanout = await asyncio.gather(
        *[_search_one(q, payload.results_per_query) for q in queries],
        return_exceptions=False,
    )
    sources = _dedupe_sources(fanout, payload.top_sources)
    report = await _synthesize(payload.topic, sources)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[deep_research] topic=%r queries=%d sources=%d elapsed=%dms",
        payload.topic[:80],
        len(queries),
        len(sources),
        elapsed_ms,
    )
    return {
        "topic": payload.topic,
        "queries": queries,
        "sources": [
            {
                "idx": i + 1,
                "title": s.get("title"),
                "url": s.get("url"),
                "snippet": s.get("content"),
            }
            for i, s in enumerate(sources)
        ],
        "report_markdown": report,
        "elapsed_ms": elapsed_ms,
    }


@router.get("/status")
async def status() -> dict:
    return {
        "enabled": _enabled(),
        "flag_env": _FLAG_ENV,
        "searxng_enabled": searxng.enabled(),
    }


_PAGE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Deep Research — LeadGen</title>
<style>
 body{font-family:system-ui,Segoe UI,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}
 .wrap{max-width:1200px;margin:0 auto;padding:24px}
 h1{margin:0 0 6px 0;font-size:22px}
 .sub{color:#94a3b8;margin-bottom:20px;font-size:13px}
 .card{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:16px;margin-bottom:16px}
 input,textarea{width:100%;background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:8px;border-radius:6px;box-sizing:border-box}
 button{background:#3b82f6;color:#fff;border:0;padding:10px 16px;border-radius:6px;cursor:pointer;font-weight:600}
 button:disabled{background:#475569}
 .queries span{background:#334155;padding:4px 10px;border-radius:14px;font-size:12px;margin:2px;display:inline-block}
 .report{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:16px;white-space:pre-wrap;font-size:14px;line-height:1.6;max-height:70vh;overflow:auto}
 .src{padding:8px 0;border-bottom:1px solid #334155;font-size:13px}
 .src .t{color:#3b82f6;font-weight:600}
 .src .u{color:#64748b;font-size:11px;font-family:ui-monospace,Menlo,monospace;word-break:break-all}
 .src .s{color:#94a3b8;margin-top:4px;font-size:12px}
 .meta{color:#64748b;font-size:12px;margin-top:8px}
</style></head>
<body><div class="wrap">
 <h1>Deep Research · Multi-step + Cited</h1>
 <div class="sub">Topic → LLM plans sub-queries → SearXNG fanout → cited markdown report.</div>

 <div class="card">
  <input id="topic" placeholder="e.g. 'Best CRM options for Indian solar installers 2026'">
  <div style="margin-top:10px;display:flex;gap:10px">
   <button id="run">Research</button>
   <span id="msg" style="color:#94a3b8;font-size:12px;align-self:center"></span>
  </div>
 </div>

 <div id="qcard" class="card" style="display:none">
  <h3 style="margin:0 0 8px 0;font-size:14px;color:#94a3b8">Sub-queries</h3>
  <div id="queries" class="queries"></div>
  <div id="meta" class="meta"></div>
 </div>

 <div id="rcard" class="card" style="display:none">
  <h3 style="margin:0 0 8px 0;font-size:14px;color:#94a3b8">Report</h3>
  <div id="report" class="report"></div>
 </div>

 <div id="scard" class="card" style="display:none">
  <h3 style="margin:0 0 8px 0;font-size:14px;color:#94a3b8">Sources</h3>
  <div id="sources"></div>
 </div>
</div>
<script>
async function api(p,o={}){ const r = await fetch('/api/research/deep'+p,{...o,credentials:'include',
 headers:{'Content-Type':'application/json',...(o.headers||{})}}); if(!r.ok) throw new Error(r.status+': '+await r.text());
 return r.json(); }

const esc = (s) => (s||'').replace(/[<>&]/g, c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));

document.getElementById('run').onclick = async () => {
  const t = document.getElementById('topic').value.trim();
  if(!t){ document.getElementById('msg').textContent = 'Topic zaroori.'; return; }
  document.getElementById('run').disabled = true;
  document.getElementById('msg').textContent = 'Planning + searching + synthesizing...';
  ['qcard','rcard','scard'].forEach(id=>document.getElementById(id).style.display='none');
  try{
    const j = await api('/run', {method:'POST', body: JSON.stringify({topic: t})});
    document.getElementById('queries').innerHTML = j.queries.map(q=>'<span>'+esc(q)+'</span>').join('');
    document.getElementById('meta').textContent = j.sources.length+' sources · '+j.elapsed_ms+'ms';
    document.getElementById('report').textContent = j.report_markdown;
    document.getElementById('sources').innerHTML = j.sources.map(s=>`
      <div class="src"><div class="t">[${s.idx}] ${esc(s.title||'(no title)')}</div>
        <div class="u">${esc(s.url||'')}</div>
        <div class="s">${esc(s.snippet||'')}</div></div>`).join('');
    ['qcard','rcard','scard'].forEach(id=>document.getElementById(id).style.display='block');
    document.getElementById('msg').textContent = 'Done.';
  }catch(e){ document.getElementById('msg').textContent = 'Fail: '+e.message; }
  finally{ document.getElementById('run').disabled = false; }
};
</script></body></html>
"""


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def research_ui(_user=Depends(require_admin)) -> HTMLResponse:
    _require_enabled()
    return HTMLResponse(_PAGE_HTML)


__all__ = ["router"]
