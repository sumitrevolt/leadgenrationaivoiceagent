"""Engineering-agent extension endpoints — code-review · self-recall · checkpoints.

3 naye engineering capabilities (Kilo-Code "Review agent" + Hermes self-recall +
Hermes/Kilo checkpoints) ko admin-gated API surface deta. Modules khud read-only,
never-raise, flag-gated; yeh router unko expose karta verify + ad-hoc use ke liye.

Mount (main session wires it): app.include_router(eng_agents.router, prefix="/api/agents-ext")
Routes (sab require_admin; rollback = require_super_admin RBAC design):
  - POST /code-review            → code_reviewer.review
  - POST /recall   GET /recall   → agent_recall.record / .recall
  - POST /checkpoint  GET /checkpoints  POST /rollback/{ckpt_id}
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin, require_super_admin

router = APIRouter(tags=["EngAgents"])


# --------------------------- Code Review agent (Kilo-Code parity) --------------------- #
class CodeReviewIn(BaseModel):
    code: str
    dimensions: list[str] | None = None


@router.post("/code-review")
async def code_review(body: CodeReviewIn, _user=Depends(require_admin)):
    """Dedicated review-agent: code/diff ka multi-dimension structured review
    (correctness/security/performance/style/tests). LLM-grounded; fail → static
    minimal result. Read-only, never-raise, flag-independent (admin-gated)."""
    from app.agents import code_reviewer

    result = await code_reviewer.review(body.code, body.dimensions)
    return {"review_enabled": code_reviewer.enabled(), **result}


# --------------------------- Agent self-recall (Hermes parity) ------------------------ #
class RecallRecordIn(BaseModel):
    kind: str
    text: str
    meta: dict | None = None


@router.post("/recall")
async def recall_record(body: RecallRecordIn, _user=Depends(require_admin)):
    """Agent ka ek run/decision recall-store me record karo (append-only jsonl)."""
    from app.agents import agent_recall

    return agent_recall.record(body.kind, body.text, body.meta)


@router.get("/recall")
async def recall_search(q: str, k: int = 6, _user=Depends(require_admin)):
    """Agent ke apne past runs/decisions search karo — semantic-if-available,
    deterministic keyword fallback. Read-only, never-raise."""
    from app.agents import agent_recall

    hits = await agent_recall.recall(q, k=k)
    return {
        "ok": True,
        "query": q,
        "recall_enabled": agent_recall.enabled(),
        "count": len(hits),
        "hits": hits,
    }


# --------------------------- Checkpoints + rollback (Hermes/Kilo parity) --------------- #
class CheckpointIn(BaseModel):
    paths: list[str]
    label: str = ""


@router.post("/checkpoint")
async def checkpoint_create(body: CheckpointIn, _user=Depends(require_admin)):
    """Files/dirs ka snapshot lo agent ke data mutate karne se PEHLE. SIRF data/ +
    app/ ke andar safe paths (traversal-guarded). never-raise."""
    from app.agents import agent_checkpoints

    return agent_checkpoints.snapshot(body.paths, body.label)


@router.get("/checkpoints")
async def checkpoints_list(limit: int = 50, _user=Depends(require_admin)):
    """Recent checkpoints (newest-first manifests)."""
    from app.agents import agent_checkpoints

    return {"checkpoints": agent_checkpoints.list_checkpoints(limit)}


@router.post("/rollback/{ckpt_id}")
async def checkpoint_rollback(ckpt_id: str, _user=Depends(require_super_admin)):
    """Checkpoint ke files wapas restore karo — SUPER_ADMIN only (mutating + RBAC
    design, code_upgrader patch-status jaisa gate)."""
    from app.agents import agent_checkpoints

    result = agent_checkpoints.rollback(ckpt_id)
    if not result.get("ok") and result.get("error") == "checkpoint not found":
        raise HTTPException(status_code=404, detail="checkpoint not found")
    return result


# --------------------------- Enterprise Persona Registry (ADR-184) --------------------- #
@router.get("/personas")
async def get_agent_personas(_user=Depends(require_admin)):
    """Saare AI staff members ke enterprise-grade distinct personas.

    Har agent ka: name, title, tone, expertise, sales_motivation, system_prompt,
    coordination_role. Admin dashboard /app/office isse render karta hai.
    """
    from app.platform.team import staff_personas_summary

    personas = staff_personas_summary()
    return {"personas": personas, "count": len(personas)}
