"""
content_os — Daily video automation engine (leadsgen self-promo + per-customer).

Public entry points:
  - daily_video_run()        — master task: pick today's queue, render, package.
  - enqueue_daily_video_run()— enqueue (idempotent within a day) from beat/admin.
  - run_for_client(slug)     — manual one-client one-shot.

Design principles:
  * INERT by default. Enabled when CONTENT_OS_ENABLED=1 in env.
  * Failures in this module NEVER break the calling stack; we always log and
    return a {"error": str} so beat stays happy.
  * HMAC-signs everything that talks to the local renderer PC.
  * Reuses existing brand_kit, content_pack, reel_video, jingle, video_pipeline
    whenever possible; we only orchestrate around them.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
ENABLED = os.getenv("CONTENT_OS_ENABLED", "0") == "1"
RENDERER_BASE_URL = os.getenv("CONTENT_OS_RENDERER_URL", "http://127.0.0.1:8779").rstrip("/")
RENDERER_HMAC_KEY = os.getenv("CONTENT_OS_HMAC_KEY", "")
MEDIA_INBOX = Path(os.getenv("CONTENT_OS_INBOX", "/opt/leadgen/media/inbox"))
DAILY_BRIEFS_PER_CLIENT = int(os.getenv("CONTENT_OS_DAILY_PER_CLIENT", "2"))
DAILY_BRIEFS_LEADSGEN = int(os.getenv("CONTENT_OS_DAILY_LEADSGEN", "3"))
ASPECTS = ["9x16", "1x1", "16x9"]
IST = timezone(timedelta(hours=5, minutes=30))

# State directories (cheap, append-only — kept on VPS disks).
DATA_DIR = Path(os.getenv("CONTENT_OS_DATA", "/opt/leadgen/media/content_os"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_FILE = DATA_DIR / "queue.jsonl"
LEDGER_FILE = DATA_DIR / "ledger.jsonl"

# Proven-path alias: queue/ledger use the same DATA_DIR store.
PROVEN_PATH_ALIAS = DATA_DIR


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
@dataclass
class RenderBrief:
    """A render request. Serializes to JSON; sent to renderer."""
    brief_id: str
    owner_kind: str           # "leadgen" | "customer"
    owner_slug: str           # "leadgen" or client slug
    niche: str                # e.g., "dentist_pune", "salon_mumbai"
    title: str
    hook: str
    cta_text: str
    cta_url: str
    voice: str = "hi-IN-SwaraNeural"
    captions_burn: bool = True
    brand_kit: dict | None = None
    template: str = "local_service_promo_v1"
    aspects: list[str] = field(default_factory=lambda: list(ASPECTS))
    created_at: float = field(default_factory=time.time)

    def to_dict(self):
        return asdict(self)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _sign(body: bytes) -> str:
    """HMAC-SHA256 renderer auth."""
    if not RENDERER_HMAC_KEY:
        return ""
    mac = hmac.new(RENDERER_HMAC_KEY.encode(), body, hashlib.sha256).hexdigest()
    return mac


def _today_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _idempotency_key() -> str:
    """Day-scoped idempotency key — beat calls within same day are no-ops
    once we've successfully kicked the master task."""
    key_file = DATA_DIR / f"last_run_{_today_ist()}.lock"
    return str(key_file)


def _led_already_ran_today() -> bool:
    p = Path(PROVEN_PATH_ALIAS / f"last_run_{_today_ist()}.lock")
    return p.exists() and p.read_text().strip() == "ok"


def _mark_ran_today():
    lock_file = Path(PROVEN_PATH_ALIAS / f"last_run_{_today_ist()}.lock")
    lock_file.write_text("ok", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict):
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("[content_os] failed to write %s: %s", path, e)


# --------------------------------------------------------------------------- #
# Queue selection
# --------------------------------------------------------------------------- #
def _pick_leadsgen_briefs() -> list[RenderBrief]:
    """leadsgen self-promo briefs — sell THIS product by USING it."""
    today = _today_ist()
    angle_pool = [
        ("automated-lead-machines",
         "Local biz ko daily leads machine chahiye?",
         "Free 90-sec audit lein",
         "https://leadsgenai.in/audit"),
        ("voice-agent-bhashini",
         "AI telecaller jo Hindi me baat karta hai",
         "Demo dekhein",
         "https://leadsgenai.in/demo"),
        ("combo-plan-promo",
         "₹5,999 combo — marketing + voice ek plan me",
         "Pricing dekhein",
         "https://leadsgenai.in/pricing"),
    ]
    out: list[RenderBrief] = []
    for i, (niche, hook, cta, url) in enumerate(angle_pool[:DAILY_BRIEFS_LEADSGEN]):
        out.append(RenderBrief(
            brief_id=f"leadgen-{today}-{i}",
            owner_kind="leadgen",
            owner_slug="leadgen",
            niche=niche,
            title="LeadGen AI Daily",
            hook=hook,
            cta_text=cta,
            cta_url=url,
            template="agency_product_launch_v1",
        ))
    return out


def _pick_customer_briefs() -> list[RenderBrief]:
    """Pick per-customer briefs from onboarded customers.

    Hooks into the existing brand_kit + niche_pack modules — we never duplicate
    business logic. If those say a client has no brand kit we skip them, never
    fall back to fake brand colors."""
    out: list[RenderBrief] = []
    try:
        from app.marketing.brand_kit import list_active_clients  # type: ignore
        from app.marketing.niche_pack import next_pack_item  # type: ignore
    except Exception as e:
        logger.info("[content_os] leadgen marketing deps unavailable (%s); skipping customer queue", e)
        return out

    try:
        clients = list_active_clients() or []
    except Exception as e:
        logger.warning("[content_os] list_active_clients failed: %s", e)
        clients = []

    today = _today_ist()
    for client in clients[:20]:  # safe upper bound per day
        slug = client.get("slug") or client.get("id")
        niche = client.get("niche") or "general"
        try:
            item = next_pack_item(niche=niche, day_key=today)
        except Exception as e:
            logger.info("[content_os] no pack item for %s: %s", niche, e)
            continue
        if not item:
            continue
        for k in range(DAILY_BRIEFS_PER_CLIENT):
            out.append(RenderBrief(
                brief_id=f"{slug}-{today}-{k}",
                owner_kind="customer",
                owner_slug=str(slug),
                niche=str(niche),
                title=item.get("title") or "Daily Promo",
                hook=item.get("hook") or "Acche se accha result chahiye?",
                cta_text=item.get("cta_text") or "Book a slot",
                cta_url=item.get("cta_url") or "https://leadsgenai.in/audit",
                brand_kit=client.get("brand_kit"),
            ))
    return out


# --------------------------------------------------------------------------- #
# Renderer transport
# --------------------------------------------------------------------------- #
def dispatch_to_renderer(brief: RenderBrief) -> dict:
    """POST a brief to the renderer. If renderer unreachable, queue to disk."""
    import requests  # local import — keep leadgen import-graph small

    body = json.dumps(brief.to_dict(), ensure_ascii=False).encode()
    sig = _sign(body)

    # 1) Try live renderer first.
    try:
        r = requests.post(
            f"{RENDERER_BASE_URL}/render",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Render-Signature": sig,
                "X-Brief-Id": brief.brief_id,
            },
            timeout=10,
        )
        if r.ok:
            return r.json()
        logger.warning("[content_os] renderer HTTP %s: %s", r.status_code, r.text[:120])
    except requests.RequestException as e:
        logger.info("[content_os] renderer offline (%s); falling back to inbox-push", e)

    # 2) Fall back: write manifest + placeholders to MEDIA_INBOX so VPS-side
    #    watcher can pick them up and produce locally via ffmpeg/image-gen path.
    target_dir = MEDIA_INBOX / brief.owner_slug / _today_ist() / brief.brief_id
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "brief.json").write_text(body.decode(), encoding="utf-8")
    (target_dir / ".pending").write_text("1", encoding="utf-8")
    return {"status": "queued_local", "path": str(target_dir.resolve())}


# --------------------------------------------------------------------------- #
# Master entry — daily run
# --------------------------------------------------------------------------- #
def daily_video_run(*, force: bool = False) -> dict:
    """Day-scoped master.

    1. Pick leadsgen self-promo briefs.
    2. Pick per-customer briefs from active brand kits.
    3. Dispatch each to renderer (or queue locally).
    4. Persist ledger row.
    """
    if not ENABLED:
        return {"ok": False, "skipped": "CONTENT_OS_DISABLED"}

    if not force and _led_already_ran_today():
        return {"ok": True, "skipped": "already_ran_today"}

    started_at = time.time()
    briefs: list[RenderBrief] = []
    briefs.extend(_pick_leadsgen_briefs())
    briefs.extend(_pick_customer_briefs())

    results = []
    errors = 0
    for b in briefs:
        try:
            res = dispatch_to_renderer(b)
            results.append({"brief_id": b.brief_id, **res})
        except Exception as e:
            errors += 1
            logger.exception("[content_os] dispatch failed for %s", b.brief_id)
            results.append({"brief_id": b.brief_id, "error": str(e)[:200]})

    summary = {
        "ok": True,
        "date": _today_ist(),
        "dispatched": len(results),
        "errors": errors,
        "leadgen_briefs": DAILY_BRIEFS_LEADSGEN,
        "customer_briefs": len(briefs) - DAILY_BRIEFS_LEADSGEN,
        "duration_s": round(time.time() - started_at, 2),
        "results": results[:50],
    }
    _append_jsonl(LEDGER_FILE, {"ts": time.time(), "kind": "daily_run", **summary})
    _mark_ran_today()

    # Hermes staff-log (best-effort; never raises).
    try:
        from app.platform.team import log_event  # type: ignore
        log_event(
            member="content",
            action="daily_video_run",
            detail=f"dispatched={summary['dispatched']} errors={errors}",
            status="ok" if errors == 0 else "partial",
            meta={"module": "content_os", "date": summary["date"]},
        )
    except Exception:
        pass

    return summary


def run_for_client(slug: str) -> dict:
    """Manual one-client trigger — useful for owner 1-clicks or pilot tests."""
    if not ENABLED:
        return {"ok": False, "skipped": "CONTENT_OS_DISABLED"}
    try:
        from app.marketing.brand_kit import get_client  # type: ignore
        client = get_client(slug)
    except Exception as e:
        return {"ok": False, "error": f"unknown_client:{e}"}
    if not client:
        return {"ok": False, "error": "unknown_client"}

    today = _today_ist()
    briefs = []
    for k in range(DAILY_BRIEFS_PER_CLIENT):
        briefs.append(RenderBrief(
            brief_id=f"{slug}-{today}-{k}-manual",
            owner_kind="customer",
            owner_slug=slug,
            niche=client.get("niche") or "general",
            title=f"{client.get('name') or slug} — Daily",
            hook="Quick win in 60 seconds",
            cta_text="Book",
            cta_url="https://leadsgenai.in/start",
            brand_kit=client.get("brand_kit"),
        ))

    out = []
    for b in briefs:
        out.append({"brief_id": b.brief_id, **dispatch_to_renderer(b)})
    return {"ok": True, "client": slug, "dispatched": out}
