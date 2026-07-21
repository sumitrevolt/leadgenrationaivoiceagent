"""Skill pack — Claude project skills ko VPS agents ke liye runtime-available banata hai.

Sources:
  1. `.claude/skills/*/SKILL.md` (repo-committed, 35 skills — image me baked)
  2. `data/skills_extra/*.md` (agent/admin-authored, bind-mounted = runtime-live)

Public API (sab never-raise):
    list_skills() -> [{name, description, source, chars}]
    load(name) -> {name, description, text} | None
    find(query, k=2) -> top-k skills (keyword-overlap score)
    snippet_for(topic, max_chars=1200) -> prompt-injectable text ("" agar kuch nahi)
    author(name, text) -> Tier-1 safe write into data/skills_extra/ (validated)
    ingest_to_kb() -> Qdrant/KB namespace "skills" me chunks (semantic recall)
    enabled() -> SKILL_PACK flag (wiring gates; manual API flag-independent)

Design: mtime-cached load, pure-python scoring (zero dep/latency), markdown-only,
path-escape blocked. Flag OFF = prompt-injection wiring inert (zero behaviour change).
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_SKILLS_DIR = os.path.join(".claude", "skills")
# Canonical skill registry consolidated to .claude/skills (Phase 12 skill-tree
# de-duplication). The former secondary agents skill mirror was a byte-identical
# duplicate plus 23 extra skills that are now merged here; it no longer exists.
_EXTRA_DIR = os.path.join("data", "skills_extra")
_MAX_AUTHOR_BYTES = 16 * 1024  # Tier-1 size cap
_CACHE_TTL_S = 300

_cache: dict[str, Any] = {"at": 0.0, "skills": []}


def enabled() -> bool:
    return (os.getenv("SKILL_PACK") or "").strip().lower() in ("1", "true", "yes")


def _safe_name(name: str) -> str:
    """Slug-only — path escape / weird chars block."""
    return re.sub(r"[^a-z0-9_-]", "", (name or "").strip().lower())[:60]


def _parse_skill(path: str, source: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
        if not text.strip():
            return None
        name = (
            os.path.basename(os.path.dirname(path))
            if source in ("project", "agents")
            else os.path.splitext(os.path.basename(path))[0]
        )
        desc = ""
        m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        if m:
            desc = m.group(1).strip()[:300]
        else:
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "---", "name:")):
                    desc = line[:300]
                    break
        return {
            "name": name,
            "description": desc,
            "text": text,
            "source": source,
            "chars": len(text),
        }
    except Exception:
        return None


def _load_all() -> list[dict[str, Any]]:
    now = time.time()
    if _cache["skills"] and now - _cache["at"] < _CACHE_TTL_S:
        return _cache["skills"]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add_skill(s: dict[str, Any] | None) -> None:
        if not s:
            return
        name = str(s.get("name") or "")
        if not name or name in seen:
            return
        seen.add(name)
        out.append(s)

    try:
        if os.path.isdir(_SKILLS_DIR):
            for d in sorted(os.listdir(_SKILLS_DIR)):
                p = os.path.join(_SKILLS_DIR, d, "SKILL.md")
                if os.path.isfile(p):
                    _add_skill(_parse_skill(p, "project"))
        if os.path.isdir(_EXTRA_DIR):
            for fn in sorted(os.listdir(_EXTRA_DIR)):
                if fn.endswith(".md"):
                    _add_skill(_parse_skill(os.path.join(_EXTRA_DIR, fn), "extra"))
    except Exception as e:
        logger.warning(f"skill_pack load failed: {e}")
    _cache["skills"] = out
    _cache["at"] = now
    return out


def list_skills() -> list[dict[str, Any]]:
    return [{k: s[k] for k in ("name", "description", "source", "chars")} for s in _load_all()]


def load(name: str) -> dict[str, Any] | None:
    n = _safe_name(name)
    for s in _load_all():
        if s["name"] == n:
            return {"name": s["name"], "description": s["description"], "text": s["text"]}
    return None


_WORD = re.compile(r"[a-z0-9]{3,}")


def find(query: str, k: int = 2) -> list[dict[str, Any]]:
    """Keyword-overlap scoring: name match heavy, description medium, body light."""
    q = set(_WORD.findall((query or "").lower()))
    if not q:
        return []
    scored = []
    for s in _load_all():
        nw = set(_WORD.findall(s["name"].replace("-", " ")))
        dw = set(_WORD.findall(s["description"].lower()))
        bw = set(_WORD.findall(s["text"][:4000].lower()))
        score = 3.0 * len(q & nw) + 2.0 * len(q & dw) + 0.5 * len(q & bw)
        if score > 0:
            scored.append((score, s))
    scored.sort(key=lambda t: -t[0])
    return [
        {
            "name": s["name"],
            "description": s["description"],
            "score": round(sc, 1),
            "source": s["source"],
        }
        for sc, s in scored[: max(1, k)]
    ]


def snippet_for(topic: str, max_chars: int = 1200) -> str:
    """Top-match skill ka prompt-injectable excerpt. Kuch na mile to ""."""
    try:
        hits = find(topic, k=1)
        if not hits:
            return ""
        s = load(hits[0]["name"])
        if not s:
            return ""
        body = re.sub(r"^---.*?---\s*", "", s["text"], count=1, flags=re.DOTALL).strip()
        return f"[skill: {s['name']}] {s['description']}\n{body[: max(200, max_chars)]}"
    except Exception:
        return ""


def author(name: str, text: str) -> dict[str, Any]:
    """Tier-1 SAFE write — sirf data/skills_extra/*.md. Validated, capped, never-raise."""
    try:
        n = _safe_name(name)
        if not n:
            return {"ok": False, "error": "invalid name (a-z 0-9 _ - only)"}
        body = (text or "").strip()
        if not body or len(body.encode("utf-8")) > _MAX_AUTHOR_BYTES:
            return {"ok": False, "error": f"text empty ya >{_MAX_AUTHOR_BYTES // 1024}KB"}
        if "<script" in body.lower():
            return {"ok": False, "error": "script tags not allowed"}
        os.makedirs(_EXTRA_DIR, exist_ok=True)
        path = os.path.join(_EXTRA_DIR, f"{n}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        _cache["at"] = 0.0  # bust cache
        logger.info(f"skill_pack: authored extra skill '{n}' ({len(body)} chars)")
        return {"ok": True, "name": n, "path": path, "chars": len(body)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def ingest_to_kb() -> dict[str, Any]:
    """Saari skills KB namespace 'skills' me (Qdrant semantic; fallback keyword index)."""
    try:
        from app.voice_agent.knowledge_base import KnowledgeBase

        kb = KnowledgeBase()
        skills = _load_all()
        docs = [
            {
                "text": f"SKILL {s['name']}: {s['description']}\n\n{s['text'][:8000]}",
                "source": f"skill:{s['name']}",
            }
            for s in skills
        ]
        added = kb.add_documents(docs, namespace="skills")
        return {"ok": True, "skills": len(skills), "chunks": added, "backend": kb.backend("skills")}
    except Exception as e:
        logger.warning(f"skill_pack ingest failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = ["enabled", "list_skills", "load", "find", "snippet_for", "author", "ingest_to_kb"]
