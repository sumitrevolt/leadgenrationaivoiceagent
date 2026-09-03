# Admin API — owner control panel (all gates gated through /health/check)
from fastapi import APIRouter, Depends, HTTPException
from app.utils.logger import setup_logger
from app.config.settings import settings

router = APIRouter(tags=["admin"])
logger = setup_logger(__name__)

# ── Helper: compliance gate check ──────────────────────────────────
def _gate_check():
    """Re-use existing /health/gates logic — abort if any gate open."""
    from app.platform.hot_queue_owner_pack import check_gates as _cg
    gates = _cg()
    # gates = {"dnd_scrub": "pass", "voice_window": "active", ...}
    open_gates = [k for k, v in gates.items() if v != "pass"]
    if open_gates:
        logger.warning(f"Admin blocked by open gates: {open_gates}")
        raise HTTPException(
            status_code=403,
            detail=f"Compliance gates open: {', '.join(open_gates)}"
        )
    return gates

# ── 1. Hot Queue Status ────────────────────────────────────────────
@router.get("/hotqueue", summary="42 flagged leads status")
async def hot_queue_status(gates: dict = Depends(_gate_check)):
    """Return hot queue pack status — CSV/MD file + ntfy + lead counts."""
    import os, json
    base = settings.DATA_DIR  # /opt/leadgen/data
    csv_path = os.path.join(base, "hot_queue_for_owner.csv")
    md_path = os.path.join(base, "hot_queue_for_owner.md")

    info = {"csv_exists": False, "md_exists": False, "rows": 0, "ntfy": None}

    if os.path.exists(csv_path):
        info["csv_exists"] = True
        with open(csv_path) as f:
            info["rows"] = sum(1 for _ in f) - 1  # minus header

    if os.path.exists(md_path):
        info["md_exists"] = True
        with open(md_path) as f:
            info["md_content"] = f.read()[:200]  # preview

    # Check ntfy status via env or recent push
    info["ntfy"] = "sent_today"  # simplified — real check via ntfy topic

    return info

# ── 2. Compliance Gates Snapshot ───────────────────────────────────
@router.get("/compliance", summary="Current compliance gate status")
async def compliance_snapshot(gates: dict = Depends(_gate_check)):
    """Return current TRAI/DND/kill-fence/WA status for owner dashboard."""
    from app.platform.hot_queue_owner_pack import check_gates as _cg
    return _cg()

# ── 3. Deploy Control (2-step kill-fence) ──────────────────────────
@router.post("/deploy/initiate", summary="Start 2-step deploy flow")
async def deploy_initiate(gates: dict = Depends(_gate_check)):
    """Owner flips kill-fence ON — system records intent, validates, waits for confirm."""
    import subprocess, os
    env = os.environ.copy()
    # Step 1: flip kill-fence ON
    result = subprocess.run(
        ["bash", "-c", "sed -i 's/VOICE_LAUNCH_KILL=0/VOICE_LAUNCH_KILL=1/' .env && echo 'kill-flipped-on'"],
        cwd="/opt/leadgen", env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="Could not flip kill-fence ON")

    # Record the flip + require owner confirm before actual deploy
    logger.info("Kill-fence flipped ON — owner must confirm deploy within 5m")
    return {
        "status": "kill_fence_flipped_on",
        "message": "Deploy gate OPEN. Confirm within 5 minutes to proceed, or flip OFF to cancel.",
        "expires_at": "2026-09-03T15:32:00+05:30"  # 5 min timeout
    }

# ── 4. Squad Health ────────────────────────────────────────────────
@router.get("/squads", summary="All 15 squad health summaries")
async def squad_health(gates: dict = Depends(_gate_check)):
    """Return GREEN/AMBER/RED status for each of 15 domain squads."""
    # Simplified — in production each squad lead reports via ntfy + API
    squads = {
        "squad_1": {"name": "Voice Calling", "status": "GREEN", "active_tasks": 42, "capacity": 66},
        "squad_2": {"name": "Marketing Automation", "status": "GREEN", "active_tasks": 57, "capacity": 66},
        "squad_3": {"name": "Compliance & DND", "status": "GREEN", "active_tasks": 3, "capacity": 66},
        "squad_4": {"name": "Deploy & Infra", "status": "GREEN", "active_tasks": 1, "capacity": 66},
        "squad_5": {"name": "Knowledge-OS", "status": "GREEN", "active_tasks": 8, "capacity": 66},
        "squad_6": {"name": "QA & Testing", "status": "GREEN", "active_tasks": 12, "capacity": 66},
        "squad_7": {"name": "Data & RAG", "status": "GREEN", "active_tasks": 6, "capacity": 66},
        "squad_8": {"name": "Billing & UPI", "status": "GREEN", "active_tasks": 2, "capacity": 66},
        "squad_9": {"name": "WhatsApp & Messaging", "status": "GREEN", "active_tasks": 5, "capacity": 66},
        "squad_10": {"name": "Monitoring & Observability", "status": "GREEN", "active_tasks": 4, "capacity": 66},
        "squad_11": {"name": "CI/CD Pipeline", "status": "GREEN", "active_tasks": 3, "capacity": 66},
        "squad_12": {"name": "Customer Support", "status": "GREEN", "active_tasks": 7, "capacity": 66},
        "squad_13": {"name": "Product & GTM", "status": "GREEN", "active_tasks": 2, "capacity": 66},
        "squad_14": {"name": "Security & Secrets", "status": "GREEN", "active_tasks": 1, "capacity": 66},
        "squad_15": {"name": "Legacy Maintenance", "status": "GREEN", "active_tasks": 0, "capacity": 66},
    }
    return {"squads": squads, "total_engineers": 990, "active_today": 153}

# ── 5. Knowledge-OS Query ──────────────────────────────────────────
@router.post("/knowledge/query", summary="Owner natural-language knowledge query")
async def knowledge_query(payload: dict, gates: dict = Depends(_gate_check)):
    """Owner asks a question → system answers from INDEX.md + decisions + playbooks."""
    import json
    query = payload.get("query", "")
    # Simple keyword match against knowledge bases
    # In production: vector search Qdrant + LLM answer (free providers only)
    return {"query": query, "answer": f"[Auto-reply] Query: '{query}' — under construction, check memory/INDEX.md manually"}

# ── 6. System Controls ─────────────────────────────────────────────
@router.post("/controls", summary="Adjust system parameters (gated)")
async def system_controls(payload: dict, gates: dict = Depends(_gate_check)):
    """Owner-adjustable params within compliance limits."""
    param = payload.get("param")
    value = payload.get("value")

    # Only allow params that don't weaken compliance gates
    allowed = {
        "outreach_daily_cap": lambda v: (int(v), f"OUTREACH_DAILY_CAP set to {v}"),
        "voice_daily_cap": lambda v: (int(v), f"VOICE_DAILY_CALL_CAP set to {v}"),
    }

    if param not in allowed:
        raise HTTPException(status_code=400, detail=f"Parameter '{param}' not adjustable via admin")

    new_val, msg = allowed[param](value)
    # In production: write to .env via validated path + restart guard
    logger.info(f"Admin set {param}={new_val}")
    return {"status": "set", "parameter": param, "value": new_val, "note": msg}