"""Canonical runtime-data path authority.

WHY THIS EXISTS
---------------
Mutable production state currently lives at ``/opt/leadgen/data`` — *inside the
Git checkout*, bind-mounted into all five application services. Three concrete
failures follow from that, all of them already observed:

1. **Deployment can destroy live customer state.** `deploy_vps.sh` uses
   ``git pull --ff-only`` and aborts when tracked `data/` files are dirty (they
   permanently are, because production writes them). Sibling scripts
   (`_mcp_deploy_remote.sh`, `vps_pitch_deploy.sh`) run ``git reset --hard
   origin/main``, which would revert the live delivery ledger and client list.
2. **Tests read production-like fixtures.** A PR #144 test passed locally and
   failed in CI because the repo's committed ``data/wa_suppression.jsonl``
   answered a suppression lookup. A test run on the VPS would write the real
   files.
3. **Paths disagree.** Several modules hardcode ``os.path.join("data", ...)``
   past their own module constant, so there is no single knob to move anything.

The fix is one resolver, consulted **at operation time** — never a module-level
constant captured at import, because that is what makes a path impossible to
redirect from a test fixture that runs later.

CONFIGURATION
-------------
``LEADGEN_RUNTIME_DATA_DIR`` is canonical.

``DATA_DIR`` is honoured as a legacy fallback (``eval_gate``, ``ml_training``,
``lead_usage``, ``meter_watch`` already read it) so this supersedes that
convention rather than competing with it.

Environment behaviour:

* **production** — must be set, absolute, existing, writable, and resolve
  OUTSIDE the repository checkout. Anything else fails closed.
* **development** — a documented local default under the repo, but never on top
  of committed fixtures.
* **tests** — must be explicitly isolated; see :func:`use_test_root`.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

#: Canonical environment key.
ENV_KEY = "LEADGEN_RUNTIME_DATA_DIR"
#: Legacy key some modules already read. Superseded, still honoured.
LEGACY_ENV_KEY = "DATA_DIR"
#: Local-development default (relative to the repo root, deliberately NOT `data/`
#: so a dev run cannot dirty committed fixtures).
DEV_DEFAULT = "var/runtime-data"


class RuntimeDataError(RuntimeError):
    """Configuration is unsafe. Always fail closed rather than guess a path."""


def _repo_root() -> Path:
    # app/platform/runtime_data.py -> app/platform -> app -> <repo root>
    return Path(__file__).resolve().parents[2]


def _is_inside(child: Path, parent: Path) -> bool:
    """True if ``child`` resolves inside ``parent`` (symlinks followed)."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _app_env() -> str:
    return (os.environ.get("APP_ENV") or os.environ.get("ENVIRONMENT") or "").strip().lower()


def is_production() -> bool:
    return _app_env() in {"production", "prod"}


#: Host-side path. NEVER passed to application code — the container sees
#: ENV_KEY. Declared here so the deployment preflight can validate both halves
#: of the mount from one authority.
HOST_ENV_KEY = "LEADGEN_RUNTIME_DATA_HOST_DIR"

#: Canonical subdirectories. A ledger and its lock share a mount by construction.
STORE_CATEGORIES = (
    "billing",
    "compliance",
    "governance",
    "customers",
    "sales",
    "communications",
    "content",
    "delivery",
    "automation",
    "audit",
    "artifacts",
    "cache",
    "locks",
    "migration",
)


def _configured() -> str:
    """Canonical value, with legacy fallback and production conflict rejection.

    `DATA_DIR` predates this module (eval_gate, ml_training, lead_usage and
    meter_watch already read it), so it is honoured rather than competed with.
    But two settings that DISAGREE in production is exactly the ambiguity that
    puts mutable state somewhere nobody expects — that fails closed.
    """
    canonical = (os.environ.get(ENV_KEY) or "").strip()
    legacy = (os.environ.get(LEGACY_ENV_KEY) or "").strip()
    if canonical and legacy and is_production():
        if Path(canonical).expanduser() != Path(legacy).expanduser():
            raise RuntimeDataError(
                f"{ENV_KEY} and {LEGACY_ENV_KEY} are both set and disagree "
                f"({canonical!r} vs {legacy!r}). Refusing to guess which one holds "
                "production state."
            )
    if canonical:
        return canonical
    if legacy:
        logger.warning("[runtime_data] %s is deprecated; set %s instead.", LEGACY_ENV_KEY, ENV_KEY)
        return legacy
    return ""


def runtime_root(*, validate: bool = True, require_writable: bool = True) -> Path:
    """Resolve the runtime-data root. Never cached — see module docstring.

    Fails CLOSED in production: an unset, relative, missing, unwritable, or
    inside-the-checkout path raises rather than silently falling back to the
    repository, because that fallback is exactly the bug this module removes.

    ``require_writable=False`` is for the deploy-gate container, which mounts the
    external root read-only on purpose (it must see the cutover marker without
    being able to mutate production bytes). Live writers keep the default.
    """
    configured = _configured()
    prod = is_production()

    if not configured:
        if prod:
            raise RuntimeDataError(
                f"{ENV_KEY} is not set. Production must store mutable state OUTSIDE "
                "the Git checkout — a deploy that resets the repo would otherwise "
                "destroy live customer data."
            )
        root = _repo_root() / DEV_DEFAULT
        root.mkdir(parents=True, exist_ok=True)
        return root

    root = Path(configured).expanduser()

    if not validate:
        return root

    if prod:
        if not root.is_absolute():
            raise RuntimeDataError(f"{ENV_KEY}={configured!r} must be an absolute path.")
        if not root.exists():
            raise RuntimeDataError(f"{ENV_KEY}={configured!r} does not exist.")
        if not root.is_dir():
            raise RuntimeDataError(f"{ENV_KEY}={configured!r} is not a directory.")
        # Symlink-aware: a symlink pointing back into the checkout is the same
        # hazard wearing a disguise.
        if _is_inside(root, _repo_root()):
            raise RuntimeDataError(
                f"{ENV_KEY}={configured!r} resolves INSIDE the repository checkout "
                f"({_repo_root()}). Mutable state there is destroyed by "
                "`git reset --hard` and blocks `git pull --ff-only`."
            )
        if require_writable and not os.access(root, os.W_OK):
            raise RuntimeDataError(f"{ENV_KEY}={configured!r} is not writable by this user.")
    else:
        root.mkdir(parents=True, exist_ok=True)

    return root


def _safe_segment(segment: str) -> str:
    """Reject path traversal and separators in tenant-derived names.

    Tenant ids reach filenames (``data/content_queue/<client_id>.jsonl``), so an
    id like ``../../etc`` must never escape the data root.
    """
    seg = str(segment or "").strip()
    if not seg or seg in {".", ".."} or "/" in seg or "\\" in seg or "\x00" in seg:
        raise RuntimeDataError(f"unsafe path segment: {segment!r}")
    return seg


def store_path(*segments: str) -> Path:
    """Absolute path to a mutable store beneath the runtime root.

    ``store_path("content_queue", f"{client_id}.jsonl")``
    """
    root = runtime_root()
    parts = [_safe_segment(s) for s in segments]
    path = root.joinpath(*parts)
    if not _is_inside(path.parent, root) and path.parent != root:
        raise RuntimeDataError(f"resolved path escapes the runtime root: {path}")
    return path


def store_dir(*segments: str) -> Path:
    """Like :func:`store_path`, creating the directory."""
    path = store_path(*segments) if segments else runtime_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def lock_path(*segments: str) -> Path:
    """Lock file for a store — deliberately beside its ledger.

    A lock resolving somewhere other than the shared mount coordinates nothing:
    five containers would each take a private lock and all write at once.
    """
    target = store_path(*segments)
    return target.with_suffix(target.suffix + ".lock")


def use_test_root(tmp_path: os.PathLike[str] | str) -> None:
    """Point every mutable store at an isolated temporary root (tests only)."""
    os.environ[ENV_KEY] = str(tmp_path)


def describe() -> dict[str, object]:
    """Safe diagnostic summary — paths and booleans only, never secrets."""
    try:
        root = runtime_root()
        return {
            "env_key": ENV_KEY,
            "configured": bool(_configured()),
            "root": str(root),
            "production": is_production(),
            "inside_checkout": _is_inside(root, _repo_root()),
            "writable": os.access(root, os.W_OK) if root.exists() else False,
        }
    except RuntimeDataError as e:
        return {"env_key": ENV_KEY, "error": str(e), "production": is_production()}


__all__ = [
    "ENV_KEY",
    "LEGACY_ENV_KEY",
    "RuntimeDataError",
    "runtime_root",
    "store_path",
    "store_dir",
    "lock_path",
    "use_test_root",
    "is_production",
    "describe",
]
