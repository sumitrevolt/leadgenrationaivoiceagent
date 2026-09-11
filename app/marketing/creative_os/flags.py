"""Creative Automation OS flags — all default OFF (fail-closed)."""

from __future__ import annotations

import os


def _on(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def os_enabled() -> bool:
    """Master kill for Creative Automation OS APIs/orchestration."""
    return _on("CREATIVE_OS_ENABLED")


def provider_enabled(name: str) -> bool:
    """Per-provider gate. Deterministic is always eligible when OS is on."""
    key = str(name or "").strip().lower().replace("-", "_").replace(".", "_")
    if key in ("deterministic", "ffmpeg", "ffmpeg_template"):
        return os_enabled()
    if key == "hyperframes":
        # Named _ENABLED rather than the generic CREATIVE_PROVIDER_<NAME> shape.
        # Kept here so this function stays the single answer to "is provider X
        # on?" — a second, differently-named check elsewhere is how a provider
        # ends up live while the flag snapshot still reports it off.
        return os_enabled() and _on("CREATIVE_PROVIDER_HYPERFRAMES_ENABLED")
    return os_enabled() and _on(f"CREATIVE_PROVIDER_{key.upper()}")


def gpu_lab_enabled() -> bool:
    return os_enabled() and _on("CREATIVE_GPU_LAB_ENABLED")


def comfyui_enabled() -> bool:
    return os_enabled() and gpu_lab_enabled() and _on("CREATIVE_COMFYUI_ENABLED")


def learning_enabled() -> bool:
    """Recommendations surface only — never auto-mutates prompts."""
    return os_enabled() and _on("CREATIVE_LEARNING_ENABLED", "1")


def novelty_enabled() -> bool:
    """Novelty gate active.

    ON is the *safe* state — it refuses clones of a recent video. Disabling it is
    the risky act, so fail-closed = ON. Independent of ``os_enabled()`` so the
    flag snapshot always reflects the intended default.
    """
    return _on("CREATIVE_NOVELTY_ENABLED", "1")


# ---------------------------------------------------- novelty-gate tunables
# The novelty gate's three numeric knobs plus its "cannot evaluate" alert switch.
# Every one is read at CALL time (never frozen at import) so an operator can
# retune the gate without a restart. The fail-closed direction is stated per
# accessor; a `try/except` fallback keeps a malformed value from ever widening
# the gate. `novelty.py` keeps `JACCARD_THRESHOLD` / `DEFAULT_LOOKBACK` as the
# *defaults behind* these accessors — the constants are documentation, these are
# the live authority.
def novelty_window_days() -> int:
    """Rolling window (calendar days) for the same-recipe/template rule.

    A prior same-(recipe, template) entry within this many calendar days of the
    candidate is refused. Fail-closed = **larger** (a wider window refuses more).
    Clamped to ``[1, 30]``; a ``0``/garbage value clamps to ``1`` so the gate is
    never disabled by a bad value.
    """
    try:
        v = int(str(os.getenv("CREATIVE_NOVELTY_WINDOW_DAYS", "7")).strip())
    except Exception:
        v = 1
    return max(1, min(30, v))


def novelty_jaccard_threshold() -> float:
    """Scene-text Jaccard at/above which a candidate is a near-duplicate.

    Fail-closed = **lower** (a lower threshold refuses more). Clamped to
    ``[0.4, 0.9]``; the clamp prevents ``0`` (refuse-everything) and ``1``
    (allow-everything).
    """
    try:
        v = float(str(os.getenv("CREATIVE_NOVELTY_JACCARD_THRESHOLD", "0.6")).strip())
    except Exception:
        v = 0.6
    return max(0.4, min(0.9, v))


def novelty_max_rotations() -> int:
    """Max rotation retries the selector may offer before the gate exhausts.

    Fail-closed = **higher** (more rotations = more chances to find a distinct
    creative). Clamped to ``[1, 12]``.
    """
    try:
        v = int(str(os.getenv("CREATIVE_NOVELTY_MAX_ROTATIONS", "6")).strip())
    except Exception:
        v = 6
    return max(1, min(12, v))


def novelty_alert_on_unverifiable() -> bool:
    """Alert (owner feed) when a candidate cannot be fingerprinted.

    Fail-closed = ON: a gate that cannot evaluate a candidate is a truthfulness
    gap the owner should see. Independent of ``os_enabled()`` so the flag
    snapshot always reflects the intended default.
    """
    return _on("CREATIVE_NOVELTY_ALERT_ON_UNVERIFIABLE", "1")


def novelty_scene_match_ratio() -> float:
    """Fraction of a candidate's scenes that must match a prior's to be refused.

    Catches the Jaccard-DILUTION clone: changing 1 of 4 scenes keeps the
    whole-text Jaccard near/below the 0.6 threshold, so the global shingle check
    misses it, yet 3 of 4 scenes are byte-identical. Fail-closed = LOWER (a lower
    ratio refuses more partial clones). Clamped to ``[0.0, 1.0]``; the clamp floor
    stops a ``0`` value from refusing *every* candidate and starving the tenant.
    """
    try:
        v = float(str(os.getenv("CREATIVE_NOVELTY_SCENE_MATCH_RATIO", "0.75")).strip())
    except Exception:
        v = 0.75
    return max(0.0, min(1.0, v))


def social_profile_enabled() -> bool:
    """Social-profile analysis (new customer-data collection) → off by default."""
    return _on("CREATIVE_SOCIAL_PROFILE_ENABLED", "0")


def learning_persist_enabled() -> bool:
    """Persist the creative-learning ledger to disk (durable, per-tenant)."""
    return _on("CREATIVE_LEARNING_PERSIST_ENABLED", "1")


def max_revisions() -> int:
    try:
        return max(1, int(os.getenv("CREATIVE_MAX_REVISIONS", "3")))
    except Exception:
        return 3


def tenant_gen_budget() -> int:
    """Max generations per tenant per UTC day (fail-closed when exceeded)."""
    try:
        return max(1, int(os.getenv("CREATIVE_TENANT_DAILY_BUDGET", "20")))
    except Exception:
        return 20


def worker_timeout_s() -> int:
    try:
        return max(30, int(os.getenv("CREATIVE_WORKER_TIMEOUT_S", "300")))
    except Exception:
        return 300


# ----------------------------------------------------------------- P1-3 caps
# Concurrency caps for the render plane. These are exposed here (the single
# flag authority) but deliberately NOT wired into `app/render_plane/*` by this
# wave — that module belongs to another writer. Fail-closed for a numeric cap
# means a small, safe default: an unset/!malformed value can never widen
# concurrency, and `max(1, ...)` refuses a 0/negative that would deadlock the
# plane.
def max_concurrent_renders_per_tenant() -> int:
    """Max concurrent renders for ONE tenant (P1-3). Safe default 2."""
    try:
        return max(1, int(os.getenv("CREATIVE_RENDER_MAX_CONCURRENT_PER_TENANT", "2")))
    except Exception:
        return 2


def max_concurrent_renders_global() -> int:
    """Max concurrent renders across ALL tenants (P1-3). Safe default 8."""
    try:
        return max(1, int(os.getenv("CREATIVE_RENDER_MAX_CONCURRENT_GLOBAL", "8")))
    except Exception:
        return 8


def flag_snapshot() -> dict[str, bool | int | float]:
    return {
        "CREATIVE_OS_ENABLED": os_enabled(),
        "CREATIVE_PROVIDER_DETERMINISTIC": provider_enabled("deterministic"),
        "CREATIVE_PROVIDER_HYPERFRAMES_ENABLED": provider_enabled("hyperframes"),
        "CREATIVE_PROVIDER_QWEN_IMAGE": provider_enabled("qwen_image"),
        "CREATIVE_PROVIDER_FLUX_SCHNELL": provider_enabled("flux_schnell"),
        "CREATIVE_PROVIDER_WAN22": provider_enabled("wan22"),
        "CREATIVE_PROVIDER_COMFYUI": provider_enabled("comfyui"),
        "CREATIVE_GPU_LAB_ENABLED": gpu_lab_enabled(),
        "CREATIVE_COMFYUI_ENABLED": comfyui_enabled(),
        "CREATIVE_LEARNING_ENABLED": learning_enabled(),
        "CREATIVE_NOVELTY_ENABLED": novelty_enabled(),
        "CREATIVE_NOVELTY_WINDOW_DAYS": novelty_window_days(),
        "CREATIVE_NOVELTY_JACCARD_THRESHOLD": novelty_jaccard_threshold(),
        "CREATIVE_NOVELTY_MAX_ROTATIONS": novelty_max_rotations(),
        "CREATIVE_NOVELTY_ALERT_ON_UNVERIFIABLE": novelty_alert_on_unverifiable(),
        "CREATIVE_NOVELTY_SCENE_MATCH_RATIO": novelty_scene_match_ratio(),
        "CREATIVE_SOCIAL_PROFILE_ENABLED": social_profile_enabled(),
        "CREATIVE_LEARNING_PERSIST_ENABLED": learning_persist_enabled(),
        "CREATIVE_MAX_REVISIONS": max_revisions(),
        "CREATIVE_TENANT_DAILY_BUDGET": tenant_gen_budget(),
        "CREATIVE_WORKER_TIMEOUT_S": worker_timeout_s(),
        "CREATIVE_RENDER_MAX_CONCURRENT_PER_TENANT": max_concurrent_renders_per_tenant(),
        "CREATIVE_RENDER_MAX_CONCURRENT_GLOBAL": max_concurrent_renders_global(),
        "PLATFORM_DIAL_DAILY_HARD_OFF": not _on("PLATFORM_DIAL_DAILY"),
    }


__all__ = [
    "comfyui_enabled",
    "flag_snapshot",
    "gpu_lab_enabled",
    "learning_enabled",
    "learning_persist_enabled",
    "max_concurrent_renders_global",
    "max_concurrent_renders_per_tenant",
    "max_revisions",
    "novelty_alert_on_unverifiable",
    "novelty_enabled",
    "novelty_jaccard_threshold",
    "novelty_max_rotations",
    "novelty_scene_match_ratio",
    "novelty_window_days",
    "os_enabled",
    "provider_enabled",
    "social_profile_enabled",
    "tenant_gen_budget",
    "worker_timeout_s",
]
