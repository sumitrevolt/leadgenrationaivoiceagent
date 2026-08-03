"""Workforce Memory Hub — per-STAFF-agent layered memory (TencentDB-inspired, native).

LEARNED (NOT vendored) from https://github.com/TencentCloud/TencentDB-Agent-Memory:

  1. Four reusable **assets**: chat · skill · wiki · code
  2. Long-term **pyramid**: L0 conversation → L1 atom → L2 scenario → L3 persona
  3. **Progressive disclosure**: inject structure first; drill to evidence via node_id
  4. **Context offload**: bulky tool/raw text → refs/{node_id}.md, keep index in JSONL
  5. **Fixed binding + ACL**: each of the 31 STAFF agents may only use allowed assets

WHY NOT vendor the whole repo:
  - Separate Node/OpenClaw plugin + MemoryPanel/Proxy deploy (not our FastAPI path)
  - Optional Tencent Cloud Vector DB — conflicts with free-stack + existing Qdrant
  - We already have equivalent lanes (agent_memory, skill_library, memory_vault,
    trajectory, Graphify) — need a HUB, not a second memory product

Maps:
  chat  → this store + voice agent_memory (lead facts) + coordinator Reflexion
  skill → this store + skill_library lessons
  wiki  → this store + memory_vault markdown
  code  → this store + Graphify (dev-only; never customer data)

INVARIANTS: flag-gated (`WORKFORCE_MEMORY`, OFF default) · never-raise ·
tenant/agent scoped · no paid AI · no prompt auto-mutation · DPDP purge API.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --- asset + layer vocabulary (TencentDB taxonomy) ---------------------------
ASSET_CHAT = "chat"
ASSET_SKILL = "skill"
ASSET_WIKI = "wiki"
ASSET_CODE = "code"
ASSETS = frozenset({ASSET_CHAT, ASSET_SKILL, ASSET_WIKI, ASSET_CODE})

LAYER_L0 = "l0_conversation"
LAYER_L1 = "l1_atom"
LAYER_L2 = "l2_scenario"
LAYER_L3 = "l3_persona"
LAYERS = frozenset({LAYER_L0, LAYER_L1, LAYER_L2, LAYER_L3})

# Progressive recall prefers structure over raw logs.
_LAYER_PRIORITY = (LAYER_L3, LAYER_L2, LAYER_L1, LAYER_L0)

# Fixed bindings — which assets each STAFF agent may write/read by default.
# Unknown agents get chat+skill only (fail-closed on wiki/code write).
_DEFAULT_BINDINGS: dict[str, frozenset[str]] = {
    "manager": frozenset(ASSETS),
    "guru": frozenset({ASSET_CHAT, ASSET_SKILL, ASSET_WIKI}),
    "vidya": frozenset({ASSET_CHAT, ASSET_SKILL, ASSET_WIKI}),
    "lekha": frozenset({ASSET_CHAT, ASSET_SKILL, ASSET_WIKI}),
    "dev": frozenset({ASSET_CHAT, ASSET_SKILL, ASSET_CODE}),
    "hermes": frozenset({ASSET_CHAT, ASSET_SKILL, ASSET_CODE}),
    "arjun": frozenset({ASSET_CHAT, ASSET_SKILL, ASSET_CODE}),
    "swara": frozenset({ASSET_CHAT, ASSET_SKILL}),
}

_AGENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_MAX_ENTRY_CHARS = 800
_MAX_OFFLOAD_CHARS = 80_000
_MAX_ENTRIES_PER_AGENT = 3000
_VIS_PRIVATE = "private"
_VIS_TEAM = "team"
_VISIBILITIES = frozenset({_VIS_PRIVATE, _VIS_TEAM})
_STATS: dict[str, int] = {
    "stored": 0,
    "recalled": 0,
    "offloaded": 0,
    "purged": 0,
    "denied": 0,
    "disabled": 0,
    "error": 0,
    "deduped": 0,
    "recall_timeout": 0,
    "pruned": 0,
    "equipped": 0,
    "injected": 0,
}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except Exception:
        return default


def _max_chars_per() -> int:
    return max(80, min(_env_int("WORKFORCE_MEMORY_MAX_CHARS_PER", 280), 2000))


def _max_total_chars() -> int:
    return max(200, min(_env_int("WORKFORCE_MEMORY_MAX_TOTAL", 1200), 8000))


def _recall_timeout_ms() -> int:
    return max(10, min(_env_int("WORKFORCE_MEMORY_RECALL_TIMEOUT_MS", 50), 2000))


def _l0_l1_retention_days() -> int:
    # 0 = keep forever (Tencent capture.l0l1RetentionDays semantics)
    return max(0, min(_env_int("WORKFORCE_MEMORY_L0_L1_DAYS", 90), 3650))


def _content_hash(agent_id: str, asset: str, layer: str, content: str) -> str:
    norm = " ".join((content or "").strip().lower().split())
    raw = f"{agent_id}|{asset}|{layer}|{norm}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def is_enabled() -> bool:
    return (os.getenv("WORKFORCE_MEMORY", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# Scanner-visible store root (runtime-data allowlist matches this symbol).
_ROOT_DEFAULT = os.path.join("data", "workforce_memory")


def _root() -> str:
    override = (os.getenv("WORKFORCE_MEMORY_DIR") or "").strip()
    if override:
        return override
    return _ROOT_DEFAULT


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_agent(agent_id: str) -> str | None:
    aid = (agent_id or "").strip().lower()
    if not aid or not _AGENT_RE.match(aid):
        return None
    return aid


def _agent_dir(agent_id: str) -> str:
    return os.path.join(_root(), agent_id)


def _entries_path(agent_id: str) -> str:
    return os.path.join(_agent_dir(agent_id), "entries.jsonl")


def _refs_dir(agent_id: str) -> str:
    return os.path.join(_agent_dir(agent_id), "refs")


def _persona_path(agent_id: str) -> str:
    return os.path.join(_agent_dir(agent_id), "persona.md")


def _shared_dir() -> str:
    return os.path.join(_root(), "_shared")


def _equipments_path() -> str:
    return os.path.join(_root(), "equipments.json")


def known_staff_ids() -> list[str]:
    try:
        from app.platform.team import STAFF

        return sorted(STAFF.keys())
    except Exception:
        return sorted(_DEFAULT_BINDINGS.keys())


def agent_bindings(agent_id: str) -> list[str]:
    """Fixed asset ACL for an agent (TencentDB 'Fixed Binding' pattern)."""
    aid = _safe_agent(agent_id)
    if not aid:
        return []
    bound = _DEFAULT_BINDINGS.get(aid)
    if bound is None:
        # Unknown / other STAFF → chat+skill only
        bound = frozenset({ASSET_CHAT, ASSET_SKILL})
    return sorted(bound)


def _allowed(agent_id: str, asset: str) -> bool:
    return (asset or "").strip().lower() in set(agent_bindings(agent_id))


def _append_entry(agent_id: str, rec: dict[str, Any]) -> bool:
    try:
        agent_dir = _agent_dir(agent_id)
        os.makedirs(agent_dir, exist_ok=True)
        entries_path = _entries_path(agent_id)
        with open(entries_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        # Soft trim — keep last N lines if file grows huge
        try:
            if os.path.getsize(entries_path) > 4_000_000:
                rows = _read_entries(agent_id, limit=_MAX_ENTRIES_PER_AGENT + 200)
                keep = rows[:_MAX_ENTRIES_PER_AGENT]
                with open(entries_path, "w", encoding="utf-8") as f:
                    for r in reversed(keep):
                        f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass
        return True
    except Exception as e:
        logger.debug("[workforce_memory] append skipped: %s", e)
        return False


def _read_entries(agent_id: str, limit: int = 200) -> list[dict[str, Any]]:
    """Latest-first."""
    out: list[dict[str, Any]] = []
    entries_path = _entries_path(agent_id)
    try:
        if not os.path.exists(entries_path):
            return []
        with open(entries_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        return []
    return out[-limit:][::-1]


def offload_ref(agent_id: str, text: str, *, label: str = "ref") -> str | None:
    """Write bulky evidence to refs/{node_id}.md; return node_id (or None)."""
    if not is_enabled():
        _STATS["disabled"] = _STATS.get("disabled", 0) + 1
        return None
    aid = _safe_agent(agent_id)
    body = (text or "").strip()
    if not aid or not body:
        return None
    try:
        node_id = uuid.uuid4().hex[:12]
        rd = _refs_dir(aid)
        os.makedirs(rd, exist_ok=True)
        ref_path = os.path.join(rd, f"{node_id}.md")
        header = f"# {label[:80]}\n\nagent: {aid}\nat: {_now()}\nnode_id: {node_id}\n\n"
        with open(ref_path, "w", encoding="utf-8") as f:
            f.write(header + body[:_MAX_OFFLOAD_CHARS])
        _STATS["offloaded"] = _STATS.get("offloaded", 0) + 1
        return node_id
    except Exception as e:
        _STATS["error"] = _STATS.get("error", 0) + 1
        logger.debug("[workforce_memory] offload skipped: %s", e)
        return None


def drilldown(agent_id: str, node_id: str) -> str | None:
    """Recover offloaded evidence by node_id (TencentDB drill-down)."""
    aid = _safe_agent(agent_id)
    nid = re.sub(r"[^a-f0-9]", "", (node_id or "").lower())[:32]
    if not aid or not nid:
        return None
    try:
        rd = _refs_dir(aid)
        ref_path = os.path.join(rd, f"{nid}.md")
        if not os.path.exists(ref_path):
            return None
        with open(ref_path, encoding="utf-8") as f:
            return f.read()[:_MAX_OFFLOAD_CHARS]
    except Exception:
        return None


def remember(
    agent_id: str,
    content: str,
    *,
    layer: str = LAYER_L1,
    asset: str = ASSET_CHAT,
    topic: str = "",
    meta: dict[str, Any] | None = None,
    offload: str | None = None,
    score: float | None = None,
    visibility: str = _VIS_PRIVATE,
    parent_id: str | None = None,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Append a layered memory entry for a STAFF agent. Never raises."""
    if not is_enabled():
        _STATS["disabled"] = _STATS.get("disabled", 0) + 1
        return {"ok": False, "error": "disabled"}
    try:
        aid = _safe_agent(agent_id)
        body = (content or "").strip()
        if not aid or not body:
            return {"ok": False, "error": "agent_id and content required"}
        ly = (layer or LAYER_L1).strip().lower()
        asst = (asset or ASSET_CHAT).strip().lower()
        vis = (visibility or _VIS_PRIVATE).strip().lower()
        if ly not in LAYERS:
            return {"ok": False, "error": f"layer must be one of {sorted(LAYERS)}"}
        if asst not in ASSETS:
            return {"ok": False, "error": f"asset must be one of {sorted(ASSETS)}"}
        if vis not in _VISIBILITIES:
            return {"ok": False, "error": "visibility must be private|team"}
        # Chat/L0 stay private — no team leak of conversational raw (Tencent default).
        if asst == ASSET_CHAT or ly == LAYER_L0:
            vis = _VIS_PRIVATE
        if vis == _VIS_TEAM and asst not in {ASSET_SKILL, ASSET_WIKI}:
            return {"ok": False, "error": "team_visibility_only_skill_or_wiki"}
        if not _allowed(aid, asst):
            _STATS["denied"] = _STATS.get("denied", 0) + 1
            return {
                "ok": False,
                "error": "asset_denied",
                "agent_id": aid,
                "asset": asst,
                "allowed": agent_bindings(aid),
            }

        ch = _content_hash(aid, asst, ly, body)
        for prev in _read_entries(aid, limit=80):
            if prev.get("content_hash") == ch:
                _STATS["deduped"] = _STATS.get("deduped", 0) + 1
                return {"ok": True, "deduped": True, "entry": prev}

        node_id: str | None = None
        if offload and str(offload).strip():
            node_id = offload_ref(aid, str(offload), label=(topic or "offload")[:80])

        # Auto-offload oversized content — keep short index in the entry.
        index_body = body[:_MAX_ENTRY_CHARS]
        if len(body) > _MAX_ENTRY_CHARS and not node_id:
            node_id = offload_ref(aid, body, label=(topic or "auto_offload")[:80])

        refs = [str(x)[:32] for x in (source_refs or []) if x][:8]
        if node_id and node_id not in refs:
            refs.append(node_id)

        rec: dict[str, Any] = {
            "id": uuid.uuid4().hex[:16],
            "agent_id": aid,
            "layer": ly,
            "asset": asst,
            "topic": (topic or "")[:120],
            "content": index_body,
            "node_id": node_id,
            "content_hash": ch,
            "visibility": vis,
            "parent_id": (parent_id or "")[:32] or None,
            "source_refs": refs,
            "score": score,
            "meta": {k: str(v)[:200] for k, v in (meta or {}).items()} if meta else {},
            "at": _now(),
            "source": "workforce_memory",
        }
        if not _append_entry(aid, rec):
            _STATS["error"] = _STATS.get("error", 0) + 1
            return {"ok": False, "error": "write_failed"}

        if vis == _VIS_TEAM:
            _mirror_shared(rec)

        if ly == LAYER_L3:
            _maybe_update_persona(aid, index_body, topic)

        _STATS["stored"] = _STATS.get("stored", 0) + 1
        return {"ok": True, "entry": rec}
    except Exception as e:
        _STATS["error"] = _STATS.get("error", 0) + 1
        logger.debug("[workforce_memory] remember skipped: %s", e)
        return {"ok": False, "error": type(e).__name__}


def _mirror_shared(rec: dict[str, Any]) -> None:
    """Copy team-visible skill/wiki into _shared/ for equip/loadout."""
    try:
        os.makedirs(_shared_dir(), exist_ok=True)
        shared_path = os.path.join(_shared_dir(), "entries.jsonl")
        with open(shared_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _read_shared(limit: int = 200) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    shared_path = os.path.join(_shared_dir(), "entries.jsonl")
    try:
        if not os.path.exists(shared_path):
            return []
        with open(shared_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        return []
    return out[-limit:][::-1]


def _load_equipments() -> dict[str, list[str]]:
    """agent_id -> list of shared entry ids equipped to them."""
    try:
        equip_path = _equipments_path()
        if not os.path.exists(equip_path):
            return {}
        with open(equip_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {
                str(k): [str(x) for x in (v or []) if x][:50]
                for k, v in data.items()
                if isinstance(v, list)
            }
    except Exception:
        pass
    return {}


def _save_equipments(data: dict[str, list[str]]) -> bool:
    try:
        os.makedirs(_root(), exist_ok=True)
        equip_path = _equipments_path()
        with open(equip_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def equip(entry_id: str, to_agent: str) -> dict[str, Any]:
    """Admin loadout: bind a team-shared entry to a STAFF agent (fail-closed)."""
    if not is_enabled():
        return {"ok": False, "error": "disabled"}
    try:
        aid = _safe_agent(to_agent)
        eid = (entry_id or "").strip()[:32]
        if not aid or not eid:
            return {"ok": False, "error": "entry_id and to_agent required"}
        shared = {r.get("id"): r for r in _read_shared(limit=500)}
        rec = shared.get(eid)
        if not rec:
            return {"ok": False, "error": "shared_entry_not_found"}
        if str(rec.get("visibility")) != _VIS_TEAM:
            return {"ok": False, "error": "not_team_visible"}
        if not _allowed(aid, str(rec.get("asset", ""))):
            _STATS["denied"] = _STATS.get("denied", 0) + 1
            return {"ok": False, "error": "asset_denied_for_target", "allowed": agent_bindings(aid)}
        eq = _load_equipments()
        cur = list(eq.get(aid) or [])
        if eid not in cur:
            cur.append(eid)
        eq[aid] = cur[-50:]
        if not _save_equipments(eq):
            return {"ok": False, "error": "write_failed"}
        _STATS["equipped"] = _STATS.get("equipped", 0) + 1
        return {"ok": True, "agent_id": aid, "entry_id": eid, "equipped_count": len(eq[aid])}
    except Exception as e:
        _STATS["error"] = _STATS.get("error", 0) + 1
        return {"ok": False, "error": type(e).__name__}


def list_equipments(agent_id: str | None = None) -> dict[str, Any]:
    eq = _load_equipments()
    if agent_id:
        aid = _safe_agent(agent_id)
        return {"agent_id": aid, "entry_ids": eq.get(aid or "", [])}
    return {"equipments": eq}


def _maybe_update_persona(agent_id: str, content: str, topic: str) -> None:
    """Human-readable L3 persona.md (upper layer = structure, inspectable)."""
    try:
        persona_path = _persona_path(agent_id)
        os.makedirs(os.path.dirname(persona_path), exist_ok=True)
        stamp = _now()
        block = f"\n## {topic or 'insight'} ({stamp})\n\n{content}\n"
        prev = ""
        if os.path.exists(persona_path):
            with open(persona_path, encoding="utf-8") as f:
                prev = f.read()
        # Keep persona file bounded
        merged = (prev + block)[-12_000:]
        if not merged.startswith("#"):
            merged = f"# Persona — {agent_id}\n" + merged
        with open(persona_path, "w", encoding="utf-8") as f:
            f.write(merged)
    except Exception:
        pass


def _score_overlap(query: str, hay: str) -> int:
    toks = {w for w in (query or "").lower().split() if len(w) > 2}
    if not toks:
        return 1  # no query → chronological ok
    h = (hay or "").lower()
    return sum(1 for w in toks if w in h)


def recall(
    agent_id: str,
    query: str = "",
    *,
    layers: list[str] | None = None,
    assets: list[str] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Keyword-lite recall with progressive layer preference. Never raises."""
    if not is_enabled():
        _STATS["disabled"] = _STATS.get("disabled", 0) + 1
        return []
    t0 = time.monotonic()
    try:
        aid = _safe_agent(agent_id)
        if not aid:
            return []
        allow_layers = {x.lower() for x in (layers or list(LAYERS)) if x}
        allow_assets = {x.lower() for x in (assets or list(ASSETS)) if x}
        rows = list(_read_entries(aid, limit=400))
        # Equipped team-shared skill/wiki (Tencent Agent Loadout)
        try:
            eq_ids = set(_load_equipments().get(aid) or [])
            if eq_ids:
                for r in _read_shared(limit=300):
                    if r.get("id") in eq_ids:
                        rows.append(r)
        except Exception:
            pass
        deadline = t0 + (_recall_timeout_ms() / 1000.0)
        scored: list[tuple[int, int, dict[str, Any]]] = []
        for i, r in enumerate(rows):
            if time.monotonic() > deadline:
                _STATS["recall_timeout"] = _STATS.get("recall_timeout", 0) + 1
                break
            if str(r.get("layer", "")).lower() not in allow_layers:
                continue
            if str(r.get("asset", "")).lower() not in allow_assets:
                continue
            if not _allowed(aid, str(r.get("asset", ""))):
                continue
            hay = f"{r.get('topic', '')} {r.get('content', '')}"
            ov = _score_overlap(query, hay)
            if ov <= 0 and query.strip():
                continue
            try:
                layer_bonus = 10 - _LAYER_PRIORITY.index(str(r.get("layer")))
            except ValueError:
                layer_bonus = 0
            scored.append((ov + layer_bonus, -i, r))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        out = [r for _, __, r in scored[: max(1, min(int(limit), 50))]]
        if out:
            _STATS["recalled"] = _STATS.get("recalled", 0) + 1
        return out
    except Exception as e:
        _STATS["error"] = _STATS.get("error", 0) + 1
        logger.debug("[workforce_memory] recall skipped: %s", e)
        return []


def recall_brief(agent_id: str, query: str = "", *, max_chars: int | None = None) -> str:
    """Compact progressive-disclosure brief for prompt injection (budgeted)."""
    if not is_enabled():
        return ""
    try:
        budget = int(max_chars) if max_chars is not None else _max_total_chars()
        per = _max_chars_per()
        rows = recall(agent_id, query, limit=6)
        if not rows:
            aid = _safe_agent(agent_id)
            persona_path = _persona_path(aid) if aid else ""
            if persona_path and os.path.exists(persona_path):
                with open(persona_path, encoding="utf-8") as f:
                    return f.read()[:budget]
            return ""
        lines: list[str] = []
        used = 0
        for r in rows:
            layer = r.get("layer", "?")
            asset = r.get("asset", "?")
            topic = r.get("topic") or ""
            content = (r.get("content") or "").strip()[:per]
            nid = r.get("node_id")
            prefix = f"[{layer}/{asset}]"
            if topic:
                prefix += f" {topic}:"
            line = f"- {prefix} {content}"
            if nid:
                line += f" (node_id={nid})"
            if used + len(line) + 1 > budget:
                break
            lines.append(line)
            used += len(line) + 1
        return "\n".join(lines)
    except Exception:
        return ""


def composite_brief(
    agent_id: str,
    query: str = "",
    *,
    max_chars: int | None = None,
    include_external: bool = True,
) -> str:
    """Hub brief = workforce entries + skill lessons + vault snippet (fail-open)."""
    budget = int(max_chars) if max_chars is not None else _max_total_chars()
    parts: list[str] = []
    core = recall_brief(agent_id, query, max_chars=max(200, budget // 2))
    if core:
        parts.append("## Workforce memory\n" + core)

    if include_external and is_enabled():
        try:
            from app.platform import skill_library

            snip = skill_library.lessons_snippet(query or agent_id, k=2)
            if snip.strip():
                parts.append("## Skill lessons\n" + snip.strip())
        except Exception:
            pass
        try:
            # memory_vault is entity-scoped (phone / client_id) — never pass free text as key
            q = (query or "").strip()
            digits = re.sub(r"\D", "", q)
            phone = digits if len(digits) >= 10 else None
            cid = (
                q
                if (not phone and 8 <= len(q) <= 40 and re.match(r"^[A-Za-z0-9_-]+$", q))
                else None
            )
            if phone or cid:
                from app.platform import memory_vault

                if memory_vault.enabled():
                    vs = memory_vault.context_snippet(phone=phone, client_id=cid, max_chars=400)
                    if vs and vs.strip():
                        parts.append("## Vault\n" + vs.strip()[:400])
        except Exception:
            pass

    out = "\n\n".join(parts).strip()
    return out[:budget]


def inject_for_runtime(agent_id: str, action: str = "") -> str:
    """Bounded labeled brief for agent_runtime pilots. Never raises; "" when off/timeout."""
    if not is_enabled():
        return ""
    try:
        # Prefer action overlap; fall back to recent progressive brief (empty query).
        brief = composite_brief(agent_id, action or "", max_chars=_max_total_chars())
        if not brief.strip():
            brief = composite_brief(agent_id, "", max_chars=_max_total_chars())
        if brief.strip():
            _STATS["injected"] = _STATS.get("injected", 0) + 1
            return brief.strip()
        return ""
    except Exception:
        return ""


def remember_runtime_outcome(
    agent_id: str,
    action: str,
    *,
    ok: bool,
    detail: str = "",
) -> dict[str, Any]:
    """L0 outcome crumb after a runtime run (fail-open, private chat)."""
    status = "ok" if ok else "fail"
    body = f"runtime {action}: {status}. {(detail or '')[:400]}".strip()
    return remember(
        agent_id,
        body,
        layer=LAYER_L0,
        asset=ASSET_CHAT,
        topic=f"runtime:{action}"[:120],
        meta={"source": "agent_runtime"},
        visibility=_VIS_PRIVATE,
    )


def prune_expired(*, dry_run: bool = True) -> dict[str, Any]:
    """Drop L0/L1 rows older than WORKFORCE_MEMORY_L0_L1_DAYS. Keeps L2/L3. Never raises."""
    if not is_enabled():
        return {"ok": False, "error": "disabled", "pruned": 0}
    days = _l0_l1_retention_days()
    if days <= 0:
        return {"ok": True, "skipped": "retention_disabled", "pruned": 0, "dry_run": dry_run}
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        root = _root()
        if not os.path.isdir(root):
            return {"ok": True, "pruned": 0, "dry_run": dry_run}
        pruned = 0
        touched: list[str] = []
        for name in os.listdir(root):
            if name.startswith("_") or name == "equipments.json":
                continue
            prune_path = os.path.join(root, name, "entries.jsonl")
            if not os.path.isfile(prune_path):
                continue
            keep: list[dict[str, Any]] = []
            removed = 0
            for r in reversed(_read_entries(name, limit=_MAX_ENTRIES_PER_AGENT)):
                ly = str(r.get("layer", ""))
                if ly in {LAYER_L0, LAYER_L1}:
                    try:
                        at = datetime.fromisoformat(str(r.get("at", "")).replace("Z", "+00:00"))
                        if at.tzinfo is None:
                            at = at.replace(tzinfo=timezone.utc)
                        if at < cutoff:
                            removed += 1
                            continue
                    except Exception:
                        pass
                keep.append(r)
            if removed and not dry_run:
                with open(prune_path, "w", encoding="utf-8") as f:
                    for r in reversed(keep):
                        f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            if removed:
                pruned += removed
                touched.append(name)
        if not dry_run:
            _STATS["pruned"] = _STATS.get("pruned", 0) + pruned
        return {
            "ok": True,
            "pruned": pruned,
            "agents": touched,
            "dry_run": dry_run,
            "retention_days": days,
        }
    except Exception as e:
        _STATS["error"] = _STATS.get("error", 0) + 1
        return {"ok": False, "error": type(e).__name__, "pruned": 0, "dry_run": dry_run}


def canvas_mermaid(agent_id: str, *, limit: int = 10) -> str:
    """Symbolic short-term canvas — recent L2 scenarios as Mermaid (token-light)."""
    if not is_enabled():
        return ""
    rows = recall(agent_id, layers=[LAYER_L2], limit=limit)
    if not rows:
        rows = recall(agent_id, limit=limit)
    if not rows:
        return ""
    lines = ["graph LR"]
    for i, r in enumerate(rows):
        nid = r.get("node_id") or r.get("id") or f"n{i}"
        label = (r.get("topic") or r.get("content") or "step")[:40].replace('"', "'")
        safe = re.sub(r"[^A-Za-z0-9_]", "_", str(nid))[:20]
        lines.append(f'  {safe}["{label}"]')
        if i > 0:
            prev_raw = rows[i - 1].get("node_id") or rows[i - 1].get("id") or f"n{i-1}"
            prev = re.sub(r"[^A-Za-z0-9_]", "_", str(prev_raw))[:20]
            lines.append(f"  {prev} --> {safe}")
    return "\n".join(lines)


def list_entries(agent_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    aid = _safe_agent(agent_id)
    if not aid:
        return []
    return _read_entries(aid, limit=max(1, min(int(limit), 500)))


def purge_agent(agent_id: str) -> dict[str, Any]:
    """DPDP / ops erase for one agent's workforce memory files."""
    aid = _safe_agent(agent_id)
    if not aid:
        return {"ok": False, "error": "bad_agent", "purged": 0}
    purged = 0
    try:
        import shutil

        agent_dir = _agent_dir(aid)
        if os.path.isdir(agent_dir):
            # Count entries before wipe
            purged = len(_read_entries(aid, limit=_MAX_ENTRIES_PER_AGENT))
            shutil.rmtree(agent_dir, ignore_errors=True)
        _STATS["purged"] = _STATS.get("purged", 0) + purged
        return {"ok": True, "agent_id": aid, "purged": purged}
    except Exception as e:
        _STATS["error"] = _STATS.get("error", 0) + 1
        return {"ok": False, "error": type(e).__name__, "purged": purged}


def hub_snapshot(*, max_agents: int = 8) -> dict[str, Any]:
    """Compact hub status for OpenClaw / admin (no PII dump)."""
    if not is_enabled():
        return {"enabled": False, "agents_with_memory": 0, "counters": stats()}
    try:
        root = _root()
        agents_present: list[str] = []
        if os.path.isdir(root):
            for name in sorted(os.listdir(root))[:80]:
                if os.path.isfile(os.path.join(root, name, "entries.jsonl")):
                    agents_present.append(name)
        briefs = []
        for aid in agents_present[:max_agents]:
            n = len(_read_entries(aid, limit=5))
            briefs.append(
                {
                    "agent_id": aid,
                    "recent_sample": n,
                    "bindings": agent_bindings(aid),
                }
            )
        return {
            "enabled": True,
            "agents_with_memory": len(agents_present),
            "sample": briefs,
            "taxonomy": {
                "assets": sorted(ASSETS),
                "layers": list(_LAYER_PRIORITY),
            },
            "counters": stats(),
            "inspired_by": "TencentDB-Agent-Memory (patterns only — not vendored)",
        }
    except Exception as e:
        return {"enabled": True, "error": type(e).__name__, "counters": stats()}


def stats() -> dict[str, int]:
    return dict(_STATS)


def remember_lesson_bridge(
    topic: str,
    lesson: str,
    *,
    agent: str = "",
    source: str = "skill_library",
) -> dict[str, Any]:
    """Dual-write hook from skill_library → L2 skill scenario."""
    aid = _safe_agent(agent) or "guru"
    return remember(
        aid,
        lesson,
        layer=LAYER_L2,
        asset=ASSET_SKILL,
        topic=topic,
        meta={"source": source},
    )


def remember_reflection_bridge(
    topic: str,
    reflection: str,
    *,
    score: float | None = None,
    agent: str = "manager",
) -> dict[str, Any]:
    """Dual-write hook from coordinator Reflexion → L2 chat scenario."""
    return remember(
        agent or "manager",
        reflection,
        layer=LAYER_L2,
        asset=ASSET_CHAT,
        topic=topic,
        score=score,
        meta={"source": "coordinator_reflexion"},
    )


__all__ = [
    "ASSET_CHAT",
    "ASSET_SKILL",
    "ASSET_WIKI",
    "ASSET_CODE",
    "LAYER_L0",
    "LAYER_L1",
    "LAYER_L2",
    "LAYER_L3",
    "is_enabled",
    "known_staff_ids",
    "agent_bindings",
    "remember",
    "recall",
    "recall_brief",
    "composite_brief",
    "inject_for_runtime",
    "remember_runtime_outcome",
    "canvas_mermaid",
    "offload_ref",
    "drilldown",
    "list_entries",
    "purge_agent",
    "prune_expired",
    "equip",
    "list_equipments",
    "hub_snapshot",
    "stats",
    "remember_lesson_bridge",
    "remember_reflection_bridge",
]
