"""Memory Vault — Rowboat-inspired compounding MARKDOWN memory per entity.

Har prospect / client / topic ka ek long-lived .md file jo events se BADHTA
rehta hai (cold retrieval nahi — accumulated context):

    data/memory/prospects/<phone10>.md
    data/memory/clients/<client_id>.md
    data/memory/topics/<slug>.md       (live_notes.py inka owner)

File structure:
    # <title>
    ## Profile      — key facts (dedupe'd bullet lines)
    ## Timeline     — append-only "- YYYY-MM-DD HH:MM — event" (newest LAST)
    ## Summary      — compacted digest (timeline > 80 bullets → compact + trim to 30)

SYNC JOB pattern (HOT-PATH HOOK NAHI — prod-down lesson): `sync_all()` existing
jsonl stores (inquiries / widget_chats / dialer_logs / deals) ko line-count
CURSOR se tail karta (data/memory/_cursor.json). Scheduler se `sync_if_enabled()`
(gated `MEMORY_VAULT=1`, default OFF) — sync_all khud sync+cheap, no LLM/network.

LLM sirf optional `regen_summary()` me (async, wait_for 25s) — sync path me
STATIC digest (job kabhi network pe na atke). Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Module-level store paths (tests monkeypatch karte hain)
_MEM_DIR = os.path.join("data", "memory")
_INQUIRIES = os.path.join("data", "inquiries.jsonl")
_CHATS = os.path.join("data", "widget_chats.jsonl")
_DIALER = os.path.join("data", "dialer_logs.jsonl")
_DEALS = os.path.join("data", "deals.jsonl")

KINDS = ("prospects", "clients", "topics")

_MAX_FILE_BYTES = 64 * 1024  # edit_memory hard cap
_COMPACT_AT = 80  # timeline bullets isse zyada → compact
_KEEP_AFTER_COMPACT = 30  # compact ke baad itne recent bullets rakho
_MAX_PROFILE_FACTS = 40

_IST = timezone(timedelta(hours=5, minutes=30))
# Indian mobile in free text (conversion.py jaisa hi pattern)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?([6-9]\d{9})(?!\d)")


# --------------------------------------------------------------------------- #
# Path / key helpers
# --------------------------------------------------------------------------- #
def _safe_key(key: str) -> str:
    """Filename-safe key (alnum/dash/underscore, lowercase, max 64ch)."""
    k = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(key or "").strip()).strip("-").lower()
    return k[:64]


def phone10(raw: Any) -> str:
    """Kisi bhi phone format se last-10 digits (prospect memory key)."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else ""


def _dir(kind: str) -> str:
    return os.path.join(_MEM_DIR, kind)


def _path(kind: str, key: str) -> str | None:
    if kind not in KINDS:
        return None
    sk = _safe_key(key)
    if not sk:
        return None
    return os.path.join(_dir(kind), sk + ".md")


def _cursor_path() -> str:
    return os.path.join(_MEM_DIR, "_cursor.json")


def _now_ist() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------- #
# Markdown parse / serialize
# --------------------------------------------------------------------------- #
def _parse(md: str) -> dict[str, Any]:
    """md text → {title, profile[], timeline[], summary}. Tolerant parser."""
    out: dict[str, Any] = {"title": "", "profile": [], "timeline": [], "summary": ""}
    section = ""
    summary_lines: list[str] = []
    for line in (md or "").splitlines():
        s = line.strip()
        if s.startswith("# ") and not out["title"]:
            out["title"] = s[2:].strip()
            continue
        low = s.lower()
        if low.startswith("## profile"):
            section = "profile"
            continue
        if low.startswith("## timeline"):
            section = "timeline"
            continue
        if low.startswith("## summary"):
            section = "summary"
            continue
        if section == "profile" and s.startswith("- "):
            out["profile"].append(s[2:].strip())
        elif section == "timeline" and s.startswith("- "):
            out["timeline"].append(s[2:].strip())
        elif section == "summary" and s:
            summary_lines.append(s)
    out["summary"] = "\n".join(summary_lines).strip()
    return out


def _serialize(mem: dict[str, Any]) -> str:
    parts = [f"# {mem.get('title') or 'Memory'}", "", "## Profile"]
    parts += [f"- {f}" for f in mem.get("profile", [])]
    parts += ["", "## Timeline"]
    parts += [f"- {b}" for b in mem.get("timeline", [])]
    parts += ["", "## Summary", mem.get("summary") or "(abhi khali)", ""]
    return "\n".join(parts)


def _load(kind: str, key: str) -> dict[str, Any] | None:
    p = _path(kind, key)
    if not p:
        return None
    try:
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                return _parse(f.read(_MAX_FILE_BYTES + 1024))
    except Exception as e:
        logger.debug(f"[memory] load failed {kind}/{key}: {e}")
    return {"title": "", "profile": [], "timeline": [], "summary": ""}


def _save(kind: str, key: str, mem: dict[str, Any]) -> bool:
    p = _path(kind, key)
    if not p:
        return False
    try:
        # ATOMIC + cross-process locked. Bare open("w") truncated the file first, so a
        # concurrent reader (call_prep/proposal injecting memory into an LLM prompt) could
        # read an empty/partial file across the 2 uvicorn workers + celery writers.
        from app.utils.file_lock import locked_rewrite

        return locked_rewrite(p, _serialize(mem))
    except Exception as e:
        logger.warning(f"[memory] save failed {kind}/{key}: {e}")
        return False


# --------------------------------------------------------------------------- #
# Public memory ops
# --------------------------------------------------------------------------- #
def get_memory(kind: str, key: str) -> str | None:
    """Raw markdown text (ya None agar file nahi). Kabhi raise nahi."""
    p = _path(kind, key)
    try:
        if p and os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                return f.read(_MAX_FILE_BYTES + 1024)
    except Exception as e:
        logger.debug(f"[memory] get failed: {e}")
    return None


def edit_memory(kind: str, key: str, content: str) -> dict[str, Any]:
    """Human-editable full overwrite (64KB cap). Kabhi raise nahi."""
    try:
        if kind not in KINDS:
            return {"ok": False, "error": f"kind inme se ho: {', '.join(KINDS)}"}
        p = _path(kind, key)
        if not p:
            return {"ok": False, "error": "valid key chahiye"}
        text = str(content or "")
        if len(text.encode("utf-8")) > _MAX_FILE_BYTES:
            return {"ok": False, "error": "content 64KB se bada hai — chhota karo"}
        from app.utils.file_lock import locked_rewrite

        locked_rewrite(p, text)  # atomic+locked (was bare open("w") truncate-then-write)
        return {"ok": True, "kind": kind, "key": _safe_key(key), "bytes": len(text.encode("utf-8"))}
    except Exception as e:
        logger.warning(f"[memory] edit failed: {e}")
        return {"ok": False, "error": str(e)}


def list_entities(kind: str) -> list[dict[str, Any]]:
    """Kind ke saare memory files (key, mtime, size) — newest first. Kabhi raise nahi."""
    out: list[dict[str, Any]] = []
    try:
        if kind not in KINDS:
            return out
        d = _dir(kind)
        if not os.path.isdir(d):
            return out
        for name in os.listdir(d):
            if not name.endswith(".md"):
                continue
            fp = os.path.join(d, name)
            try:
                st = os.stat(fp)
                out.append(
                    {
                        "key": name[:-3],
                        "kind": kind,
                        "size": st.st_size,
                        "updated_at": datetime.fromtimestamp(
                            st.st_mtime, tz=timezone.utc
                        ).isoformat(),
                    }
                )
            except Exception:
                continue
        out.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    except Exception as e:
        logger.debug(f"[memory] list failed: {e}")
    return out


def upsert_profile_fact(kind: str, key: str, fact: str, title: str = "") -> bool:
    """Profile me ek fact add (case-insensitive dedupe, cap 40). Kabhi raise nahi."""
    try:
        f = str(fact or "").strip()[:200]
        if not f or kind not in KINDS:
            return False
        mem = _load(kind, key)
        if mem is None:
            return False
        if title and not mem.get("title"):
            mem["title"] = title[:120]
        existing = {x.strip().lower() for x in mem["profile"]}
        if f.lower() in existing:
            return True  # already there = success
        mem["profile"] = (mem["profile"] + [f])[-_MAX_PROFILE_FACTS:]
        return _save(kind, key, mem)
    except Exception as e:
        logger.debug(f"[memory] fact failed: {e}")
        return False


def add_event(kind: str, key: str, event: str, title: str = "") -> bool:
    """Timeline me dated bullet append (newest LAST). >80 bullets → static
    compact (digest Summary me, timeline trim to 30). Kabhi raise nahi."""
    try:
        ev = re.sub(r"\s+", " ", str(event or "")).strip()[:240]
        if not ev or kind not in KINDS:
            return False
        mem = _load(kind, key)
        if mem is None:
            return False
        if title and not mem.get("title"):
            mem["title"] = title[:120]
        bullet = f"{_now_ist()} — {ev}"
        # consecutive-duplicate guard (same event do baar tail hua to)
        if mem["timeline"] and mem["timeline"][-1].split(" — ", 1)[-1] == ev:
            return True
        mem["timeline"].append(bullet)
        if len(mem["timeline"]) > _COMPACT_AT:
            _compact_static(mem)
        return _save(kind, key, mem)
    except Exception as e:
        logger.debug(f"[memory] event failed: {e}")
        return False


def _compact_static(mem: dict[str, Any]) -> None:
    """Purane bullets → chhota static digest Summary me; timeline trim.
    Sync path me LLM NAHI (job kabhi network pe na atke) — LLM regen alag."""
    old = mem["timeline"][:-_KEEP_AFTER_COMPACT]
    mem["timeline"] = mem["timeline"][-_KEEP_AFTER_COMPACT:]
    if not old:
        return
    first_d = old[0].split(" ", 1)[0]
    last_d = old[-1].split(" ", 1)[0]
    # event-type rough counts (pehla word group)
    counts: dict[str, int] = {}
    for b in old:
        tail = b.split(" — ", 1)[-1]
        head = tail.split(":")[0].split(" ")[0].strip().lower() or "event"
        counts[head] = counts.get(head, 0) + 1
    top = ", ".join(f"{k}×{v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])[:5])
    digest = f"[{first_d} → {last_d}] {len(old)} purani events compact: {top}."
    mem["summary"] = (mem.get("summary", "") + "\n" + digest).strip()[:4000]


async def regen_summary(kind: str, key: str) -> dict[str, Any]:
    """Optional LLM summary regen (free_ai, 25s cap, fallback = current). Kabhi raise nahi."""
    try:
        import asyncio

        mem = _load(kind, key)
        if mem is None or not (mem["timeline"] or mem["profile"]):
            return {"ok": False, "error": "memory khali ya key galat"}
        try:
            from app.voice_agent import free_ai

            corpus = "\n".join(mem["profile"][-20:] + mem["timeline"][-60:])[:4000]
            txt, _prov = await asyncio.wait_for(
                free_ai.chat(
                    "Tum ek CRM analyst ho. Niche di gayi prospect/client history ko 3-5 line "
                    "Hinglish summary me compact karo (kaun hai, kya hua, abhi kahan khada). Sirf summary.",
                    [{"role": "user", "content": corpus}],
                    max_tokens=220,
                ),
                timeout=25,
            )
            if txt and txt.strip():
                mem["summary"] = txt.strip()[:2000]
                _save(kind, key, mem)
                return {"ok": True, "summary": mem["summary"]}
        except Exception as e:
            logger.debug(f"[memory] llm summary skip: {e}")
        return {"ok": True, "summary": mem.get("summary", ""), "provider": "fallback"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def context_snippet(
    phone: str | None = None, client_id: str | None = None, max_chars: int = 1200
) -> str:
    """Agents ke liye fast context: Summary + Profile + last 10 timeline bullets.
    Pure sync, no LLM, max 2 file reads. Memory na ho to ''. Kabhi raise nahi."""
    try:
        parts: list[str] = []
        for kind, key in (
            ("prospects", phone10(phone) if phone else ""),
            ("clients", client_id or ""),
        ):
            if not key:
                continue
            p = _path(kind, key)
            if not p or not os.path.isfile(p):
                continue
            mem = _load(kind, key)
            if not mem:
                continue
            seg = []
            if mem.get("title"):
                seg.append(f"[{mem['title']}]")
            if mem.get("summary"):
                seg.append("Summary: " + mem["summary"][:400])
            if mem.get("profile"):
                seg.append("Facts: " + "; ".join(mem["profile"][:10]))
            if mem.get("timeline"):
                seg.append("Recent: " + " | ".join(mem["timeline"][-10:]))
            if seg:
                parts.append("\n".join(seg))
        return "\n---\n".join(parts)[: max(200, max_chars)]
    except Exception as e:
        logger.debug(f"[memory] snippet failed: {e}")
        return ""


# --------------------------------------------------------------------------- #
# Sync job — jsonl stores ko cursor se tail karo (NO hot-path hooks)
# --------------------------------------------------------------------------- #
def _read_cursor() -> dict[str, int]:
    try:
        with open(_cursor_path(), encoding="utf-8") as f:
            d = json.load(f)
            return {str(k): int(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write_cursor(cur: dict[str, int]) -> None:
    try:
        os.makedirs(os.path.dirname(_cursor_path()), exist_ok=True)
        with open(_cursor_path(), "w", encoding="utf-8") as f:
            json.dump(cur, f)
    except Exception as e:
        logger.debug(f"[memory] cursor write failed: {e}")


def _tail_new(path: str, done: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    """File ki `done` ke baad wali max-`limit` NEW jsonl lines. Returns (records,
    new_done). File chhota ho gaya (rewrite/trim) to cursor reset — reprocess
    nahi karte (duplicate events se behtar miss). Kabhi raise nahi."""
    recs: list[dict[str, Any]] = []
    last_n = 0
    new_done = done
    try:
        if not os.path.isfile(path):
            return recs, done
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, start=1):
                last_n = n
                if n <= done:
                    continue
                if len(recs) >= limit:
                    break
                new_done = n  # consumed (corrupt ho ya na ho — cursor drift na ho)
                try:
                    r = json.loads(line)
                    if isinstance(r, dict):
                        recs.append(r)
                except Exception:
                    continue
        if not recs and last_n < done:  # file shrank (rewrite-store / manual trim)
            return [], last_n
        return recs, new_done
    except Exception as e:
        logger.debug(f"[memory] tail failed {path}: {e}")
        return [], done


def sync_all(limit_per_store: int = 500) -> dict[str, Any]:
    """Saare stores se naye events memory files me. Sync + cheap (no LLM/network).
    Defensive per-store. Returns {store: events_added}. Kabhi raise nahi."""
    summary: dict[str, Any] = {"ok": True}
    try:
        cur = _read_cursor()

        # 1) inquiries.jsonl → prospect (+ client agar mini-site/client_id)
        try:
            recs, cur[_INQUIRIES] = _tail_new(_INQUIRIES, cur.get(_INQUIRIES, 0), limit_per_store)
            n = 0
            for r in recs:
                ph = phone10(r.get("phone"))
                msg = str(r.get("message") or "").strip()[:80]
                src = str(r.get("source") or "website")
                ev = f"Inquiry via {src}" + (f": {msg}" if msg else "")
                title = str(r.get("business_name") or r.get("name") or "").strip()
                if ph and add_event("prospects", ph, ev, title=title or f"Prospect {ph}"):
                    n += 1
                    for label, val in (
                        ("Naam", r.get("name")),
                        ("Business", r.get("business_name")),
                        ("Niche", r.get("niche")),
                        ("City", r.get("city")),
                        ("Package interest", r.get("package")),
                    ):
                        if val:
                            upsert_profile_fact(
                                "prospects", ph, f"{label}: {str(val).strip()[:80]}"
                            )
                cid = str(r.get("client_id") or "").strip()
                if cid:
                    who = str(r.get("name") or ph or "lead").strip()[:60]
                    if add_event(
                        "clients",
                        cid,
                        f"Mini-site inquiry: {who}" + (f" — {msg[:60]}" if msg else ""),
                        title=f"Client {cid}",
                    ):
                        n += 1
            summary["inquiries"] = n
        except Exception as e:
            logger.debug(f"[memory] inquiries sync skip: {e}")
            summary["inquiries"] = 0

        # 2) widget_chats.jsonl → prospect (sirf un sessions ke user-turns jinme phone mila)
        try:
            recs, cur[_CHATS] = _tail_new(_CHATS, cur.get(_CHATS, 0), limit_per_store)
            sess_phone: dict[str, str] = {}
            for r in recs:  # pass 1: session → phone map (batch ke andar)
                sid = str(r.get("session_id") or "")
                if not sid or sid in sess_phone:
                    continue
                m = _PHONE_RE.search(str(r.get("phone") or "") + " " + str(r.get("text") or ""))
                if m:
                    sess_phone[sid] = m.group(1)
            n = 0
            for r in recs:  # pass 2: user turns of phone-known sessions
                if str(r.get("role") or "") != "user":
                    continue
                ph = sess_phone.get(str(r.get("session_id") or ""))
                if not ph:
                    continue
                txt = str(r.get("text") or "").strip()[:80]
                if txt and add_event("prospects", ph, f"Web chat: {txt}", title=f"Prospect {ph}"):
                    n += 1
            summary["widget_chats"] = n
        except Exception as e:
            logger.debug(f"[memory] chats sync skip: {e}")
            summary["widget_chats"] = 0

        # 3) dialer_logs.jsonl → prospect (disposition + notes)
        try:
            recs, cur[_DIALER] = _tail_new(_DIALER, cur.get(_DIALER, 0), limit_per_store)
            n = 0
            for r in recs:
                ph = phone10(r.get("phone"))
                if not ph:
                    continue
                disp = str(r.get("disposition") or "call").strip()
                notes = str(r.get("notes") or "").strip()[:60]
                ev = f"Call (dialer): {disp}" + (f" — {notes}" if notes else "")
                if add_event("prospects", ph, ev, title=f"Prospect {ph}"):
                    n += 1
            summary["dialer_logs"] = n
        except Exception as e:
            logger.debug(f"[memory] dialer sync skip: {e}")
            summary["dialer_logs"] = 0

        # 4) deals.jsonl (rewrite-store: sirf NAYE deals new-line banate; in-place
        #    stage edits cursor se nahi dikhte — acceptable, dialer/inquiry cover karte)
        try:
            recs, cur[_DEALS] = _tail_new(_DEALS, cur.get(_DEALS, 0), limit_per_store)
            n = 0
            for r in recs:
                ph = phone10(r.get("phone"))
                if not ph:
                    continue
                biz = str(r.get("business_name") or "Lead").strip()[:60]
                stage = str(r.get("stage") or "new")
                if add_event("prospects", ph, f"Deal '{biz}' — stage: {stage}", title=biz):
                    n += 1
            summary["deals"] = n
        except Exception as e:
            logger.debug(f"[memory] deals sync skip: {e}")
            summary["deals"] = 0

        _write_cursor(cur)
    except Exception as e:
        logger.warning(f"[memory] sync_all failed: {e}")
        summary = {"ok": False, "error": str(e)}
    return summary


def enabled() -> bool:
    return os.environ.get("MEMORY_VAULT", "0").strip().lower() in ("1", "true", "yes")


async def sync_if_enabled() -> dict[str, Any]:
    """Scheduler hook — gated MEMORY_VAULT=1 (default OFF). sync_all thread me
    (event loop block na ho). Kabhi raise nahi."""
    if not enabled():
        return {"ok": False, "skipped": "MEMORY_VAULT off"}
    # Governance gate (fail-CLOSED, active only while MEMORY_STACK_ENABLED is on):
    # this background job grows durable per-prospect memory files, so an
    # unreadable do-not-remember authority must pause it, not silently append.
    try:
        from app.platform.memory_governance import durable_writes_allowed

        _g = durable_writes_allowed()
        if not _g["ok"]:
            return {"ok": False, "deferred": True, "code": _g["code"], "skipped": _g["reason"]}
    except Exception:
        return {
            "ok": False,
            "deferred": True,
            "code": "MEMORY_WRITE_DEFERRED_GOVERNANCE_UNAVAILABLE",
            "skipped": "governance module unavailable",
        }
    try:
        import asyncio

        result = await asyncio.to_thread(sync_all)

        # Obsidian — write vault sync summary to System/ (INERT if OBSIDIAN_SYNC unset).
        try:
            from app.platform import obsidian_sync as _obs

            lines = ["# Memory Vault Sync\n"]
            for k, v in (result or {}).items():
                if k != "ok":
                    lines.append(f"- **{k}**: {v}")
            _obs.write_system_health("memory-vault-sync", "\n".join(lines))
        except Exception:
            pass

        return result
    except Exception as e:
        logger.warning(f"[memory] sync_if_enabled failed: {e}")
        return {"ok": False, "error": str(e)}


__all__ = [
    "KINDS",
    "phone10",
    "get_memory",
    "edit_memory",
    "list_entities",
    "upsert_profile_fact",
    "add_event",
    "regen_summary",
    "context_snippet",
    "sync_all",
    "sync_if_enabled",
    "enabled",
]
