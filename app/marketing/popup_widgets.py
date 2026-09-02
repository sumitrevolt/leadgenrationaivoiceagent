"""Popup conversion pack (OptinMonster-style, free-stack) — ek script se client
website pe 3 cheezein: exit-intent/scroll/delay POPUP + ANNOUNCEMENT BAR
(countdown ke saath) + SPIN-TO-WIN wheel (loyalty.py ke REAL coupon codes).

CORS-free lead capture (prod lesson): popup/wheel ka CTA hamare PROVEN
`/b/{slug}/embed` iframe modal ko kholta hai (embed_widget.py wala contract —
form HAMARI origin se `POST /api/public/inquiry` + source_slug karta, lead auto
client se link). Cross-origin JSON fetch jaan-bujhke NAHI (prod CORS allowlist
tight hai — direct fetch fail hota).

  get_config(slug)              -> effective config (defaults merged, latest-wins)
  save_config(slug, cfg)        -> validate + append (data/popup_config.jsonl)
  create_wheel_coupons(...)     -> loyalty.create_campaign se real codes + config save
  render_js(slug)               -> vanilla JS IIFE (no deps), localStorage 1/day cap
  snippet(slug)                 -> copy-paste <script> one-liner

Pure-logic module (NO LLM, no network). Never raises.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CONFIG_FILE = os.path.join("data", "popup_config.jsonl")

_TRIGGERS = {"exit_intent", "scroll50", "delay"}
_MAX_SEGMENTS = 6
_MIN_SEGMENTS = 2  # 4-6 recommended; <2 = wheel render nahi hota


def _slug_key(slug: str) -> str:
    """Slug normalize — sirf [a-z0-9-] (regex-lock, JS/URL inject safe)."""
    return "".join(c for c in (slug or "").strip().lower() if c.isalnum() or c == "-")[:64]


def _site_base() -> str:
    try:
        from app.marketing.embed_widget import site_base

        return site_base()
    except Exception:
        return "https://leadsgenai.in"


def _load_client(slug: str) -> dict[str, Any]:
    """Client record by slug (tests monkeypatch karte hain). Never raises."""
    try:
        from app.marketing import clients_store

        return clients_store.get_by_slug(slug) or {}
    except Exception:
        return {}


def _clean_color(v: Any) -> str:
    s = str(v or "").strip()
    if s.startswith("#") and 4 <= len(s) <= 9 and all(c in "0123456789abcdefABCDEF" for c in s[1:]):
        return s
    return ""


def _brand_color(slug: str) -> str:
    """brand_kit primary > client record color > default blue."""
    try:
        client = _load_client(slug)
        cid = client.get("id")
        if cid:
            try:
                from app.marketing import brand_kit

                brand = brand_kit.get_brand(cid) or {}
                c = _clean_color((brand.get("colors") or {}).get("primary"))
                if c:
                    return c
            except Exception:
                pass
        for k in ("brand_color", "primary_color", "color", "theme_color"):
            c = _clean_color(client.get(k))
            if c:
                return c
    except Exception:
        pass
    return "#2563eb"


# --------------------------------------------------------------------------- #
# Config (data/popup_config.jsonl, latest-wins per slug)
# --------------------------------------------------------------------------- #
def _defaults() -> dict[str, Any]:
    return {
        "popup": {
            "enabled": False,
            "trigger": "delay",  # exit_intent | scroll50 | delay
            "delay_s": 8,
            "title": "Ek minute! \U0001f381",
            "body": "Apna number chhodiye — turant callback milega.",
            "cta_text": "Callback chahiye",
            "coupon_code": "",
        },
        "bar": {"enabled": False, "text": "", "countdown_until": "", "link": ""},
        "wheel": {"enabled": False, "segments": []},
    }


def _safe_url(v: Any) -> str:
    s = str(v or "").strip()[:300]
    if s.startswith(("http://", "https://", "/")):
        return s
    return ""


def _clean_segment(s: Any) -> dict[str, str] | None:
    if not isinstance(s, dict):
        return None
    label = str(s.get("label") or "").strip()[:40]
    if not label:
        return None
    code = str(s.get("coupon_code") or "").strip().upper()[:24]
    return {"label": label, "coupon_code": code}


def _clean_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Incoming config validate/normalize — unknown keys drop, galat values default."""
    cfg = cfg if isinstance(cfg, dict) else {}
    out = _defaults()

    p_in = cfg.get("popup") if isinstance(cfg.get("popup"), dict) else {}
    p = out["popup"]
    p["enabled"] = bool(p_in.get("enabled"))
    trig = str(p_in.get("trigger") or "delay").strip().lower()
    if trig == "delay_s":  # spec alias
        trig = "delay"
    p["trigger"] = trig if trig in _TRIGGERS else "delay"
    try:
        p["delay_s"] = max(1, min(120, int(p_in.get("delay_s") or 8)))
    except Exception:
        p["delay_s"] = 8
    for k, maxlen in (("title", 80), ("body", 200), ("cta_text", 40)):
        v = str(p_in.get(k) or "").strip()[:maxlen]
        if v:
            p[k] = v
    p["coupon_code"] = str(p_in.get("coupon_code") or "").strip().upper()[:24]

    b_in = cfg.get("bar") if isinstance(cfg.get("bar"), dict) else {}
    b = out["bar"]
    b["enabled"] = bool(b_in.get("enabled"))
    b["text"] = str(b_in.get("text") or "").strip()[:120]
    cd = str(b_in.get("countdown_until") or "").strip()[:25]
    # rough ISO sanity: "2026-06-15..." (warna JS Date.parse NaN — defensive yahin)
    b["countdown_until"] = cd if (len(cd) >= 10 and cd[:4].isdigit() and cd[4] == "-") else ""
    b["link"] = _safe_url(b_in.get("link"))

    w_in = cfg.get("wheel") if isinstance(cfg.get("wheel"), dict) else {}
    w = out["wheel"]
    segs = [c for c in (_clean_segment(x) for x in (w_in.get("segments") or [])) if c]
    w["segments"] = segs[:_MAX_SEGMENTS]
    w["enabled"] = bool(w_in.get("enabled")) and len(w["segments"]) >= _MIN_SEGMENTS
    return out


def save_config(slug: str, cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Per-slug popup-pack config save (append-only jsonl, latest-wins)."""
    try:
        key = _slug_key(slug)
        if not key:
            return {"ok": False, "error": "slug required"}
        clean = _clean_config(cfg)
        rec = {"slug": key, **clean}
        os.makedirs(os.path.dirname(_CONFIG_FILE) or ".", exist_ok=True)
        with open(_CONFIG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"ok": True, "slug": key, "config": clean}
    except Exception as e:
        logger.warning(f"[popup_widgets] save failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def get_config(slug: str) -> dict[str, Any]:
    """Effective config (latest record wins; kuch saved nahi = sab disabled defaults)."""
    key = _slug_key(slug)
    found: dict[str, Any] | None = None
    try:
        if key and os.path.isfile(_CONFIG_FILE):
            with open(_CONFIG_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(rec, dict) and rec.get("slug") == key:
                        found = rec
    except Exception as e:
        logger.warning(f"[popup_widgets] read failed: {e}")
    return _clean_config(found or {})


def create_wheel_coupons(client_id: str, slug: str, offers: list[dict] | None) -> dict[str, Any]:
    """Spin-wheel segments ke liye loyalty.py se REAL coupon campaigns banao
    aur config me wheel enable kar do. offers = [{title, kind?, value?}] (2-6)."""
    try:
        client_id = (client_id or "").strip()
        key = _slug_key(slug)
        if not client_id or not key:
            return {"ok": False, "error": "client_id + slug required"}
        offers = [
            o for o in (offers or []) if isinstance(o, dict) and str(o.get("title") or "").strip()
        ]
        offers = offers[:_MAX_SEGMENTS]
        if len(offers) < _MIN_SEGMENTS:
            return {"ok": False, "error": f"kam se kam {_MIN_SEGMENTS} offers chahiye"}
        from app.marketing import loyalty

        segments: list[dict[str, str]] = []
        for o in offers:
            res = loyalty.create_campaign(
                client_id,
                str(o.get("title")).strip()[:40],
                kind=str(o.get("kind") or "percent"),
                value=int(o.get("value") or 10),
            )
            camp = (res or {}).get("campaign") or {}
            segments.append(
                {
                    "label": str(o.get("title")).strip()[:40],
                    "coupon_code": str(camp.get("id") or ""),
                }
            )
        cfg = get_config(key)
        cfg["wheel"] = {"enabled": True, "segments": segments}
        saved = save_config(key, cfg)
        return {"ok": bool(saved.get("ok")), "segments": segments, "config": saved.get("config")}
    except Exception as e:
        logger.warning(f"[popup_widgets] create_wheel_coupons failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


# --------------------------------------------------------------------------- #
# JS render (vanilla IIFE, no deps) — strings json.dumps se embed (inject-safe),
# DOM text hamesha textContent se (innerHTML user-text kabhi nahi).
# --------------------------------------------------------------------------- #
_JS_TEMPLATE = r"""/* LeadsGenAI popup pack */
(function(){
 if(window.__lgaiPopupPack)return;window.__lgaiPopupPack=1;
 var CFG=__CFG__,SLUG=__SLUG__,EMBED=__EMBED__,COLOR=__COLOR__;
 var FONT="-apple-system,Segoe UI,Roboto,Arial,sans-serif";
 function today(){return new Date().toISOString().slice(0,10);}
 function seen(k){try{return localStorage.getItem(k)===today();}catch(e){return false;}}
 function mark(k){try{localStorage.setItem(k,today());}catch(e){}}
 function el(t,c){var d=document.createElement(t);if(c)d.style.cssText=c;return d;}
 var ov=null;
 function openForm(){
  if(!ov){
   ov=el("div","position:fixed;inset:0;z-index:2147483450;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center");
   var box=el("div","position:relative;width:380px;max-width:94vw;height:560px;max-height:90vh;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.4)");
   var x=el("button","position:absolute;top:8px;right:10px;z-index:2;background:rgba(0,0,0,.06);border:0;border-radius:999px;width:30px;height:30px;font-size:18px;cursor:pointer;color:#333");
   x.type="button";x.setAttribute("aria-label","Close");x.textContent="×";
   var f=document.createElement("iframe");f.style.cssText="border:0;width:100%;height:100%";f.src=EMBED;
   box.appendChild(x);box.appendChild(f);ov.appendChild(box);document.body.appendChild(ov);
   x.addEventListener("click",function(){ov.style.display="none";});
   ov.addEventListener("click",function(e){if(e.target===ov)ov.style.display="none";});
  }
  ov.style.display="flex";
 }
 /* ---- announcement bar (+ countdown) ---- */
 (function(){
  var B=CFG.bar||{};if(!B.enabled||!B.text)return;
  var bar=el("div","position:fixed;top:0;left:0;right:0;z-index:2147483300;background:"+COLOR+";color:#fff;font:600 13px/1.5 "+FONT+";padding:8px 36px 8px 12px;text-align:center"+(B.link?";cursor:pointer":""));
  var t=document.createElement("span");t.textContent=B.text;bar.appendChild(t);
  var cd=document.createElement("strong");cd.style.marginLeft="8px";bar.appendChild(cd);
  var x=el("span","position:absolute;right:10px;top:6px;font-size:15px;cursor:pointer;opacity:.85");
  x.textContent="✕";bar.appendChild(x);
  x.addEventListener("click",function(e){e.stopPropagation();bar.remove();});
  if(B.link){bar.addEventListener("click",function(){location.href=B.link;});}
  document.body.appendChild(bar);
  if(B.countdown_until){
   var end=Date.parse(B.countdown_until);
   if(!isNaN(end)){
    var iv=setInterval(function(){
     var s=Math.floor((end-Date.now())/1e3);
     if(s<=0){cd.textContent="";clearInterval(iv);return;}
     var d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);
     cd.textContent="⏳ "+(d>0?d+"d ":"")+h+"h "+m+"m "+(s%60)+"s";
    },1000);
   }
  }
 })();
 /* ---- popup (exit-intent / scroll50 / delay) — 1/day localStorage cap ---- */
 (function(){
  var P=CFG.popup||{};if(!P.enabled)return;
  var KEY="lgpw_"+SLUG,shown=false;
  if(seen(KEY))return;
  function show(){
   if(shown||seen(KEY))return;shown=true;mark(KEY);
   var o=el("div","position:fixed;inset:0;z-index:2147483400;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center");
   var c=el("div","position:relative;width:340px;max-width:92vw;background:#fff;border-radius:16px;padding:24px 20px;text-align:center;font-family:"+FONT+";box-shadow:0 20px 60px rgba(0,0,0,.35)");
   var x=el("button","position:absolute;top:6px;right:10px;background:none;border:0;font-size:20px;cursor:pointer;color:#888");
   x.type="button";x.setAttribute("aria-label","Close");x.textContent="×";c.appendChild(x);
   var h=el("h3","margin:4px 0 8px;font-size:19px;color:#111");h.textContent=P.title||"";c.appendChild(h);
   var p=el("p","margin:0 0 14px;font-size:14px;color:#555;line-height:1.5");p.textContent=P.body||"";c.appendChild(p);
   if(P.coupon_code){
    var cp=el("div","border:2px dashed "+COLOR+";border-radius:10px;padding:10px;font:700 17px/1.2 "+FONT+";letter-spacing:1px;color:"+COLOR+";margin-bottom:14px;cursor:pointer");
    cp.textContent=P.coupon_code;cp.title="Tap to copy";
    cp.addEventListener("click",function(){try{navigator.clipboard.writeText(P.coupon_code);cp.textContent="✅ Copied!";setTimeout(function(){cp.textContent=P.coupon_code;},1200);}catch(e){}});
    c.appendChild(cp);
   }
   var b=el("button","width:100%;padding:12px;border:0;border-radius:10px;background:"+COLOR+";color:#fff;font:700 15px/1 "+FONT+";cursor:pointer");
   b.type="button";b.textContent=P.cta_text||"Callback chahiye";c.appendChild(b);
   o.appendChild(c);document.body.appendChild(o);
   function close(){try{o.remove();}catch(e){}}
   x.addEventListener("click",close);
   o.addEventListener("click",function(e){if(e.target===o)close();});
   b.addEventListener("click",function(){close();openForm();});
  }
  if(P.trigger==="exit_intent"){
   document.addEventListener("mouseout",function(e){if(!e.relatedTarget&&e.clientY<10)show();});
  }else if(P.trigger==="scroll50"){
   window.addEventListener("scroll",function(){
    var h=document.documentElement,d=(h.scrollTop+window.innerHeight)/Math.max(1,h.scrollHeight);
    if(d>=0.5)show();
   },{passive:true});
  }else{
   setTimeout(show,Math.max(1,P.delay_s||8)*1000);
  }
 })();
 /* ---- spin-to-win wheel (CSS conic, coupon reveal) — 1/day cap ---- */
 (function(){
  var W=CFG.wheel||{},SEG=W.segments||[];
  if(!W.enabled||SEG.length<2)return;
  var KEY="lgww_"+SLUG;
  if(seen(KEY))return;
  var COLS=["#f59e0b","#10b981","#3b82f6","#ef4444","#8b5cf6","#14b8a6"];
  var fab=el("button","position:fixed;left:18px;bottom:18px;z-index:2147483200;background:"+COLOR+";color:#fff;border:0;border-radius:999px;padding:12px 16px;font:600 14px/1 "+FONT+";cursor:pointer;box-shadow:0 6px 22px rgba(0,0,0,.25)");
  fab.type="button";fab.textContent="🎡 Lucky Spin";
  if(document.body){document.body.appendChild(fab);}else{document.addEventListener("DOMContentLoaded",function(){document.body.appendChild(fab);});}
  fab.addEventListener("click",function(){
   var n=SEG.length,arc=360/n,stops=[],i;
   for(i=0;i<n;i++){stops.push(COLS[i%COLS.length]+" "+(i*arc)+"deg "+((i+1)*arc)+"deg");}
   var o=el("div","position:fixed;inset:0;z-index:2147483400;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center");
   var c=el("div","position:relative;width:320px;max-width:92vw;background:#fff;border-radius:16px;padding:22px 18px;text-align:center;font-family:"+FONT);
   var x=el("button","position:absolute;top:6px;right:10px;background:none;border:0;font-size:20px;cursor:pointer;color:#888");
   x.type="button";x.textContent="×";c.appendChild(x);
   var h=el("h3","margin:0 0 10px;font-size:18px;color:#111");h.textContent="Spin karo, offer jeeto! 🎁";c.appendChild(h);
   var ptr=el("div","width:0;height:0;margin:0 auto;border-left:10px solid transparent;border-right:10px solid transparent;border-top:14px solid #111");c.appendChild(ptr);
   var wh=el("div","width:230px;height:230px;margin:2px auto 10px;border-radius:50%;border:6px solid #eee;background:conic-gradient("+stops.join(",")+");transition:transform 3.2s cubic-bezier(.15,.65,.1,1)");c.appendChild(wh);
   var lg=el("div","font-size:12px;color:#555;text-align:left;margin:0 auto 10px;max-width:230px");
   for(i=0;i<n;i++){
    var row=el("div","margin:2px 0");
    var dot=el("span","display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;background:"+COLS[i%COLS.length]);
    var lb=document.createElement("span");lb.textContent=SEG[i].label||"";
    row.appendChild(dot);row.appendChild(lb);lg.appendChild(row);
   }
   c.appendChild(lg);
   var res=el("div","min-height:44px;font:700 15px/1.4 "+FONT+";color:#111;margin-bottom:8px");c.appendChild(res);
   var b=el("button","width:100%;padding:12px;border:0;border-radius:10px;background:"+COLOR+";color:#fff;font:700 15px/1 "+FONT+";cursor:pointer");
   b.type="button";b.textContent="SPIN 🎰";c.appendChild(b);
   o.appendChild(c);document.body.appendChild(o);
   function close(){try{o.remove();}catch(e){}}
   x.addEventListener("click",close);
   o.addEventListener("click",function(e){if(e.target===o)close();});
   var spun=false;
   b.addEventListener("click",function(){
    if(spun)return;spun=true;mark(KEY);b.disabled=true;
    var idx=Math.floor(Math.random()*n);
    wh.style.transform="rotate("+(5*360+(360-(idx*arc+arc/2)))+"deg)";
    setTimeout(function(){
     var s=SEG[idx]||{};
     res.textContent="🎉 "+(s.label||"Offer")+(s.coupon_code?" — code: "+s.coupon_code:"");
     b.disabled=false;b.textContent="📞 Offer claim karein";
     b.addEventListener("click",function(){close();openForm();});
     try{fab.style.display="none";}catch(e){}
    },3400);
   });
  });
 })();
})();"""


def render_js(slug: str) -> str:
    """Popup-pack JS (vanilla, no deps). Config inactive ho to bhi VALID JS
    lautata (sab sections khud skip ho jaate). Never raises."""
    try:
        key = _slug_key(slug)
        cfg = get_config(key)
        embed = f"{_site_base()}/b/{key}/embed"
        # "</" → "<\/" — json.dumps "/" escape nahi karta; </script> breakout lock
        cfg_json = json.dumps(cfg, ensure_ascii=True).replace("</", "<\\/")
        return (
            _JS_TEMPLATE.replace("__CFG__", cfg_json)
            .replace("__SLUG__", json.dumps(key))
            .replace("__EMBED__", json.dumps(embed))
            .replace("__COLOR__", json.dumps(_brand_color(key)))
        )
    except Exception as e:  # pragma: no cover - sab pieces defensive hain
        logger.warning(f"[popup_widgets] render failed: {e}")
        return "/* popup pack unavailable */"


def snippet(slug: str) -> str:
    """Client ko dene ka copy-paste one-liner."""
    key = _slug_key(slug)
    return f'<!-- LeadsGenAI Popup Pack --><script src="{_site_base()}/api/widgets/popup.js?slug={key}" async></script>'


__all__ = [
    "get_config",
    "save_config",
    "create_wheel_coupons",
    "render_js",
    "snippet",
]
