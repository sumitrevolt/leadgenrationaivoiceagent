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
    return os_enabled() and _on("CREATIVE_LEARNING_ENABLED")


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


def flag_snapshot() -> dict[str, bool | int]:
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
        "CREATIVE_MAX_REVISIONS": max_revisions(),
        "CREATIVE_TENANT_DAILY_BUDGET": tenant_gen_budget(),
        "CREATIVE_WORKER_TIMEOUT_S": worker_timeout_s(),
        "PLATFORM_DIAL_DAILY_HARD_OFF": not _on("PLATFORM_DIAL_DAILY"),
    }


__all__ = [
    "comfyui_enabled",
    "flag_snapshot",
    "gpu_lab_enabled",
    "learning_enabled",
    "max_revisions",
    "os_enabled",
    "provider_enabled",
    "tenant_gen_budget",
    "worker_timeout_s",
]
