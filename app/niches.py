"""
Top 25 Niches Configuration — research-finalized (June 2026).

Selection criteria (web research, see docs/Niche_Pricing_Research.md + Excel):
  (a) high ticket size, (b) phone-call-heavy buying journey in India,
  (c) proven willingness to pay for qualified leads (CPL/CPQL benchmarks),
  (d) clear B2B client + B2C/B2B end-customer extension for tier-2 campaigns.

Two-tier model:
  - Tier 1 (platform → B2B): hum in niches ke BUSINESSES ko client banate hain.
  - Tier 2 (client → end customers): client ka voice agent uske END CUSTOMERS
    ko call karta hai — `target_type` batata hai wo audience B2C hai ya B2B.

Voice-product pricing (ADR-009, 2026-06-11): PER-LEAD pricing REMOVED.
  lead_band = "A" | "B" | "C"   # Band A mass-local / B high-ticket / C premium-HNI
  Actual prices (per-10-qualified-leads tiers + top-up packs) live in
  app/marketing/voice_packages.py — yahan sirf band mapping.
Product split: category "marketing" -> sirf Product 1 (AI Automated Marketing),
  "leadgen" -> sirf Product 2 (AI Voice Calling Agent), "both" -> dono.
  Helpers: niches_for_product() / niche_products() / lead_band().
Backward-compatible fields retained: name, keywords, avg_deal_value,
pitch_hook, qualification_questions.
"""

# ========================================================================== #
# CUSTOM NICHES — runtime-added niches (persisted to data/custom_niches.json)
# Builtin 42 upar static hain; client koi NAYA niche maange to add_custom_niche()
# se turant add hota hai aur flows/KB/agents/web-call sab me waise hi kaam
# karta hai (sab consumers NICHES dict hi padhte hain — hum usme merge karte).
# ========================================================================== #
import json as _json
import re as _re
from pathlib import Path as _Path

from app.niches_data import NICHES  # noqa: F401  (catalog data extracted 2026-06-20)

_BUILTIN_KEYS = frozenset(NICHES.keys())
_CUSTOM_FILE = _Path(__file__).resolve().parent.parent / "data" / "custom_niches.json"
_custom_mtime: float = -1.0


def _slugify(name: str) -> str:
    s = _re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return s[:50] or "custom_niche"


def _load_custom_niches(force: bool = False) -> None:
    """File se custom niches NICHES me merge karo (mtime-cached, multi-worker safe)."""
    global _custom_mtime
    try:
        if not _CUSTOM_FILE.exists():
            if _custom_mtime != -1.0:  # file delete ho gayi — purge customs
                for k in [k for k in list(NICHES) if k not in _BUILTIN_KEYS]:
                    NICHES.pop(k, None)
                _custom_mtime = -1.0
            return
        m = _CUSTOM_FILE.stat().st_mtime
        if not force and m == _custom_mtime:
            return
        data = _json.loads(_CUSTOM_FILE.read_text(encoding="utf-8")) or {}
        for k in [k for k in list(NICHES) if k not in _BUILTIN_KEYS and k not in data]:
            NICHES.pop(k, None)
        for k, cfg in data.items():
            if k in _BUILTIN_KEYS:
                continue
            cfg["custom"] = True
            NICHES[k] = cfg
        _custom_mtime = m
    except Exception:
        pass  # corrupt file should never break the app


def refresh_custom_niches() -> None:
    """Cheap mtime check — call before reads jahan freshness chahiye."""
    _load_custom_niches(force=False)


def add_custom_niche(
    name: str,
    keywords: list = None,
    target_type: str = "b2c",
    b2b_client: str = "",
    end_customer: str = "",
    avg_ticket_inr: str = "",
    pitch_hook: str = "",
    qualification_questions: list = None,
    lead_band: str = "A",
    key: str = None,
) -> tuple:
    """
    Naya niche register karo. Returns (key, config).
    Sensible defaults — sirf `name` zaroori hai; baaki business ke hisab se.
    """
    nkey = _slugify(key or name)
    refresh_custom_niches()
    if nkey in _BUILTIN_KEYS or nkey in NICHES:
        raise ValueError(f"Niche '{nkey}' already exists")
    if target_type not in ("b2c", "b2b", "both"):
        raise ValueError("target_type must be b2c | b2b | both")
    _band = str(lead_band or "A").strip().upper()
    cfg = {
        "name": name.strip(),
        "tier": "C",  # custom tier — dropdown me [custom] group
        "custom": True,
        "target_type": target_type,
        "b2b_client": b2b_client or f"{name} businesses",
        "end_customer": end_customer
        or (
            "Consumers interested in this service"
            if target_type != "b2b"
            else "Business buyers for this service"
        ),
        "keywords": keywords or [name.lower()],
        "avg_deal_value": avg_ticket_inr or "varies",
        "avg_ticket_inr": avg_ticket_inr or "varies",
        "pitch_hook": pitch_hook
        or f"bring qualified {name} customers to your business on autopilot",
        "lead_band": _band if _band in ("A", "B", "C") else "A",
        "qualification_questions": qualification_questions
        or [
            f"Are you currently looking for more {name} customers?",
            "What is your average deal or ticket size?",
            "Who follows up with your inquiries today?",
        ],
    }
    data = {}
    if _CUSTOM_FILE.exists():
        try:
            data = _json.loads(_CUSTOM_FILE.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    data[nkey] = cfg
    _CUSTOM_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOM_FILE.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    NICHES[nkey] = cfg
    _load_custom_niches(force=True)
    return nkey, cfg


def remove_custom_niche(key: str) -> bool:
    """Sirf custom niches delete ho sakte hain (builtin 25 protected)."""
    if key in _BUILTIN_KEYS:
        raise ValueError("Built-in niches cannot be removed")
    refresh_custom_niches()
    if not _CUSTOM_FILE.exists():
        return False
    try:
        data = _json.loads(_CUSTOM_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    if key not in data:
        return False
    del data[key]
    _CUSTOM_FILE.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    NICHES.pop(key, None)
    _load_custom_niches(force=True)
    return True


_load_custom_niches(force=True)  # module import pe custom niches merge


# Convenience views ------------------------------------------------------- #


def niches_by_tier(tier: str) -> dict:
    """Return niches of a given tier ('S' | 'A' | 'B' | 'C'=custom)."""
    refresh_custom_niches()
    return {k: v for k, v in NICHES.items() if v.get("tier") == tier}


def niches_by_target(target_type: str) -> dict:
    """Return niches whose END CUSTOMERS match 'b2c' | 'b2b' (includes 'both')."""
    refresh_custom_niches()
    return {k: v for k, v in NICHES.items() if v.get("target_type") in (target_type, "both")}


def niche_products(cfg: dict) -> list:
    """Niche kis PRODUCT me bikta hai (ADR-009 two-product split).

    category: "marketing" -> sirf Product 1 (AI Automated Marketing);
    "leadgen" -> sirf Product 2 (AI Voice Calling Agent); "both"/missing -> dono.
    """
    cat = str((cfg or {}).get("category") or "both").strip().lower()
    return {"marketing": ["marketing"], "leadgen": ["voice"]}.get(cat, ["marketing", "voice"])


def niches_for_product(product: str) -> dict:
    """product='marketing' | 'voice' ke niches — dono products ke niche sets ALAG."""
    refresh_custom_niches()
    p = (product or "").strip().lower()
    if p not in ("marketing", "voice"):
        return dict(NICHES)
    return {k: v for k, v in NICHES.items() if p in niche_products(v)}


def lead_band(key: str) -> str:
    """Voice-product pricing band ('A'|'B'|'C') for a niche key — default 'A'."""
    refresh_custom_niches()
    cfg = NICHES.get((key or "").strip().lower()) or {}
    b = str(cfg.get("lead_band") or "A").strip().upper()
    return b if b in ("A", "B", "C") else "A"


def classify_from_text(text: str, default: str = "general") -> str:
    """Best-match niche key for free text (e.g. Udyam MajorActivity + enterprise name).

    Scores each niche by how many of its keyword TOKENS appear in `text` (longer
    keyword phrases weigh more). Returns the top niche key, else `default`. Pure +
    never-raise — lets the Udyam pipeline tag each lead with the RIGHT niche so scoring
    + outreach pitch are accurate (was tagging everything 'general')."""
    try:
        refresh_custom_niches()
        t = " " + (text or "").lower().strip() + " "
        if not t.strip():
            return default
        best_key, best_score = default, 0
        for nkey, cfg in (NICHES or {}).items():
            score = 0
            for kw in (cfg or {}).get("keywords") or []:
                kwl = str(kw).lower().strip()
                if not kwl:
                    continue
                if kwl in t:  # full phrase match = strong signal
                    score += 3 + kwl.count(" ")
                else:  # partial: count distinct significant tokens present
                    toks = [w for w in kwl.split() if len(w) >= 4]
                    score += sum(1 for w in toks if f" {w}" in t)
            # also try the niche's own name/key as a weak signal
            if str(nkey).replace("_", " ") in t:
                score += 1
            if score > best_score:
                best_key, best_score = nkey, score
        # require a reasonably strong signal (>=2) so a weak single-token overlap
        # ("general trading") falls back to default instead of a wrong niche.
        return best_key if best_score >= 2 else default
    except Exception:
        return default
