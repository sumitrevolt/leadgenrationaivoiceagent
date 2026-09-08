"""Public OKF bundle surface — agent-readable Markdown at /okf/ (ADR-119 + ai-seo).

Serves curated ``knowledge/*.md`` only. Path-traversal refuse. Secret-pattern
docs return 404 (never leak). Gated by OKF_PUBLIC_BUNDLE (default ON).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.platform import okf_bundle

router = APIRouter(tags=["OKF Public"])


def _ensure_public() -> None:
    if not okf_bundle.public_bundle_enabled():
        raise HTTPException(status_code=404, detail="okf_public_disabled")


@router.get("/okf", include_in_schema=False)
@router.get("/okf/", include_in_schema=False)
async def okf_index() -> PlainTextResponse:
    _ensure_public()
    path = okf_bundle.resolve_public_path("index.md")
    if path is None:
        raise HTTPException(status_code=404, detail="okf_index_missing")
    raw = path.read_text(encoding="utf-8", errors="replace")
    if okf_bundle._secret_blocked(raw):  # noqa: SLF001 — shared guard
        raise HTTPException(status_code=404, detail="okf_blocked")
    return PlainTextResponse(raw, media_type="text/markdown; charset=utf-8")


@router.get("/okf/{doc_path:path}", include_in_schema=False)
async def okf_doc(doc_path: str) -> PlainTextResponse:
    _ensure_public()
    path = okf_bundle.resolve_public_path(doc_path)
    if path is None:
        raise HTTPException(status_code=404, detail="okf_not_found")
    raw = path.read_text(encoding="utf-8", errors="replace")
    if okf_bundle._secret_blocked(raw):  # noqa: SLF001
        raise HTTPException(status_code=404, detail="okf_blocked")
    return PlainTextResponse(raw, media_type="text/markdown; charset=utf-8")
