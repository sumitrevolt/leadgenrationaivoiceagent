"""OKF (Open Knowledge Format) bundle helpers — ADR-119 curated layer.

Reads repo-root ``knowledge/`` Markdown + YAML frontmatter. Not a vector DB.
Secrets never belong here; ingest refuses obvious credential patterns.

Live customer/ledger truth stays PostgreSQL. Large-scale retrieval stays Qdrant.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

# Single internal namespace for curated OKF chunks in kb_main (not customer-scoped).
OKF_NAMESPACE = "okf"
OKF_SOURCE_PREFIX = "okf:"

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
_SECRET_HINTS = re.compile(
    r"(?i)("
    r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"
    r"|password\s*[:=]\s*\S{8,}"
    r"|Bearer\s+[A-Za-z0-9\-._~+/]+=*"
    r")"
)


@dataclass(frozen=True)
class OkfDoc:
    relpath: str
    title: str
    doc_type: str
    description: str
    tags: list[str] = field(default_factory=list)
    body: str = ""
    frontmatter: dict[str, Any] = field(default_factory=dict)
    source_id: str = ""
    blocked_reason: str = ""

    @property
    def ok(self) -> bool:
        return not self.blocked_reason

    @property
    def kb_source(self) -> str:
        return f"{OKF_SOURCE_PREFIX}{self.relpath}"


def bundle_root() -> Path:
    """Repo-root ``knowledge/`` (override via OKF_BUNDLE_DIR for tests)."""
    override = (os.getenv("OKF_BUNDLE_DIR") or "").strip()
    if override:
        return Path(override).resolve()
    # app/platform/okf_bundle.py → parents[2] = repo root
    return Path(__file__).resolve().parents[2] / "knowledge"


def public_bundle_enabled() -> bool:
    """Agent-readable public /okf/ surface. Default ON (content already in git)."""
    v = (os.getenv("OKF_PUBLIC_BUNDLE") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def ingest_enabled() -> bool:
    """Qdrant ingest bridge. Default OFF — owner must arm OKF_INGEST_ENABLED=1."""
    v = (os.getenv("OKF_INGEST_ENABLED") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    text = raw or ""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text.strip()
    meta_raw, body = m.group(1), m.group(2)
    meta: dict[str, Any] = {}
    try:
        loaded = yaml.safe_load(meta_raw) or {}
        if isinstance(loaded, dict):
            meta = loaded
    except Exception as e:
        logger.debug("OKF frontmatter parse skip: %s", e)
    return meta, (body or "").strip()


def _secret_blocked(text: str) -> str:
    if _SECRET_HINTS.search(text or ""):
        return "secret_pattern"
    return ""


def load_doc(path: Path, *, root: Path | None = None) -> OkfDoc:
    root = root or bundle_root()
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    raw = path.read_text(encoding="utf-8", errors="replace")
    meta, body = parse_frontmatter(raw)
    blocked = _secret_blocked(raw)
    tags = meta.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    return OkfDoc(
        relpath=rel,
        title=str(meta.get("title") or path.stem),
        doc_type=str(meta.get("type") or "Knowledge"),
        description=str(meta.get("description") or ""),
        tags=[str(t) for t in tags],
        body=body,
        frontmatter=meta,
        source_id=str(meta.get("resource") or rel),
        blocked_reason=blocked,
    )


def list_docs(*, root: Path | None = None) -> list[OkfDoc]:
    root = (root or bundle_root()).resolve()
    if not root.is_dir():
        return []
    out: list[OkfDoc] = []
    for path in sorted(root.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            out.append(load_doc(path, root=root))
        except Exception as e:
            logger.debug("OKF skip %s: %s", path, e)
    return out


def resolve_public_path(rel: str, *, root: Path | None = None) -> Path | None:
    """Resolve a public /okf/ path under knowledge/. Refuse traversal."""
    root = (root or bundle_root()).resolve()
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not rel or rel.endswith("/"):
        rel = (rel or "") + "index.md"
    if ".." in rel.split("/") or rel.startswith("/") or ":" in rel:
        return None
    if not rel.endswith(".md"):
        # allow /okf/product/pricing-rules → pricing-rules.md
        candidate = root / f"{rel}.md"
        if candidate.is_file():
            target = candidate.resolve()
        else:
            target = (root / rel).resolve()
    else:
        target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    if not target.is_file() or target.suffix.lower() != ".md":
        return None
    return target


def route_knowledge_source(query: str) -> str:
    """Cheap query router hint (ADR-119). Returns layer name, not retrieval."""
    q = (query or "").lower()
    if any(
        t in q
        for t in (
            "invoice",
            "mrr",
            "paid",
            "ledger",
            "subscription",
            "how many",
            "kitne",
            "status of",
            "delivery %",
        )
    ):
        return "postgres"
    if any(t in q for t in ("depends on", "caller of", "blast radius", "which file", "import")):
        return "graphify"
    if any(
        t in q
        for t in (
            "pricing rule",
            "runbook",
            "onboarding",
            "deploy",
            "adr-119",
            "tenant isolation",
            "agent routing",
            "okf",
        )
    ):
        return "okf"
    return "qdrant"


def snapshot(*, root: Path | None = None) -> dict[str, Any]:
    docs = list_docs(root=root)
    blocked = [d.relpath for d in docs if not d.ok]
    return {
        "okf_version": "0.1",
        "root": str((root or bundle_root()).resolve()),
        "doc_count": len(docs),
        "blocked_count": len(blocked),
        "blocked": blocked,
        "namespace": OKF_NAMESPACE,
        "public_bundle": public_bundle_enabled(),
        "ingest_enabled": ingest_enabled(),
        "docs": [
            {
                "relpath": d.relpath,
                "title": d.title,
                "type": d.doc_type,
                "tags": d.tags,
                "source": d.kb_source,
                "ok": d.ok,
                "blocked_reason": d.blocked_reason or None,
                "chars": len(d.body),
            }
            for d in docs
        ],
    }
