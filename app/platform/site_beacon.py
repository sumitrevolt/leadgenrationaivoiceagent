"""First-party site analytics beacon (Plausible-lite, free-stack) — client website
pe ~1KB JS: pageview (path/ref/utm_source) + WhatsApp/tel/[data-lg-track] clicks
navigator.sendBeacon se HAMARE collect endpoint pe (text/plain = no CORS preflight).

Privacy-first (DPDP): NO cookies, NO fingerprinting — IP last-octet-masked
(proposal_tracking._coarse_ip jaisa) + short UA hash, sirf coarse day-level
visitor approx. Store data/beacon_events.jsonl (auto-trim 20k lines).

  beacon_js(slug)            -> tiny JS snippet (serve as application/javascript)
  record_event(data, ip, ua) -> validate + append (never raises)
  stats(slug, days)          -> visitors/top paths/top sources/wa-tel clicks + Hinglish line

Pure-logic (NO LLM, no network). Never raises.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import Counter
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_EVENTS_FILE = os.path.join("data", "beacon_events.jsonl")
_MAX_LINES = 20000
_TRIM_EVERY = 500  # har N writes pe line-count check (hot-path cheap)
_writes_since_check = 0

_TYPES = {"pageview", "click"}


def _slug_key(slug: str) -> str:
    return "".join(c for c in (slug or "").strip().lower() if c.isalnum() or c == "-")[:64]


def _site_base() -> str:
    try:
        from app.marketing.embed_widget import site_base

        return site_base()
    except Exception:
        return "https://leadsgenai.in"


def _coarse_ip(ip: str) -> str:
    """Privacy-coarse IP — last octet mask (proposal_tracking pattern)."""
    try:
        parts = str(ip or "").strip().split(".")
        if len(parts) == 4:
            return ".".join(parts[:3]) + ".x"
        return str(ip or "")[:24]  # ipv6/other — truncate
    except Exception:
        return ""


def _ua_key(ua: str) -> str:
    """Short non-reversible UA hash (no fingerprint — sirf same-day dedupe)."""
    try:
        return hashlib.sha256((ua or "").encode("utf-8", "ignore")).hexdigest()[:10]
    except Exception:
        return ""


def _trim_if_needed() -> None:
    """File _MAX_LINES se badi ho to last _MAX_LINES rakh ke rewrite (best-effort)."""
    try:
        if not os.path.isfile(_EVENTS_FILE):
            return
        with open(_EVENTS_FILE, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) <= _MAX_LINES:
            return
        keep = lines[-_MAX_LINES:]
        tmp = _EVENTS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(keep)
        os.replace(tmp, _EVENTS_FILE)
        logger.info(f"[site_beacon] trimmed events file to {_MAX_LINES} lines")
    except Exception as e:
        logger.warning(f"[site_beacon] trim failed: {e}")


def record_event(data: dict[str, Any] | None, ip: str = "", ua: str = "") -> dict[str, Any]:
    """Beacon event store karo (coarse/anonymous). Galat payload = silently drop."""
    global _writes_since_check
    try:
        data = data if isinstance(data, dict) else {}
        slug = _slug_key(str(data.get("slug") or ""))
        etype = str(data.get("type") or "").strip().lower()
        if not slug or etype not in _TYPES:
            return {"ok": False}
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "slug": slug,
            "type": etype,
            "path": str(data.get("path") or "/")[:200],
            "ref": str(data.get("ref") or "")[:200],
            "source": str(data.get("source") or "")[:60],
            "kind": str(data.get("kind") or "")[:12],  # wa | tel | track ("" = pageview)
            "name": str(data.get("name") or "")[:60],
            "ip": _coarse_ip(ip),
            "ua": _ua_key(ua),
        }
        os.makedirs(os.path.dirname(_EVENTS_FILE) or ".", exist_ok=True)
        with open(_EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _writes_since_check += 1
        if _writes_since_check >= _TRIM_EVERY:
            _writes_since_check = 0
            _trim_if_needed()
        return {"ok": True}
    except Exception as e:
        logger.warning(f"[site_beacon] record failed: {e}")
        return {"ok": False}


def _ref_source(ref: str) -> str:
    """Referrer host se readable source (instagram.com → Instagram)."""
    try:
        host = ref.split("//", 1)[-1].split("/", 1)[0].lower()
        host = host.removeprefix("www.").removeprefix("l.").removeprefix("m.")
        if not host:
            return ""
        return host.split(".")[0].title()
    except Exception:
        return ""


def stats(slug: str, days: int = 7) -> dict[str, Any]:
    """Coarse analytics — visitors approx (ip+ua+day unique), top paths/sources,
    wa/tel clicks + Hinglish summary. Never raises."""
    key = _slug_key(slug)
    days = days if days in (7, 30) else (30 if days and int(days or 0) > 7 else 7)
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - days * 86400))
    visitors: set[tuple[str, str, str]] = set()
    paths: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    pageviews = 0
    wa_clicks = 0
    tel_clicks = 0
    track_clicks: Counter[str] = Counter()
    try:
        if key and os.path.isfile(_EVENTS_FILE):
            with open(_EVENTS_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(rec, dict) or rec.get("slug") != key:
                        continue
                    ts = str(rec.get("ts") or "")
                    if ts < cutoff:
                        continue
                    if rec.get("type") == "pageview":
                        pageviews += 1
                        visitors.add((str(rec.get("ip")), str(rec.get("ua")), ts[:10]))
                        paths[str(rec.get("path") or "/")] += 1
                        src = str(rec.get("source") or "").strip() or _ref_source(
                            str(rec.get("ref") or "")
                        )
                        if src:
                            sources[src[:40]] += 1
                    elif rec.get("type") == "click":
                        kind = str(rec.get("kind") or "")
                        if kind == "wa":
                            wa_clicks += 1
                        elif kind == "tel":
                            tel_clicks += 1
                        elif rec.get("name"):
                            track_clicks[str(rec.get("name"))[:60]] += 1
    except Exception as e:
        logger.warning(f"[site_beacon] stats failed: {e}")
    n_visitors = len(visitors)
    top_source = sources.most_common(1)[0][0] if sources else "direct"
    summary = (
        f"{n_visitors} visitors ({days} din), {pageviews} pageviews, "
        f"{wa_clicks} WhatsApp + {tel_clicks} call clicks — top source {top_source}."
    )
    return {
        "slug": key,
        "days": days,
        "visitors": n_visitors,
        "pageviews": pageviews,
        "top_paths": paths.most_common(10),
        "top_sources": sources.most_common(10),
        "wa_clicks": wa_clicks,
        "tel_clicks": tel_clicks,
        "tracked_clicks": track_clicks.most_common(10),
        "summary": summary,
    }


# --------------------------------------------------------------------------- #
# Beacon JS (~1KB) — sendBeacon text/plain = cross-origin OK bina preflight
# --------------------------------------------------------------------------- #
_JS_TEMPLATE = r"""/* LeadsGenAI beacon */
(function(){
 if(window.__lgaiBeacon)return;window.__lgaiBeacon=1;
 var S=__SLUG__,EP=__EP__;
 function send(d){
  d.slug=S;
  try{
   var s=JSON.stringify(d);
   if(navigator.sendBeacon){navigator.sendBeacon(EP,s);}
   else{var x=new XMLHttpRequest();x.open("POST",EP,true);x.setRequestHeader("Content-Type","text/plain");x.send(s);}
  }catch(e){}
 }
 var u="";
 try{u=(new URLSearchParams(location.search)).get("utm_source")||"";}catch(e){}
 send({type:"pageview",path:location.pathname,ref:document.referrer||"",source:u});
 document.addEventListener("click",function(ev){
  try{
   var a=ev.target&&ev.target.closest?ev.target.closest("a,[data-lg-track]"):null;
   if(!a)return;
   var n=(a.getAttribute&&a.getAttribute("data-lg-track"))||"";
   var h=(a.getAttribute&&a.getAttribute("href"))||"";
   var k="";
   if(/wa\.me|api\.whatsapp\.com/.test(h))k="wa";
   else if(h.indexOf("tel:")===0)k="tel";
   else if(n)k="track";
   if(!k)return;
   send({type:"click",kind:k,name:n,path:location.pathname});
  }catch(e){}
 },true);
})();"""


def beacon_js(slug: str) -> str:
    """Tiny analytics JS (slug baked-in). Invalid slug = harmless comment."""
    try:
        key = _slug_key(slug)
        if not key:
            return "/* beacon: slug missing */"
        return _JS_TEMPLATE.replace("__SLUG__", json.dumps(key)).replace(
            "__EP__", json.dumps(f"{_site_base()}/api/widgets/beacon")
        )
    except Exception:  # pragma: no cover
        return "/* beacon unavailable */"


def snippet(slug: str) -> str:
    """Client ko dene ka copy-paste one-liner."""
    key = _slug_key(slug)
    return f'<!-- LeadsGenAI Analytics --><script src="{_site_base()}/api/widgets/beacon.js?slug={key}" async></script>'


__all__ = ["beacon_js", "record_event", "stats", "snippet"]
