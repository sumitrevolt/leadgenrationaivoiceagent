"""
Growth Engine — "self-run + self-improve" data-driven pulse (100% FREE).
========================================================================

User vision: "project self run and grow minute by minute by getting data,
knowledge and self-improvement techniques."

REALITY CHECK (honest, no magic): yeh koi self-aware AI nahi hai. Yeh ek
FREQUENT scheduler tick hai jo —
  1) live metrics aggregate karta hai (prospects/inquiries/emails/blog/
     content/clients/agent-actions) — ek "growth pulse" snapshot,
  2) apni pipelines ko SELF-HEAL karta hai (blog patla ho to ek article,
     content queue khali ho to generate, prospects kam ho to soch-samajh ke
     thoda scrape — cost-respecting),
  3) apne hi RESULTS se seekhta hai — kaunse niche/pitch se sabse zyada
     'replied'/'client' aaye, simple RATIO se (koi ML lib nahi) → best_niche
     + insights store karta hai taaki outreach wahi double-down kare,
  4) ek growth_pulse event log karta hai (Boss/manager ke naam).

Sab steps GUARDED hain — koi step fail ho to baaki chalte hain, pulse() KABHI
raise nahi karta. Free stack only: filesystem snapshots, koi paid API nahi.

Storage:
  - data/growth_pulse.json     -> latest snapshot (frontend isi ko padhता hai)
  - data/growth_history.jsonl  -> har pulse ki ek timestamped line (trend ke liye)

Scheduler (team_scheduler) har 15 min "growth" job se pulse() chalata hai —
"minute by minute" ka realistic free version. On-demand: POST /api/platform/
team/growth/run.

Test-monkeypatch: `_PULSE_FILE`, `_HISTORY_FILE` (tmp dirs me point karwao).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# IST for "today" boundaries (team_status/inquiries digest jaisa hi).
_IST = timezone(timedelta(hours=5, minutes=30))

# Snapshot + trend files. Tests inhe monkeypatch karte hain — hamesha module
# attribute ke through padho (globals()), taaki monkeypatch effective rahe.
_PULSE_FILE = os.path.join("data", "growth_pulse.json")
_HISTORY_FILE = os.path.join("data", "growth_history.jsonl")
_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")

# Self-heal thresholds (sab tunable — over-action se bachne ke liye conservative).
_MIN_BLOG_ARTICLES = 10  # itne se kam blog → ek naya article banao
_MIN_PROSPECTS_READY = 10  # itne se kam ready prospects → light top-up (gated)
_SCRAPE_TRIGGER_READY = 5  # sirf tab scrape jab ready isse bhi neeche ho
_SCRAPE_MIN_GAP_HOURS = 6.0  # last prospecting run se itne ghante baad hi (cost-respect)
_HISTORY_TRIM = 2000  # history.jsonl me last itni lines hi rakho (file bound)


# --------------------------------------------------------------------------- #
# Small JSON helpers (never raise)
# --------------------------------------------------------------------------- #
def _read_json(path: str) -> dict[str, Any]:
    try:
        if not os.path.isfile(path):
            return {}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug(f"[growth] read {path} failed: {e}")
        return {}


def _write_json(path: str, obj: dict[str, Any]) -> bool:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, default=str, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as e:
        logger.warning(f"[growth] write {path} failed: {e}")
        return False


def _append_history(line_obj: dict[str, Any]) -> None:
    """History me ek line append karo + file ko _HISTORY_TRIM lines pe bound rakho."""
    path = globals().get("_HISTORY_FILE", _HISTORY_FILE)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line_obj, ensure_ascii=False, default=str) + "\n")
        # Best-effort trim — file bahut badi na ho.
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > _HISTORY_TRIM:
                with open(path, "w", encoding="utf-8") as f:
                    f.writelines(lines[-_HISTORY_TRIM:])
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"[growth] history append failed: {e}")


# --------------------------------------------------------------------------- #
# inquiries.jsonl helpers — total + today (IST)
# --------------------------------------------------------------------------- #
def _inquiry_rows() -> list[dict[str, Any]]:
    """Saari inquiries (parse-safe; corrupt lines skip). Kabhi raise nahi."""
    rows: list[dict[str, Any]] = []
    path = globals().get("_INQUIRIES_FILE", _INQUIRIES_FILE)
    try:
        if not os.path.isfile(path):
            return rows
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict):
                        rows.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[growth] inquiries read failed: {e}")
    return rows


def _count_today_ist(rows: list[dict[str, Any]], ts_key: str = "at") -> int:
    """Aaj (IST midnight se) ki entries count karo. Parse-fail rows skip."""
    try:
        ist_now = datetime.now(_IST)
        start = ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start.astimezone(timezone.utc).replace(tzinfo=None)
        n = 0
        for r in rows:
            at = str(r.get(ts_key) or "").replace("Z", "")
            if not at:
                continue
            try:
                dt = datetime.fromisoformat(at)
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                if dt >= start_utc:
                    n += 1
            except Exception:
                continue
        return n
    except Exception:
        return 0


# --------------------------------------------------------------------------- #
# collect_metrics — live snapshot of the whole platform
# --------------------------------------------------------------------------- #
def collect_metrics() -> dict[str, Any]:
    """Ek live growth snapshot dict banao. Har source apne try/except me — koi
    bhi source fail ho to uska metric 0/empty, baaki aate rahein. Snapshot ko
    data/growth_pulse.json me save karta hai (latest) + history me ek line
    append karta hai. KABHI raise nahi karta.

    Returns dict with keys:
      at, prospects{total,ready,sent,replied,client,dead,with_email},
      inquiries{total,today}, emails{with_email,emailed,pending},
      blog_articles, content_items, marketing_clients_active,
      actions_today, top_staff
    """
    snap: dict[str, Any] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "prospects": {
            "total": 0,
            "ready": 0,
            "sent": 0,
            "replied": 0,
            "client": 0,
            "dead": 0,
            "with_email": 0,
        },
        "inquiries": {"total": 0, "today": 0},
        "emails": {"with_email": 0, "emailed": 0, "pending": 0},
        "blog_articles": 0,
        "content_items": 0,
        "marketing_clients_active": 0,
        "actions_today": 0,
        "top_staff": [],
    }

    # --- prospects (by status + with_email) --- #
    try:
        from app.platform import prospector

        rows = prospector.list_prospects(limit=2000)
        snap["prospects"]["total"] = len(rows)
        for r in rows:
            st = str(r.get("status") or "ready").lower()
            if st in snap["prospects"]:
                snap["prospects"][st] += 1
            em = str(r.get("email") or "").strip()
            if "@" in em and "." in em.split("@")[-1]:
                snap["prospects"]["with_email"] += 1
    except Exception as e:
        logger.debug(f"[growth] prospects metric failed: {e}")

    # DB fallback: agar jsonl 0 deta hai to Postgres se real counts lo
    if snap["prospects"]["total"] == 0:
        try:
            from sqlalchemy import func as _sfunc
            from sqlalchemy import select as _sselect

            from app.models.base import get_db_session
            from app.models.lead import Lead

            with get_db_session() as _db:
                _total = _db.query(Lead).count()
                snap["prospects"]["total"] = _total
                # status breakdown
                from app.models.lead import LeadStatus

                for _ls in LeadStatus:
                    _cnt = _db.query(Lead).filter(Lead.status == _ls).count()
                    _key = _ls.value.lower()
                    if _key in snap["prospects"]:
                        snap["prospects"][_key] += _cnt
                # email count
                _em_cnt = _db.query(Lead).filter(Lead.email.isnot(None), Lead.email != "").count()
                snap["prospects"]["with_email"] = _em_cnt
        except Exception as _dbe:
            logger.debug(f"[growth] DB prospects fallback failed: {_dbe}")

    # --- inquiries (total + today) --- #
    try:
        rows = _inquiry_rows()
        snap["inquiries"]["total"] = len(rows)
        snap["inquiries"]["today"] = _count_today_ist(rows, "at")
    except Exception as e:
        logger.debug(f"[growth] inquiries metric failed: {e}")

    # --- email outreach stats --- #
    try:
        from app.platform import auto_outreach

        st = auto_outreach.outreach_stats() or {}
        snap["emails"] = {
            "with_email": int(st.get("with_email", 0) or 0),
            "emailed": int(st.get("emailed", 0) or 0),
            "pending": int(st.get("pending", 0) or 0),
        }
    except Exception as e:
        logger.debug(f"[growth] email stats failed: {e}")

    # --- blog article count --- #
    try:
        from app.marketing import seo_blog

        snap["blog_articles"] = len(seo_blog.list_articles(limit=1000))
    except Exception as e:
        logger.debug(f"[growth] blog metric failed: {e}")

    # --- marketing clients active + total content queue items --- #
    try:
        from app.marketing import auto_content, clients_store

        clients = clients_store.list_clients("active") or []
        snap["marketing_clients_active"] = len(clients)
        items = 0
        for c in clients:
            try:
                items += len(auto_content.list_queue(str(c.get("id")), limit=500))
            except Exception:
                continue
        snap["content_items"] = items
    except Exception as e:
        logger.debug(f"[growth] content metric failed: {e}")

    # --- agent actions today + top staff (from team_status) --- #
    try:
        from app.platform import team

        ts = team.team_status() or {}
        snap["actions_today"] = int((ts.get("totals") or {}).get("actions_today", 0) or 0)
        members = sorted(
            (ts.get("members") or []),
            key=lambda m: int(m.get("today_actions") or 0),
            reverse=True,
        )
        snap["top_staff"] = [
            {
                "name": m.get("name"),
                "emoji": m.get("emoji"),
                "today_actions": int(m.get("today_actions") or 0),
            }
            for m in members[:3]
            if int(m.get("today_actions") or 0) > 0
        ]
    except Exception as e:
        logger.debug(f"[growth] team metric failed: {e}")

    # --- persist: latest snapshot (merge into existing so insights survive) --- #
    try:
        pulse_file = globals().get("_PULSE_FILE", _PULSE_FILE)
        existing = _read_json(pulse_file)
        existing.update(snap)
        _write_json(pulse_file, existing)
    except Exception as e:
        logger.debug(f"[growth] snapshot persist failed: {e}")

    # --- history line (compact, for trend charts later) --- #
    try:
        _append_history(
            {
                "at": snap["at"],
                "prospects_total": snap["prospects"]["total"],
                "prospects_ready": snap["prospects"]["ready"],
                "inquiries_total": snap["inquiries"]["total"],
                "inquiries_today": snap["inquiries"]["today"],
                "emailed": snap["emails"]["emailed"],
                "blog_articles": snap["blog_articles"],
                "content_items": snap["content_items"],
                "clients_active": snap["marketing_clients_active"],
                "actions_today": snap["actions_today"],
            }
        )
    except Exception as e:
        logger.debug(f"[growth] history line failed: {e}")

    return snap


# --------------------------------------------------------------------------- #
# Pitch learning — kaunse niche se sabse zyada conversions (replied/client)?
# --------------------------------------------------------------------------- #
def _learn_best_niche() -> dict[str, Any]:
    """Prospects ke statuses + inquiries se per-niche conversion RATIO nikalo.

    Conversion signal = status in {replied, client} (warm/won). Ratio =
    conversions / total_prospects(niche). 'best_niche' = highest ratio jiska
    sample chhota na ho (min 3 prospects). Inquiries ke niche/package bhi count
    hote hain (demand signal). Pure logic — koi ML lib nahi. Failure -> {}.
    """
    out: dict[str, Any] = {
        "best_niche": None,
        "best_niche_ratio": 0.0,
        "by_niche": {},
        "inquiry_niches": {},
        "insights": [],
    }
    try:
        from app.platform import prospector

        rows = prospector.list_prospects(limit=500)

        # Per-niche tallies.
        per: dict[str, dict[str, int]] = {}
        for r in rows:
            niche = str(r.get("niche") or "general").strip().lower() or "general"
            st = str(r.get("status") or "ready").lower()
            d = per.setdefault(niche, {"total": 0, "replied": 0, "client": 0, "sent": 0})
            d["total"] += 1
            if st in d:
                d[st] += 1

        by_niche: dict[str, dict[str, Any]] = {}
        best_niche = None
        best_ratio = -1.0
        for niche, d in per.items():
            conv = d.get("replied", 0) + d.get("client", 0)
            total = max(1, d.get("total", 0))
            ratio = round(conv / total, 3)
            by_niche[niche] = {
                "total": d["total"],
                "replied": d.get("replied", 0),
                "client": d.get("client", 0),
                "sent": d.get("sent", 0),
                "conversion_ratio": ratio,
            }
            # Best = highest ratio with a non-trivial sample (>=3 prospects).
            if d["total"] >= 3 and ratio > best_ratio:
                best_ratio = ratio
                best_niche = niche
        out["by_niche"] = by_niche

        # Inquiries → demand by niche/package (jo log khud aaye).
        inq_niches: dict[str, int] = {}
        for r in _inquiry_rows():
            key = str(r.get("niche") or r.get("package") or r.get("interest") or "").strip().lower()
            if key:
                inq_niches[key] = inq_niches.get(key, 0) + 1
        out["inquiry_niches"] = inq_niches

        # If no prospect signal yet, fall back to most-demanded inquiry niche.
        if best_niche is None and inq_niches:
            best_niche = max(inq_niches.items(), key=lambda kv: kv[1])[0]
            best_ratio = 0.0

        out["best_niche"] = best_niche
        out["best_niche_ratio"] = round(best_ratio, 3) if best_ratio >= 0 else 0.0

        # ---- human-readable Hinglish insights ---- #
        insights: list[str] = []
        if best_niche and best_ratio > 0:
            insights.append(
                f"Best converting niche: '{best_niche}' "
                f"({int(best_ratio * 100)}% prospects warm/won) — yahan zyada outreach karo."
            )
        elif best_niche:
            insights.append(
                f"Sabse zyada demand '{best_niche}' niche me dikh rahi hai — ispe focus badhao."
            )
        # Dead-heavy niches → pitch revisit.
        for niche, d in by_niche.items():
            if d["total"] >= 5 and d.get("conversion_ratio", 0) == 0:
                insights.append(
                    f"'{niche}' me {d['total']} prospects par 0 conversion — "
                    "pitch/targeting revisit karo."
                )
                break
        if not insights:
            insights.append(
                "Abhi conversion data patla hai — pipeline bharo, "
                "thode replies aate hi best niche auto-detect hoga."
            )
        out["insights"] = insights[:4]
    except Exception as e:
        logger.debug(f"[growth] niche learning failed: {e}")
    return out


# --------------------------------------------------------------------------- #
# Self-heal — pipelines ko bhara rakho (cost-respecting, guarded)
# --------------------------------------------------------------------------- #
async def _self_heal(metrics: dict[str, Any]) -> dict[str, Any]:
    """Patli pipelines ko top-up karo. Har action apne try/except me; KABHI
    raise nahi. Returns {"actions": [...]} (kya-kya kiya, dashboard ke liye)."""
    actions: list[str] = []

    # (a) Blog patla ho → ek naya article (free LLM + template fallback).
    try:
        if int(metrics.get("blog_articles", 0) or 0) < _MIN_BLOG_ARTICLES:
            from app.marketing import seo_blog

            res = await seo_blog.run_daily_blog(1)
            pub = (res or {}).get("published", 0)
            if pub:
                actions.append(f"blog +{pub} article")
    except Exception as e:
        logger.debug(f"[growth] self-heal blog failed: {e}")

    # (b) Content queue khali ho (active clients hain par 0 items) → generate.
    try:
        clients = int(metrics.get("marketing_clients_active", 0) or 0)
        items = int(metrics.get("content_items", 0) or 0)
        if clients > 0 and items == 0:
            from app.marketing import auto_content

            res = await auto_content.run_daily_content()
            made = (res or {}).get("items", 0)
            if made:
                actions.append(f"content +{made} items")
    except Exception as e:
        logger.debug(f"[growth] self-heal content failed: {e}")

    # (c) Prospects bahut kam → SOCH-SAMAJH ke light top-up (over-scrape nahi).
    #     Sirf tab jab ready < _SCRAPE_TRIGGER_READY AND last run > 6h purana
    #     (Google Maps billing + OSM politeness respect). Gap last growth_pulse
    #     ke "last_scrape_at" marker se track hota hai.
    try:
        ready = int((metrics.get("prospects") or {}).get("ready", 0) or 0)
        if ready < _SCRAPE_TRIGGER_READY:
            prev = _read_json(globals().get("_PULSE_FILE", _PULSE_FILE))
            last_scrape = str(prev.get("last_scrape_at") or "").strip()
            gap_ok = True
            if last_scrape:
                try:
                    s = last_scrape[:-1] if last_scrape.endswith("Z") else last_scrape
                    dt = datetime.fromisoformat(s)
                    hrs = (datetime.utcnow() - dt).total_seconds() / 3600.0
                    gap_ok = hrs >= _SCRAPE_MIN_GAP_HOURS
                except Exception:
                    gap_ok = True
            if gap_ok:
                from app.platform import prospector

                # Chhota limit — surprise cost na ho (daily 09:30 run bada hai).
                res = await prospector.run_prospecting(limit_per_query=5)
                new = (res or {}).get("new", 0)
                actions.append(f"prospect top-up +{new}")
                # Marker — next pulse 6h tak dobara scrape na kare.
                try:
                    cur = _read_json(globals().get("_PULSE_FILE", _PULSE_FILE))
                    cur["last_scrape_at"] = datetime.utcnow().isoformat() + "Z"
                    _write_json(globals().get("_PULSE_FILE", _PULSE_FILE), cur)
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"[growth] self-heal prospect failed: {e}")

    return {"actions": actions}


# --------------------------------------------------------------------------- #
# pulse — the frequent "self-run" tick (scheduler har 15 min)
# --------------------------------------------------------------------------- #
async def pulse() -> dict[str, Any]:
    """Ek growth pulse: metrics collect → self-heal pipelines → pitch learning
    → event log. Har step guarded; KABHI raise nahi karta. Returns the merged
    pulse dict (jo data/growth_pulse.json me bhi save hota hai)."""
    try:
        # (a) live snapshot (also persists growth_pulse.json + history line)
        metrics = collect_metrics()

        # (b) self-heal thin pipelines (cost-respecting)
        heal = {"actions": []}
        try:
            heal = await _self_heal(metrics)
        except Exception as e:
            logger.debug(f"[growth] self-heal block failed: {e}")

        # (c) learn best-performing niche/pitch from own results
        learning = {}
        try:
            learning = _learn_best_niche()
        except Exception as e:
            logger.debug(f"[growth] learning block failed: {e}")

        # ---- merge learning + heal-actions into the persisted pulse ---- #
        pulse_file = globals().get("_PULSE_FILE", _PULSE_FILE)
        merged = _read_json(pulse_file)
        merged.update(metrics)
        merged["healed"] = heal.get("actions", [])
        merged["best_niche"] = learning.get("best_niche")
        merged["best_niche_ratio"] = learning.get("best_niche_ratio", 0.0)
        merged["insights"] = learning.get("insights", [])
        merged["niche_breakdown"] = learning.get("by_niche", {})
        merged["inquiry_niches"] = learning.get("inquiry_niches", {})
        merged["last_pulse_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(pulse_file, merged)

        # (d) log a growth_pulse event (Boss / manager)
        try:
            from app.platform import team

            p = merged.get("prospects") or {}
            summary = (
                f"pulse: {p.get('total', 0)} prospects "
                f"({p.get('ready', 0)} ready), "
                f"{(merged.get('inquiries') or {}).get('total', 0)} inquiries, "
                f"{(merged.get('emails') or {}).get('emailed', 0)} emailed, "
                f"{merged.get('blog_articles', 0)} blogs, "
                f"{merged.get('actions_today', 0)} actions today"
            )
            healed = merged.get("healed") or []
            if healed:
                summary += f" | healed: {', '.join(healed)}"
            if merged.get("best_niche"):
                summary += f" | best: {merged['best_niche']}"
            team.log_event(
                "manager",
                "growth_pulse",
                summary[:480],
                meta={
                    "prospects": p,
                    "inquiries": merged.get("inquiries"),
                    "emails": merged.get("emails"),
                    "blog_articles": merged.get("blog_articles"),
                    "content_items": merged.get("content_items"),
                    "actions_today": merged.get("actions_today"),
                    "healed": healed,
                    "best_niche": merged.get("best_niche"),
                },
            )
        except Exception as e:
            logger.debug(f"[growth] pulse event log failed: {e}")

        logger.info(f"[growth] pulse done — healed={merged.get('healed')}")
        return merged
    except Exception as e:  # absolute guard — scheduler/API kabhi na gire
        logger.warning(f"[growth] pulse failed: {e}")
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# Read helpers (API/dashboard)
# --------------------------------------------------------------------------- #
def latest_pulse() -> dict[str, Any]:
    """Latest growth snapshot (data/growth_pulse.json). {} agar abhi tak kuch nahi."""
    return _read_json(globals().get("_PULSE_FILE", _PULSE_FILE))


def history(limit: int = 50) -> list[dict[str, Any]]:
    """Last `limit` pulse history lines (newest first). KABHI raise nahi karta."""
    out: list[dict[str, Any]] = []
    path = globals().get("_HISTORY_FILE", _HISTORY_FILE)
    try:
        if not os.path.isfile(path):
            return out
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        try:
            lim = max(1, min(int(limit), 1000))
        except Exception:
            lim = 50
        for ln in lines[-lim:]:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
                if isinstance(rec, dict):
                    out.append(rec)
            except Exception:
                continue
        out.reverse()  # newest first
    except Exception as e:
        logger.debug(f"[growth] history read failed: {e}")
    return out


__all__ = ["collect_metrics", "pulse", "latest_pulse", "history"]
