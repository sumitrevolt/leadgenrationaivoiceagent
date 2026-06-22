"""Embeddable lead-capture widget — client apni KISI BHI website pe ek line paste kare,
floating "Enquiry" button + form (ya AI CHAT) aa jata hai. Submissions seedha leads
dashboard me (reuses POST /api/public/inquiry + source_slug → client auto-resolve).

CORS-free design: form ek IFRAME me hamare origin (leadsgenai.in) se serve hota hai,
isliye cross-origin POST ki zaroorat nahi (Calendly/Tally jaisa). Fulfils Growth-tier
"Website lead-capture form setup". Pure-string module, never raises.

  embed_page_html(client) -> full HTML page (served at /b/{slug}/embed, iframe-able).
                             ?mode=chat query par CHAT UI (AI assistant, /api/public/
                             widget-chat) — default FORM = zero behaviour change.
  widget_js(slug)         -> JS injector (served at /b/{slug}/widget.js). Script src me
                             ?mode=chat ho to chat-mode iframe kholta hai.
  snippet(slug, mode)     -> copy-paste <script> one-liner for the client
  default_fields()        -> form-builder-lite ke default fields (current form)
  get_form_config(slug)   -> per-slug custom fields (data/widget_forms.jsonl) | None
  save_form_config(slug, fields) -> validate + append config (admin endpoint use karta)
"""

from __future__ import annotations

import html
import json
import os
import re

_FORMS_FILE = os.path.join("data", "widget_forms.jsonl")

_ALLOWED_TYPES = {"text", "tel", "email", "select"}
_NAME_RE = re.compile(r"[^a-z0-9_]")


def site_base() -> str:
    """Public base URL (widget iframe ke absolute src ke liye)."""
    for k in ("PUBLIC_BASE_URL", "SITE_BASE", "PUBLIC_SITE_BASE"):
        v = (os.getenv(k) or "").strip().rstrip("/")
        if v:
            return v
    return "https://leadsgenai.in"


def _brand_color(client: dict) -> str:
    for k in ("brand_color", "primary_color", "color", "theme_color"):
        v = str((client or {}).get(k) or "").strip()
        if v.startswith("#") and 4 <= len(v) <= 9:
            return v
    return "#2563eb"


# --------------------------------------------------------------------------- #
# Form-builder-lite — per-slug custom fields (data/widget_forms.jsonl)
# --------------------------------------------------------------------------- #
def default_fields() -> list[dict]:
    """Aaj ka form jaisa-ka-taisa (zero behaviour change bina config)."""
    return [
        {"name": "name", "label": "Naam *", "type": "text", "required": True},
        {"name": "phone", "label": "Phone *", "type": "tel", "required": True},
        {"name": "message", "label": "Message (optional)", "type": "text", "required": False},
    ]


def _clean_field(f: dict) -> dict | None:
    """Ek field config validate/normalize karo (galat = None, skip)."""
    try:
        if not isinstance(f, dict):
            return None
        name = _NAME_RE.sub("", str(f.get("name") or "").strip().lower())[:40]
        if not name:
            return None
        ftype = str(f.get("type") or "text").strip().lower()
        if ftype not in _ALLOWED_TYPES:
            ftype = "text"
        label = str(f.get("label") or name.replace("_", " ").title()).strip()[:80]
        options: list[str] = []
        if ftype == "select":
            raw = f.get("options") or []
            if isinstance(raw, list):
                options = [str(o).strip()[:60] for o in raw if str(o).strip()][:15]
            if not options:
                ftype = "text"  # select bina options = text
        return {
            "name": name,
            "label": label,
            "type": ftype,
            "required": bool(f.get("required")),
            "options": options,
        }
    except Exception:
        return None


def get_form_config(slug: str) -> list[dict] | None:
    """Per-slug custom form fields (last write wins) — None = default form."""
    try:
        key = (slug or "").strip().lower()
        if not key or not os.path.isfile(_FORMS_FILE):
            return None
        found: list[dict] | None = None
        with open(_FORMS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict) and str(rec.get("slug") or "").lower() == key:
                    flds = [c for c in (_clean_field(x) for x in (rec.get("fields") or [])) if c]
                    found = flds or None
        return found
    except Exception:
        return None


def save_form_config(slug: str, fields: list[dict]) -> dict:
    """Custom fields save karo (append-only jsonl). Never raises."""
    try:
        key = (slug or "").strip().lower()
        if not key:
            return {"ok": False, "error": "slug required"}
        clean = [c for c in (_clean_field(x) for x in (fields or [])) if c][:10]
        if not clean:
            return {"ok": False, "error": "koi valid field nahi mila"}
        rec = {"slug": key, "fields": clean}
        os.makedirs(os.path.dirname(_FORMS_FILE) or ".", exist_ok=True)
        with open(_FORMS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"ok": True, "slug": key, "fields": clean}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def _effective_fields(slug: str) -> list[dict]:
    """Config + safety: name/phone hamesha present (inquiry API inhe maangta hai)."""
    try:
        cfg = get_form_config(slug) or default_fields()
        names = {f["name"] for f in cfg}
        prepend: list[dict] = []
        if "name" not in names:
            prepend.append(
                {"name": "name", "label": "Naam *", "type": "text", "required": True, "options": []}
            )
        if "phone" not in names:
            prepend.append(
                {
                    "name": "phone",
                    "label": "Phone *",
                    "type": "tel",
                    "required": True,
                    "options": [],
                }
            )
        return prepend + cfg
    except Exception:
        return default_fields()


def _field_html(f: dict) -> str:
    """Ek field ka HTML (escaped). data-lgf=name, data-lgl=label, data-lgr=required."""
    name = html.escape(str(f.get("name") or ""))
    label = html.escape(str(f.get("label") or name))
    ftype = str(f.get("type") or "text")
    req = ' data-lgr="1" required' if f.get("required") else ""
    fid = f"lgF_{name}"
    attrs = f'id="{fid}" data-lgf="{name}" data-lgl="{label}"{req}'
    if name == "message":
        return (
            f'<label for="{fid}">{label}</label>'
            f'<textarea {attrs} maxlength="1000" placeholder="Aapko kya chahiye?"></textarea>'
        )
    if ftype == "select":
        opts = "".join(
            f'<option value="{html.escape(str(o))}">{html.escape(str(o))}</option>'
            for o in (f.get("options") or [])
        )
        return f'<label for="{fid}">{label}</label><select {attrs}><option value="">-- choose --</option>{opts}</select>'
    extra = ' inputmode="numeric" placeholder="10-digit mobile"' if ftype == "tel" else ""
    return (
        f'<label for="{fid}">{label}</label><input {attrs} type="{ftype}" maxlength="200"{extra} />'
    )


# --------------------------------------------------------------------------- #
# Embed page (iframe content) — FORM default, ?mode=chat = AI chat UI
# --------------------------------------------------------------------------- #
def embed_page_html(client: dict) -> str:
    """Standalone branded page (iframe content). Form POST → /api/public/inquiry;
    chat mode POST → /api/public/widget-chat. Mode CLIENT-SIDE query (?mode=chat)
    se decide hota — server route untouched (main.py edit nahi chahiye)."""
    client = client or {}
    biz = html.escape(str(client.get("business_name") or "Hamse judiye"))
    slug = html.escape(str(client.get("slug") or ""))
    color = _brand_color(client)
    try:
        fields_html = "".join(_field_html(f) for f in _effective_fields(slug))
    except Exception:
        fields_html = "".join(_field_html(f) for f in default_fields())
    return f"""<!doctype html><html lang="hi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{biz} — Enquiry</title>
<style>
 *{{box-sizing:border-box}}
 html,body{{height:100%}}
 body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#fff;color:#111}}
 .wrap{{padding:18px 16px}}
 h2{{margin:0 0 2px;font-size:18px}}
 .sub{{color:#666;font-size:13px;margin-bottom:14px}}
 label{{display:block;font-size:13px;font-weight:600;margin:10px 0 4px}}
 input,textarea,select{{width:100%;padding:11px 12px;border:1px solid #d4d4d8;border-radius:10px;font-size:15px;font-family:inherit;background:#fff}}
 input:focus,textarea:focus,select:focus{{outline:none;border-color:{color};box-shadow:0 0 0 3px {color}22}}
 textarea{{resize:vertical;min-height:64px}}
 button{{width:100%;margin-top:16px;padding:12px;border:0;border-radius:10px;background:{color};color:#fff;font-size:16px;font-weight:700;cursor:pointer}}
 button:disabled{{opacity:.6;cursor:default}}
 .ok{{text-align:center;padding:26px 10px}}
 .ok .tick{{font-size:42px}}
 .err{{color:#b91c1c;font-size:13px;margin-top:8px;min-height:16px}}
 .pw{{text-align:center;color:#9ca3af;font-size:11px;margin-top:14px}}
 .pw a{{color:#9ca3af}}
 /* chat mode */
 #lgaiChat{{display:none;flex-direction:column;height:100vh}}
 .chead{{padding:13px 16px;background:{color};color:#fff;font-weight:700;font-size:15px}}
 .chead small{{display:block;font-weight:400;font-size:11px;opacity:.85}}
 .cmsgs{{flex:1;overflow-y:auto;padding:12px;background:#f6f7fb}}
 .cm{{max-width:84%;margin:6px 0;padding:9px 12px;border-radius:14px;font-size:14px;line-height:1.4;white-space:pre-wrap;word-wrap:break-word}}
 .cm.bot{{background:#fff;border:1px solid #e5e7eb;border-bottom-left-radius:4px}}
 .cm.me{{background:{color};color:#fff;margin-left:auto;border-bottom-right-radius:4px}}
 .cm.typing{{color:#9ca3af;font-style:italic}}
 .cbar{{display:flex;gap:8px;padding:10px;border-top:1px solid #e5e7eb;background:#fff}}
 .cbar input{{flex:1;margin:0}}
 .cbar button{{width:auto;margin:0;padding:11px 16px;border-radius:10px}}
</style></head><body>
<div class="wrap" id="lgaiRoot">
  <h2>{biz}</h2>
  <div class="sub">Apni detail chhodiye — hum aapko jald call karenge. 📞</div>
  <form id="lgaiForm" autocomplete="on">
    {fields_html}
    <input type="text" id="lgHP" name="website" tabindex="-1" autocomplete="off"
           style="position:absolute;left:-9999px;width:1px;height:1px" aria-hidden="true" />
    <div class="err" id="lgErr"></div>
    <button type="submit" id="lgBtn">Callback chahiye</button>
  </form>
  <div class="pw">Powered by <a href="{site_base()}" target="_blank" rel="noopener">LeadsGenAI</a></div>
</div>
<div id="lgaiChat">
  <div class="chead">{biz}<small>AI assistant — turant jawab 24/7</small></div>
  <div class="cmsgs" id="lgC"></div>
  <form class="cbar" id="lgCF">
    <input id="lgCI" maxlength="500" placeholder="Apna sawaal likhiye…" autocomplete="off" />
    <button type="submit">➤</button>
  </form>
</div>
<script>
(function(){{
  var SLUG="{slug}", BIZ="{biz}";
  var MODE=(/[?&]mode=chat/.test(location.search||""))?"chat":"form";

  /* ---------- FORM MODE (default — pehle jaisa) ---------- */
  var f=document.getElementById("lgaiForm"),b=document.getElementById("lgBtn"),e=document.getElementById("lgErr");
  f.addEventListener("submit",function(ev){{
    ev.preventDefault(); e.textContent="";
    var els=f.querySelectorAll("[data-lgf]");
    var name="",phone="",message="",extras=[];
    for(var i=0;i<els.length;i++){{
      var el=els[i],n=el.getAttribute("data-lgf"),lb=el.getAttribute("data-lgl")||n,v=(el.value||"").trim();
      if(el.getAttribute("data-lgr")==="1"&&!v){{ e.textContent=lb.replace("*","").trim()+" bharna zaroori hai."; return; }}
      if(n==="name")name=v; else if(n==="phone")phone=v; else if(n==="message")message=v; else if(v)extras.push(lb.replace("*","").trim()+": "+v);
    }}
    var hp=document.getElementById("lgHP").value.trim();
    if(!name||phone.replace(/\\D/g,"").length<10){{ e.textContent="Naam aur sahi 10-digit phone daaliye."; return; }}
    var msg=message; if(extras.length){{ msg=(msg?msg+"\\n":"")+extras.join("\\n"); }}
    b.disabled=true; b.textContent="Bhej rahe hain…";
    fetch("/api/public/inquiry",{{method:"POST",headers:{{"Content-Type":"application/json"}},
      body:JSON.stringify({{name:name,phone:phone,message:msg,source_slug:SLUG,website:hp}})}})
    .then(function(r){{ return r.json().catch(function(){{return{{}};}}).then(function(j){{ return {{ok:r.ok,j:j}}; }}); }})
    .then(function(o){{
      if(o.ok){{ document.getElementById("lgaiRoot").innerHTML='<div class="ok"><div class="tick">✅</div><h2>Dhanyawad!</h2><div class="sub">Hum jald aapko call karenge.</div></div>'; }}
      else {{ e.textContent=(o.j&&o.j.detail)?o.j.detail:"Kuch galat hua — dobara try karein."; b.disabled=false; b.textContent="Callback chahiye"; }}
    }})
    .catch(function(){{ e.textContent="Network issue — dobara try karein."; b.disabled=false; b.textContent="Callback chahiye"; }});
  }});

  /* ---------- CHAT MODE (?mode=chat — AI assistant) ---------- */
  if(MODE==="chat"){{
    document.getElementById("lgaiRoot").style.display="none";
    var chat=document.getElementById("lgaiChat"); chat.style.display="flex";
    var box=document.getElementById("lgC"),cf=document.getElementById("lgCF"),ci=document.getElementById("lgCI");
    var SESS="";
    try{{ SESS=sessionStorage.getItem("lgaiSess")||""; if(!SESS){{ SESS=Math.random().toString(36).slice(2)+Date.now().toString(36); sessionStorage.setItem("lgaiSess",SESS); }} }}catch(_e){{ SESS="s"+Date.now(); }}
    function add(t,who){{ var d=document.createElement("div"); d.className="cm "+who; d.textContent=t; box.appendChild(d); box.scrollTop=box.scrollHeight; return d; }}
    add("Namaste! 🙏 "+BIZ+" me aapka swagat hai. Apna sawaal poochhiye — ya apna 10-digit number chhod dijiye, hum turant call karenge.","bot");
    var busy=false;
    cf.addEventListener("submit",function(ev){{
      ev.preventDefault();
      var t=(ci.value||"").trim(); if(!t||busy)return;
      ci.value=""; add(t,"me"); busy=true;
      var tp=add("likh rahe hain…","bot typing");
      fetch("/api/public/widget-chat",{{method:"POST",headers:{{"Content-Type":"application/json"}},
        body:JSON.stringify({{slug:SLUG,message:t,session_id:SESS}})}})
      .then(function(r){{ return r.json().catch(function(){{return{{}};}}); }})
      .then(function(j){{ tp.remove(); add((j&&j.reply)?j.reply:"Hmm, abhi jawab nahi de paya — apna number chhod dijiye, hum call karenge. 🙏","bot"); busy=false; }})
      .catch(function(){{ tp.remove(); add("Network issue — dobara try karein.","bot"); busy=false; }});
    }});
  }}
}})();
</script>
</body></html>"""


def widget_js(slug: str) -> str:
    """Floating-button + modal-iframe injector. Client apni site pe ek <script> se lagaye.
    Script src me ?mode=chat ho to AI-chat iframe khulta hai (default = form, zero change)."""
    slug = (slug or "").strip()
    base = site_base()
    embed_url = f"{base}/b/{slug}/embed"
    return f"""/* LeadsGenAI lead-capture widget */
(function(){{
  if(window.__lgaiWidget) return; window.__lgaiWidget=1;
  var MODE="form";
  try{{ var cs=document.currentScript; if(cs&&/[?&]mode=chat/.test(cs.src||"")) MODE="chat"; }}catch(e){{}}
  var EMBED="{embed_url}"+(MODE==="chat"?"?mode=chat":"");
  var css="#lgai-btn{{position:fixed;right:18px;bottom:18px;z-index:2147483000;background:#2563eb;color:#fff;border:0;border-radius:999px;padding:13px 18px;font:600 15px/1 -apple-system,Segoe UI,Roboto,Arial;box-shadow:0 6px 22px rgba(0,0,0,.25);cursor:pointer}}"
   +"#lgai-ov{{position:fixed;inset:0;z-index:2147483001;background:rgba(0,0,0,.5);display:none;align-items:center;justify-content:center}}"
   +"#lgai-ov.on{{display:flex}}"
   +"#lgai-box{{position:relative;width:380px;max-width:94vw;height:560px;max-height:90vh;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.4)}}"
   +"#lgai-x{{position:absolute;top:8px;right:10px;z-index:2;background:rgba(0,0,0,.06);border:0;border-radius:999px;width:30px;height:30px;font-size:18px;cursor:pointer;color:#333}}"
   +"#lgai-if{{border:0;width:100%;height:100%}}";
  var s=document.createElement("style"); s.textContent=css; document.head.appendChild(s);
  var btn=document.createElement("button"); btn.id="lgai-btn"; btn.type="button";
  btn.textContent=(MODE==="chat")?"💬 Chat karein":"💬 Enquiry";
  var ov=document.createElement("div"); ov.id="lgai-ov";
  ov.innerHTML='<div id="lgai-box"><button id="lgai-x" type="button" aria-label="Close">×</button><iframe id="lgai-if" loading="lazy"></iframe></div>';
  function open(){{ var f=ov.querySelector("#lgai-if"); if(!f.src) f.src=EMBED; ov.classList.add("on"); }}
  function close(){{ ov.classList.remove("on"); }}
  document.addEventListener("DOMContentLoaded",function(){{ document.body.appendChild(btn); document.body.appendChild(ov); }});
  if(document.body){{ document.body.appendChild(btn); document.body.appendChild(ov); }}
  btn.addEventListener("click",open);
  ov.addEventListener("click",function(ev){{ if(ev.target===ov||ev.target.id==="lgai-x") close(); }});
  document.addEventListener("keydown",function(ev){{ if(ev.key==="Escape") close(); }});
}})();"""


def snippet(slug: str, mode: str = "form") -> str:
    """Client ko dene ke liye copy-paste one-liner. mode='chat' = AI chat widget."""
    slug = (slug or "").strip()
    q = "?mode=chat" if (mode or "").strip().lower() == "chat" else ""
    return f'<!-- LeadsGenAI Widget --><script src="{site_base()}/b/{slug}/widget.js{q}" async></script>'


__all__ = [
    "embed_page_html",
    "widget_js",
    "snippet",
    "site_base",
    "default_fields",
    "get_form_config",
    "save_form_config",
]
