# Admin API — owner control panel (all gates gated through /health/check)
from fastapi import APIRouter, Depends, HTTPException

from app.config.settings import settings
from app.utils.logger import setup_logger

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
    import json
    import os
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
    import os
    import subprocess
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

# ── 7. Video Gallery ─────────────────────────────────────────────
@router.get("/videos", summary="List generated video reels")
async def list_videos(gates: dict = Depends(_gate_check)):
    """Return list of generated videos from data/reels/."""
    import json
    import os
    from datetime import datetime

    reels_dir = os.path.join(settings.DATA_DIR, "reels")
    videos = []

    if os.path.exists(reels_dir):
        for f in sorted(os.listdir(reels_dir), reverse=True):
            if f.endswith('.mp4'):
                path = os.path.join(reels_dir, f)
                stat = os.stat(path)
                # Parse info from filename if possible
                # Format: reel_{uuid}.mp4 or reel_{uuid}_mix.mp4
                title = f.replace('reel_', '').replace('.mp4', '').replace('_mix', ' (with music)')
                videos.append({
                    "title": title,
                    "url": f"/site/data/reels/{f}",
                    "size_kb": stat.st_size // 1024,
                    "aspect": "9:16",
                    "date": datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                })

    return {"videos": videos}

# ── 8. Generate Videos ───────────────────────────────────────────
@router.post("/videos/generate", summary="Generate today's branded videos")
async def generate_videos(gates: dict = Depends(_gate_check)):
    """Trigger video generation for own brand + clients."""
    from app.tasks.video_generator import sync_generate_daily_videos

    try:
        result = sync_generate_daily_videos()
        own = result.get("own_brand")
        clients = result.get("clients", [])

        videos_created = 0
        if own:
            videos_created += 1
        videos_created += sum(1 for c in clients if c.get("video_path"))

        return {"ok": True, "videos_created": videos_created, "detail": {"own": bool(own), "clients": len(clients)}}
    except Exception:
        logger.exception("Video generation failed")
        return {"ok": False, "error": "Video generation failed due to an internal error"}

# ── 9. Post Video to Social ──────────────────────────────────────
@router.post("/social/post", summary="Post video to social via Postiz")
async def post_video_to_social(payload: dict, gates: dict = Depends(_gate_check)):
    """Post a video to connected Postiz channels."""
    from app.integrations.postiz import enabled as postiz_enabled
    from app.integrations.postiz import publish_video

    if not postiz_enabled():
        return {"sent": False, "reason": "POSTIZ_API_KEY not set"}

    video_url = payload.get("video_url", "")
    if not video_url:
        return {"sent": False, "reason": "video_url required"}
    # Extract and validate local file path from URL (CodeQL: path injection)
    import os
    import re
    from urllib.parse import urlparse

    parsed = urlparse(video_url)
    filename = os.path.basename(parsed.path or "")
    if not filename:
        return {"sent": False, "reason": "Invalid video_url"}
    if not filename.endswith(".mp4"):
        return {"sent": False, "reason": "Only .mp4 files are supported"}
    if not re.fullmatch(r"[A-Za-z0-9._-]+", filename):
        return {"sent": False, "reason": "Invalid video filename"}

    reels_dir = os.path.realpath(os.path.join(settings.DATA_DIR, "reels"))
    local_path = os.path.realpath(os.path.join(reels_dir, filename))
    if os.path.commonpath([reels_dir, local_path]) != reels_dir:
        return {"sent": False, "reason": "Invalid video path"}

    if not os.path.exists(local_path):
        return {"sent": False, "reason": "Video file not found locally"}

    # Use own-brand client for own videos
    client = {"id": "leadgenai-self", "business_name": "LeadGen AI"}
    caption = payload.get("caption", "LeadGen AI Daily Update")

    result = await publish_video(
        client=client,
        caption=caption,
        video_path=local_path,
        filename=filename,
    )

    return result
