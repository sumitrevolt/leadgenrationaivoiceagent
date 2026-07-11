"""Docs AI-Edit — writing-first editor with AI actions.

Odysseus-inspired pattern (clean-room reimplement, AGPL-safe): "writing-first
editor with AI edits, suggestions, Markdown, HTML, CSV." Yahan minimal but
useful subset — plain-text editor (browser textarea) + toolbar of AI actions.

Actions (each = LLM call via free_ai.chat, bulk profile):
    improve       : rewrite for clarity + flow
    shorten       : trim to ~50% length keeping key points
    expand        : add helpful detail, examples
    fix_grammar   : correct spelling/grammar only, preserve style
    change_tone   : rewrite in target tone (formal|casual|persuasive|hinglish|hindi)
    summarize     : 3-4 bullet summary
    translate     : Hinglish ↔ English convenience

Endpoint: POST /api/docs/edit  → {edited_text, action, tokens_used_estimate}
UI:       GET  /api/docs/edit/ui  → single-page editor

Flag: `DOCS_AI_EDIT_ENABLED=1` — INERT default (503).

Where it fits: /app/office HQ, /app/inbox reply drafts, campaign copy,
customer marketing_studio content editor. Reusable by any admin/customer
surface without re-implementing prompt engineering.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger
from app.voice_agent import free_ai

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/docs/edit", tags=["Docs AI Edit"])


_FLAG_ENV = "DOCS_AI_EDIT_ENABLED"


def _enabled() -> bool:
    return (os.getenv(_FLAG_ENV, "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(status_code=503, detail=f"Docs AI-Edit disabled ({_FLAG_ENV}=0).")


# --------------------------- prompt library --------------------------- #


_ACTION_PROMPTS: dict[str, str] = {
    "improve": (
        "Rewrite the user's text for clarity, flow, and impact. Preserve meaning "
        "and voice. Return ONLY the rewritten text, no preamble."
    ),
    "shorten": (
        "Rewrite the user's text at ~50% length. Keep the core message and any "
        "concrete facts. Return ONLY the shorter text."
    ),
    "expand": (
        "Expand the user's text with helpful detail, one concrete example, and "
        "smooth transitions. Do not pad with fluff. Return ONLY the expanded text."
    ),
    "fix_grammar": (
        "Fix spelling, grammar, and punctuation in the user's text. Preserve "
        "voice, structure, and formatting. Return ONLY the corrected text."
    ),
    "summarize": (
        "Summarize the user's text as 3-4 short markdown bullet points. "
        "Return ONLY the bullets, no preamble."
    ),
    "translate_hi": (
        "Translate the user's text to Hinglish (Roman script Hindi) suitable for "
        "Indian small-business customer chat. Return ONLY the translated text."
    ),
    "translate_en": (
        "Translate the user's text to clear, business-appropriate English. "
        "Return ONLY the translated text."
    ),
}


_TONES: dict[str, str] = {
    "formal": "formal, professional",
    "casual": "warm, conversational",
    "persuasive": "persuasive, high-agency, benefit-first",
    "hinglish": "friendly Hinglish (Hindi in Roman script mixed with English)",
    "hindi": "polite Hindi (Devanagari)",
}


def _tone_prompt(tone: str) -> str:
    tone_desc = _TONES.get(tone.lower().strip(), "clear and neutral")
    return (
        f"Rewrite the user's text in a {tone_desc} tone. Preserve meaning "
        f"and factual details. Return ONLY the rewritten text."
    )


# --------------------------- api --------------------------- #

_ALLOWED_ACTIONS = set(_ACTION_PROMPTS.keys()) | {"change_tone"}


class EditIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    action: str = Field(..., min_length=1, max_length=40)
    tone: str = Field(default="casual", max_length=20)  # only used if action==change_tone


@router.get("/actions")
async def list_actions(_user=Depends(require_admin)) -> dict:
    _require_enabled()
    return {
        "actions": sorted(_ALLOWED_ACTIONS),
        "tones": sorted(_TONES.keys()),
    }


@router.post("/run")
async def run_edit(payload: EditIn, _user=Depends(require_admin)) -> dict:
    _require_enabled()
    action = (payload.action or "").lower().strip()
    if action not in _ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action '{action}'. Allowed: {sorted(_ALLOWED_ACTIONS)}",
        )
    if action == "change_tone":
        system = _tone_prompt(payload.tone)
    else:
        system = _ACTION_PROMPTS[action]

    # Bulk profile for content generation (higher throughput chain)
    try:
        text, provider = await free_ai.chat(
            system=system,
            messages=[{"role": "user", "content": payload.text}],
            max_tokens=1200,
            temperature=0.55,
            scope="docs_edit",
            profile="bulk",
        )
    except Exception as e:
        logger.warning("[docs_ai_edit] free_ai.chat failed: %s", e)
        raise HTTPException(status_code=502, detail="LLM chain unavailable.")

    edited = (text or "").strip()
    if not edited:
        raise HTTPException(status_code=502, detail="LLM returned empty — retry with fewer tokens.")

    return {
        "action": action,
        "tone": payload.tone if action == "change_tone" else None,
        "input_chars": len(payload.text),
        "output_chars": len(edited),
        "edited_text": edited,
        "provider": provider or "unknown",
    }


@router.get("/status")
async def status() -> dict:
    return {"enabled": _enabled(), "flag_env": _FLAG_ENV, "action_count": len(_ALLOWED_ACTIONS)}


_PAGE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Docs AI Edit — LeadGen</title>
<style>
 body{font-family:system-ui,Segoe UI,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}
 .wrap{max-width:1200px;margin:0 auto;padding:24px}
 h1{margin:0 0 6px 0;font-size:22px}
 .sub{color:#94a3b8;margin-bottom:20px;font-size:13px}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
 .col{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px;display:flex;flex-direction:column}
 h3{margin:0 0 8px 0;font-size:14px;color:#94a3b8}
 textarea{flex:1;min-height:420px;width:100%;background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:10px;border-radius:6px;font-family:ui-monospace,Menlo,monospace;font-size:13px;box-sizing:border-box;resize:vertical}
 .toolbar{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
 button.tool{background:#334155;color:#e2e8f0;border:0;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600}
 button.tool:hover{background:#3b82f6}
 button.tool:disabled{background:#475569;cursor:not-allowed}
 select{background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:5px 8px;border-radius:6px;font-size:12px}
 .meta{color:#64748b;font-size:11px;margin-top:6px}
 button.copy{background:#065f46;color:#a7f3d0;font-size:12px;border:0;padding:6px 12px;border-radius:6px;cursor:pointer;margin-top:6px;font-weight:600}
 @media (max-width:900px){.grid{grid-template-columns:1fr}}
</style></head>
<body><div class="wrap">
 <h1>Docs AI-Edit · Writing surface</h1>
 <div class="sub">Left me likho, action chuno, right me AI edit.</div>

 <div class="toolbar" id="toolbar">
  <button class="tool" data-a="improve">Improve</button>
  <button class="tool" data-a="shorten">Shorten</button>
  <button class="tool" data-a="expand">Expand</button>
  <button class="tool" data-a="fix_grammar">Fix grammar</button>
  <button class="tool" data-a="summarize">Summarize</button>
  <button class="tool" data-a="translate_hi">→ Hinglish</button>
  <button class="tool" data-a="translate_en">→ English</button>
  <select id="tone">
   <option value="casual">casual</option>
   <option value="formal">formal</option>
   <option value="persuasive">persuasive</option>
   <option value="hinglish">hinglish</option>
   <option value="hindi">hindi</option>
  </select>
  <button class="tool" data-a="change_tone">Change tone</button>
  <span id="msg" style="align-self:center;color:#94a3b8;font-size:12px;margin-left:10px"></span>
 </div>

 <div class="grid">
  <div class="col"><h3>Input</h3>
   <textarea id="in" placeholder="Yahan likho ya paste karo..."></textarea>
   <div class="meta" id="in_meta">0 chars</div>
  </div>
  <div class="col"><h3>AI Output</h3>
   <textarea id="out" placeholder="(AI edit yahan aayega)"></textarea>
   <div class="meta" id="out_meta">—</div>
   <div><button class="copy" id="copy">Copy · Replace input</button></div>
  </div>
 </div>
</div>
<script>
async function api(p,o={}){ const r = await fetch('/api/docs/edit'+p,{...o,credentials:'include',
 headers:{'Content-Type':'application/json',...(o.headers||{})}}); if(!r.ok) throw new Error(r.status+': '+await r.text());
 return r.json(); }

const $in = document.getElementById('in');
const $out = document.getElementById('out');
$in.addEventListener('input', ()=>document.getElementById('in_meta').textContent = $in.value.length+' chars');

async function runAction(action){
  const text = $in.value.trim();
  if(!text){ document.getElementById('msg').textContent = 'Input khaali.'; return; }
  document.querySelectorAll('button.tool').forEach(b=>b.disabled=true);
  document.getElementById('msg').textContent = 'Running '+action+'...';
  try{
    const j = await api('/run', {method:'POST', body: JSON.stringify({
      text, action, tone: document.getElementById('tone').value,
    })});
    $out.value = j.edited_text;
    document.getElementById('out_meta').textContent = j.output_chars+' chars · '+j.provider+' · '+j.action;
    document.getElementById('msg').textContent = 'Done.';
  }catch(e){ document.getElementById('msg').textContent = 'Fail: '+e.message; }
  finally{ document.querySelectorAll('button.tool').forEach(b=>b.disabled=false); }
}
document.querySelectorAll('button.tool').forEach(b=>{
  b.onclick = () => runAction(b.dataset.a);
});
document.getElementById('copy').onclick = () => {
  if(!$out.value){ return; }
  $in.value = $out.value; $in.dispatchEvent(new Event('input'));
  $out.value = '';
  document.getElementById('msg').textContent = 'Replaced input with output.';
};
</script></body></html>
"""


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def docs_ui(_user=Depends(require_admin)) -> HTMLResponse:
    _require_enabled()
    return HTMLResponse(_PAGE_HTML)


__all__ = ["router"]
