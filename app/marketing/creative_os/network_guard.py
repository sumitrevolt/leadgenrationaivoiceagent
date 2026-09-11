"""Network-isolation guard for the HyperFrames render step (RC5).

WHY THIS EXISTS
---------------
``hyperframes_provider.network_disabled()`` was a *declared* flag with **zero call
sites**: it documented an intent ("a production render must not touch the
network") that nothing actually enforced. A boolean cannot stop a child process
from opening a socket. This module turns that intent into a decision the render
path really applies — and, just as important, reports **honestly** whether
isolation happened. ``enforced`` is a *truth value*, never a wish.

MODES (priority order, all decided at CALL time)
------------------------------------------------
1. ``container_netns_none`` — ``CREATIVE_RENDER_NETLESS=1``. This is a **fact
   asserted by the runtime**: the render process is running inside the
   ``network_mode: none`` renderer service, so it has no network interface at all
   (only ``lo``). No probe is needed, and none can improve on the truth.
   ``enforced=True``. (The netless service itself is delivered by T07; this
   branch is the honest contract T07 fulfils, so the mode is addable without
   reshaping this file.)
2. ``netns`` — a call-time capability probe of ``unshare --net -- true``
   succeeded. ``argv_prefix=["unshare","--net","--"]`` is prepended to the fixed
   renderer argv. ``enforced=True``.
3. ``proxy_blackhole`` — the honest fallback. The child gets an environment that
   black-holes every proxy variable (``http://127.0.0.1:9``) and clears
   ``NO_PROXY``. This is **not** isolation — a determined child can ignore proxy
   env — so ``enforced=False`` and the artifact is labelled
   ``network_best_effort``. It is never called "hermetic".

CONTRACT
--------
* ``build_isolation()`` returns a dict and **never raises**.
* ``enforced`` is True only in modes 1 and 2, where a real primitive ran.
* No secrets are read or returned; the probe result carries only a returncode.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # noqa: S404 - fixed argv, shell=False (probe only)
import sys
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

#: Method identifiers recorded on every rendered artifact.
METHOD_CONTAINER_NETLESS = "container_netns_none"
METHOD_NETNS = "netns"
METHOD_PROXY_BLACKHOLE = "proxy_blackhole"
METHOD_NETWORK_ALLOWED = "network_allowed"

#: Truthful labels. "hermetic" is reserved for `enforced is True`.
LABEL_HERMETIC = "hermetic"
LABEL_BEST_EFFORT = "network_best_effort"

#: The netless renderer sets this in its own environment (T07).
NETLESS_ENV = "CREATIVE_RENDER_NETLESS"

#: Fail-closed switch: refuse to render rather than render un-isolated.
STRICT_ENV = "CREATIVE_HYPERFRAMES_NETWORK_STRICT"

#: Test/ops override for the `unshare` binary location.
UNSHARE_BIN_ENV = "CREATIVE_NETWORK_UNSHARE_BIN"

#: The blackhole target: TCP port 9 (discard) on loopback — nothing listens.
BLACKHOLE_PROXY = "http://127.0.0.1:9"

#: Proxy variables black-holed in fallback mode (upper + lower case).
_PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy")
_NO_PROXY_KEYS = ("NO_PROXY", "no_proxy")


# --------------------------------------------------------------------- flags
def _env_on(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def netless_requested() -> bool:
    """True inside the ``network_mode: none`` renderer (a runtime-asserted fact)."""
    return _env_on(NETLESS_ENV, "0")


def strict_requested() -> bool:
    """True when an un-enforced render must be refused (fail-closed)."""
    return _env_on(STRICT_ENV, "0")


# --------------------------------------------------------------------- probe
def unshare_path() -> str:
    """Resolve the ``unshare`` binary at CALL time (never frozen at import)."""
    override = os.getenv(UNSHARE_BIN_ENV, "").strip()
    if override:
        return override
    return shutil.which("unshare") or ""


def probe_netns(unshare: str | None = None, *, timeout_s: int = 10) -> dict[str, Any]:
    """Probe whether ``unshare --net -- true`` actually succeeds here.

    Returns a small, non-secret dict: ``{"available", "returncode", "detail"}``.
    ``available`` is True only when the probe ran AND exited 0 — a missing binary,
    a non-POSIX host, a timeout or any other failure all degrade to
    ``available=False`` (the honest "isolation did not happen" answer).
    """
    exe = unshare if unshare is not None else unshare_path()
    if not exe:
        return {"available": False, "returncode": None, "detail": "unshare_not_found"}
    if os.name != "posix":
        return {
            "available": False,
            "returncode": None,
            "detail": f"not_posix:{sys.platform}",
        }
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, shell=False
            [exe, "--net", "--", "true"],
            capture_output=True,
            timeout=max(1, int(timeout_s)),
            check=False,
        )
    except FileNotFoundError:
        return {"available": False, "returncode": None, "detail": "unshare_not_found"}
    except subprocess.TimeoutExpired:
        return {"available": False, "returncode": None, "detail": "probe_timeout"}
    except Exception as exc:  # never raises: a failed probe is just "not available"
        return {
            "available": False,
            "returncode": None,
            "detail": f"probe_error:{type(exc).__name__}",
        }
    rc = proc.returncode
    return {
        "available": rc == 0,
        "returncode": rc,
        "detail": "ok" if rc == 0 else f"returncode={rc}",
    }


# --------------------------------------------------------------- env plumbing
def isolation_env_delta() -> tuple[dict[str, str], tuple[str, ...]]:
    """Env keys to ADD and keys to REMOVE for proxy-blackhole mode.

    Returned as a delta (not a full environment) so a caller can layer it on top
    of its own hermetic env without the delta silently reverting a hermetic blank.
    """
    delta = {key: BLACKHOLE_PROXY for key in _PROXY_KEYS}
    delta["CREATIVE_NETWORK_BLACKHOLE"] = "1"
    # A render must never authenticate to a cloud provider.
    delta["HYPERFRAMES_API_KEY"] = ""
    return delta, _NO_PROXY_KEYS


def blackhole_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """A full environment with every proxy variable black-holed (for direct use)."""
    env = dict(base if base is not None else os.environ)
    delta, pops = isolation_env_delta()
    env.update(delta)
    for key in pops:
        env.pop(key, None)
    return env


def apply_isolation_env(base_env: dict[str, str], iso: dict[str, Any]) -> dict[str, str]:
    """Layer an isolation dict's env delta/pops onto a base environment."""
    env = dict(base_env or {})
    delta = iso.get("env") or {}
    if isinstance(delta, dict):
        env.update({str(k): str(v) for k, v in delta.items()})
    for key in iso.get("env_pop") or ():
        env.pop(str(key), None)
    return env


# ------------------------------------------------------------------ decisions
def _blank_probe(detail: str) -> dict[str, Any]:
    return {"available": False, "returncode": None, "detail": detail}


def build_isolation() -> dict[str, Any]:
    """Decide how (and whether) the render will be network-isolated. Never raises.

    Returns::

        {
          "method": "container_netns_none" | "netns" | "proxy_blackhole",
          "enforced": bool,          # True ONLY when a real primitive ran
          "argv_prefix": list[str],  # prepend to the fixed renderer argv
          "env": dict[str, str],     # env delta to layer on the hermetic env
          "env_pop": list[str],      # env keys to remove
          "label": "hermetic" | "network_best_effort",
          "probe": {"available", "returncode", "detail"},
        }
    """
    try:
        # Mode 1 — a runtime-asserted fact: we are already in a netless container.
        if netless_requested():
            return {
                "method": METHOD_CONTAINER_NETLESS,
                "enforced": True,
                "argv_prefix": [],
                "env": {},
                "env_pop": [],
                "label": LABEL_HERMETIC,
                "probe": {
                    "available": True,
                    "returncode": 0,
                    "detail": "netless_container",
                },
            }

        # Mode 2 — a real netns prefix, only if the probe actually succeeds.
        probe = probe_netns()
        if probe.get("available"):
            return {
                "method": METHOD_NETNS,
                "enforced": True,
                "argv_prefix": [unshare_path() or "unshare", "--net", "--"],
                "env": {},
                "env_pop": [],
                "label": LABEL_HERMETIC,
                "probe": probe,
            }

        # Mode 3 — the honest fallback. Not isolation; labelled as such.
        delta, pops = isolation_env_delta()
        return {
            "method": METHOD_PROXY_BLACKHOLE,
            "enforced": False,
            "argv_prefix": [],
            "env": delta,
            "env_pop": list(pops),
            "label": LABEL_BEST_EFFORT,
            "probe": probe,
        }
    except Exception as exc:  # pragma: no cover - defensive; must never raise
        logger.warning("[network_guard] build_isolation failed: %s", exc)
        return {
            "method": METHOD_PROXY_BLACKHOLE,
            "enforced": False,
            "argv_prefix": [],
            "env": {},
            "env_pop": [],
            "label": LABEL_BEST_EFFORT,
            "probe": _blank_probe(f"guard_error:{type(exc).__name__}"),
        }


def no_isolation(reason: str = "network_allowed") -> dict[str, Any]:
    """The evidence dict for a render where network isolation was not requested."""
    return {
        "method": METHOD_NETWORK_ALLOWED,
        "enforced": False,
        "argv_prefix": [],
        "env": {},
        "env_pop": [],
        "label": LABEL_BEST_EFFORT,
        "probe": _blank_probe(reason),
    }


def isolation_label(iso: dict[str, Any] | None) -> str:
    """``"hermetic"`` iff isolation was actually enforced, else ``network_best_effort``.

    The design forbids calling an un-enforced render "hermetic" (PRD §2 RC5 / C7).
    """
    try:
        return LABEL_HERMETIC if bool((iso or {}).get("enforced")) else LABEL_BEST_EFFORT
    except Exception:  # pragma: no cover - defensive
        return LABEL_BEST_EFFORT


def isolation_evidence(iso: dict[str, Any] | None) -> dict[str, Any]:
    """The compact ``{method, enforced, label}`` triple recorded on an artifact."""
    data = iso or {}
    method = str(data.get("method") or METHOD_NETWORK_ALLOWED)
    enforced = bool(data.get("enforced"))
    return {
        "method": method,
        "enforced": enforced,
        "label": LABEL_HERMETIC if enforced else LABEL_BEST_EFFORT,
    }


def probe_facts() -> dict[str, Any]:
    """The (a)/(b)/(c) RC5 probe facts for evidence reporting. Never raises."""
    try:
        exe = unshare_path()
        probe = probe_netns(exe if exe else "")
        iso = build_isolation()
        return {
            "unshare_present": bool(exe),
            "unshare_path": exe or None,
            "probe_returncode": probe.get("returncode"),
            "probe_detail": probe.get("detail"),
            "netless_requested": netless_requested(),
            "strict_requested": strict_requested(),
            "chosen_method": iso.get("method"),
            "enforced": bool(iso.get("enforced")),
            "label": iso.get("label"),
            "platform": sys.platform,
            "os_name": os.name,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": f"{type(exc).__name__}: {exc}"}


__all__ = [
    "BLACKHOLE_PROXY",
    "LABEL_BEST_EFFORT",
    "LABEL_HERMETIC",
    "METHOD_CONTAINER_NETLESS",
    "METHOD_NETNS",
    "METHOD_NETWORK_ALLOWED",
    "METHOD_PROXY_BLACKHOLE",
    "NETLESS_ENV",
    "STRICT_ENV",
    "UNSHARE_BIN_ENV",
    "apply_isolation_env",
    "blackhole_env",
    "build_isolation",
    "isolation_env_delta",
    "isolation_evidence",
    "isolation_label",
    "netless_requested",
    "no_isolation",
    "probe_facts",
    "probe_netns",
    "strict_requested",
    "unshare_path",
]
