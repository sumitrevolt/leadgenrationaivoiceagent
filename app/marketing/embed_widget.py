"""Embeddable lead-capture widget — client apni KISI BHI website pe ek line paste kare,
floating "Enquiry" button + form aa jata hai. Submissions seedha leads dashboard me
(reuses POST /api/public/inquiry + source_slug → client auto-resolve).

CORS-free design: form ek IFRAME me hamare origin (leadsgenai.in) se serve hota hai,
isliye cross-origin POST ki zaroorat nahi (Calendly/Tally jaisa). Fulfils Growth-tier
"Website lead-capture form setup". Pure-string module, never raises.

  embed_page_html(client) -> full HTML form page (served at /b/{slug}/embed, iframe-able)
  widget_js(slug)         -> JS injector (served at /b/{slug}/widget.js)
  snippet(slug)           -> copy-paste <script> one-liner for the client
"""

from __future__ import annotations

import html
import os


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


def embed_page_html(client: dict) -> str:
    """Standalone branded lead-form page (iframe content). POST → /api/public/inquiry."""
    client = client or {}
    biz = html.escape(str(client.get("business_name") or "Hamse judiye"))
    slug = html.escape(str(client.get("slug") or ""))
    color = _brand_color(client)
    return f"""<!doctype html><html lang="hi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{biz} — Enquiry</title>
<style>
 *{{box-sizing:border-box}}
 body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#fff;color:#111}}
 .wrap{{padding:18px 16px}}
 h2{{margin:0 0 2px;font-size:18px}}
 .sub{{color:#666;font-size:13px;margin-bottom:14px}}
 label{{display:block;font-size:13px;font-weight:600;margin:10px 0 4px}}
 input,textarea{{width:100%;padding:11px 12px;border:1px solid #d4d4d8;border-radius:10px;font-size:15px;font-family:inherit}}
 input:focus,textarea:focus{{outline:none;border-color:{color};box-shadow:0 0 0 3px {color}22}}
 textarea{{resize:vertical;min-height:64px}}
 button{{width:100%;margin-top:16px;padding:12px;border:0;border-radius:10px;background:{color};color:#fff;font-size:16px;font-weight:700;cursor:pointer}}
 button:disabled{{opacity:.6;cursor:default}}
 .ok{{text-align:center;padding:26px 10px}}
 .ok .tick{{font-size:42px}}
 .err{{color:#b91c1c;font-size:13px;margin-top:8px;min-height:16px}}
 .pw{{text-align:center;color:#9ca3af;font-size:11px;margin-top:14px}}
 .pw a{{color:#9ca3af}}
</style></head><body>
<div class="wrap" id="lgaiRoot">
  <h2>{biz}</h2>
  <div class="sub">Apni detail chhodiye — hum aapko jald call karenge. 📞</div>
  <form id="lgaiForm" autocomplete="on">
    <label for="lgN">Naam *</label>
    <input id="lgN" name="name" type="text" maxlength="120" required placeholder="Aapka naam" />
    <label for="lgP">Phone *</label>
    <input id="lgP" name="phone" type="tel" maxlength="20" required inputmode="numeric" placeholder="10-digit mobile" />
    <label for="lgM">Message (optional)</label>
    <textarea id="lgM" name="message" maxlength="1000" placeholder="Aapko kya chahiye?"></textarea>
    <input type="text" id="lgHP" name="website" tabindex="-1" autocomplete="off"
           style="position:absolute;left:-9999px;width:1px;height:1px" aria-hidden="true" />
    <div class="err" id="lgErr"></div>
    <button type="submit" id="lgBtn">Callback chahiye</button>
  </form>
  <div class="pw">Powered by <a href="{site_base()}" target="_blank" rel="noopener">LeadsGenAI</a></div>
</div>
<script>
(function(){{
  var f=document.getElementById("lgaiForm"),b=document.getElementById("lgBtn"),e=document.getElementById("lgErr");
  var SLUG="{slug}";
  f.addEventListener("submit",function(ev){{
    ev.preventDefault(); e.textContent="";
    var name=document.getElementById("lgN").value.trim();
    var phone=document.getElementById("lgP").value.trim();
    var msg=document.getElementById("lgM").value.trim();
    var hp=document.getElementById("lgHP").value.trim();
    if(!name||phone.replace(/\\D/g,"").length<10){{ e.textContent="Naam aur sahi 10-digit phone daaliye."; return; }}
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
}})();
</script>
</body></html>"""


def widget_js(slug: str) -> str:
    """Floating-button + modal-iframe injector. Client apni site pe ek <script> se lagaye."""
    slug = (slug or "").strip()
    base = site_base()
    embed_url = f"{base}/b/{slug}/embed"
    return f"""/* LeadsGenAI lead-capture widget */
(function(){{
  if(window.__lgaiWidget) return; window.__lgaiWidget=1;
  var EMBED="{embed_url}";
  var css="#lgai-btn{{position:fixed;right:18px;bottom:18px;z-index:2147483000;background:#2563eb;color:#fff;border:0;border-radius:999px;padding:13px 18px;font:600 15px/1 -apple-system,Segoe UI,Roboto,Arial;box-shadow:0 6px 22px rgba(0,0,0,.25);cursor:pointer}}"
   +"#lgai-ov{{position:fixed;inset:0;z-index:2147483001;background:rgba(0,0,0,.5);display:none;align-items:center;justify-content:center}}"
   +"#lgai-ov.on{{display:flex}}"
   +"#lgai-box{{position:relative;width:380px;max-width:94vw;height:560px;max-height:90vh;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.4)}}"
   +"#lgai-x{{position:absolute;top:8px;right:10px;z-index:2;background:rgba(0,0,0,.06);border:0;border-radius:999px;width:30px;height:30px;font-size:18px;cursor:pointer;color:#333}}"
   +"#lgai-if{{border:0;width:100%;height:100%}}";
  var s=document.createElement("style"); s.textContent=css; document.head.appendChild(s);
  var btn=document.createElement("button"); btn.id="lgai-btn"; btn.type="button"; btn.textContent="💬 Enquiry";
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


def snippet(slug: str) -> str:
    """Client ko dene ke liye copy-paste one-liner."""
    slug = (slug or "").strip()
    return f'<!-- LeadsGenAI Widget --><script src="{site_base()}/b/{slug}/widget.js" async></script>'


__all__ = ["embed_page_html", "widget_js", "snippet", "site_base"]
