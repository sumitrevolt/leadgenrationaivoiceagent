"""Agent-scale endpoints — batch harness (parallel+checkpoint), guarded code exec,
headless browser enrichment. Power-features SUPER_ADMIN + flag gated (default INERT).

NOT mounted here (no app.include_router) — main.py wiring owner ke haath:
    app.include_router(agent_scale.router, prefix="/api/agents-ext")
Paths is module me prefix-LESS likhe (mount-time prefix lagega → /api/agents-ext/...).

Flags: BATCH_HARNESS · CODE_EXEC (super-admin) · BROWSER_TOOLS (super-admin).
All modules lazy-imported (import-safe). Endpoints never-raise pe bharosa nahi —
underlying agents khud never-raise; yahan sirf gate + thin wrap.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin, require_super_admin

router = APIRouter(tags=["AgentScale"])


# ----------------------------- Batch harness (admin) ----------------------------- #
class BatchIn(BaseModel):
    items: list = []
    action: str = "echo"  # safe built-in demo fn ke liye (echo | normalize)
    concurrency: int = 4


async def _demo_echo(item) -> dict:
    """SAFE built-in demo fn — sirf echo (no side-effects). HTTP pe arbitrary fn
    nahi aa sakta, isliye endpoint yeh use karta; programmatic callers run_batch ko
    apna real `async def fn(item)` pass karte (see app.agents.batch_harness)."""
    return {"ok": True, "summary": f"echo:{str(item)[:120]}"}


async def _demo_normalize(item) -> dict:
    """SAFE built-in demo fn — string normalize (trim + lower). No side-effects."""
    try:
        s = str(item).strip().lower()
    except Exception:
        s = ""
    return {"ok": True, "summary": s[:120]}


@router.post("/batch")
async def batch_run(body: BatchIn, _user=Depends(require_admin)):
    """Bounded-parallel batch over items using a SAFE built-in demo fn (echo/normalize)
    — HTTP pe arbitrary callable nahi aa sakta. Programmatic callers
    `app.agents.batch_harness.run_batch(real_fn, items, ...)` directly call karte.
    Checkpoint + resume built-in (ckpt_id return hota)."""
    from app.agents import batch_harness

    fn = _demo_normalize if (body.action or "").strip().lower() == "normalize" else _demo_echo
    res = await batch_harness.run_batch(
        fn,
        list(body.items or []),
        concurrency=body.concurrency,
        label=f"demo:{body.action or 'echo'}",
    )
    return {"enabled": batch_harness.enabled(), **res}


@router.get("/batch/runs")
async def batch_runs(limit: int = 50, _user=Depends(require_admin)):
    """Recent checkpoint runs (per-file ok/failed summary)."""
    from app.agents import batch_harness

    return {"enabled": batch_harness.enabled(), "runs": batch_harness.list_batches(limit)}


# ----------------------------- Code exec (SUPER_ADMIN, gated) ----------------------------- #
class ExecIn(BaseModel):
    script: str
    timeout_s: int = 20


@router.post("/exec")
async def code_exec_run(body: ExecIn, _user=Depends(require_super_admin)):
    """Guarded Python script run — SUPER_ADMIN only. CODE_EXEC=1 OFF (default) ho to
    {"ok":False,"error":"disabled"} return (kuch run NAHI hota). True sandbox nahi —
    guarded isolated subprocess only."""
    from app.agents import code_exec

    return await code_exec.execute(body.script, timeout_s=body.timeout_s)


# ----------------------------- Browser tools (SUPER_ADMIN, gated) ----------------------------- #
class BrowserFetchIn(BaseModel):
    url: str
    timeout_s: int = 20


@router.post("/browser/fetch")
async def browser_fetch(body: BrowserFetchIn, _user=Depends(require_super_admin)):
    """Headless render fetch (title + text) for enrichment — SUPER_ADMIN only.
    BROWSER_TOOLS=1 OFF (default) → disabled. playwright missing → graceful error.
    ToS/robots respect — enrichment only (no bulk crawl)."""
    from app.agents import browser_tools

    return await browser_tools.fetch_rendered(body.url, timeout_s=body.timeout_s)


@router.get("/status")
async def agent_scale_status(_user=Depends(require_admin)):
    """Teen power-features ka flag-status (default sab OFF = inert)."""
    from app.agents import batch_harness, browser_tools, code_exec

    return {
        "batch_harness": batch_harness.enabled(),
        "code_exec": code_exec.enabled(),
        "browser_tools": browser_tools.enabled(),
    }
