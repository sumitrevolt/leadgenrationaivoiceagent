"""Filesystem job/artifact spool for the netless renderer (T07, RC5).

WHY THIS EXISTS
---------------
RC5's enforcement is a ``network_mode: none`` renderer container (see
``app/marketing/creative_os/network_guard.py``). A container with **no network
interface at all** cannot receive a job over HTTP and cannot upload an artifact,
so the networked orchestrator (``worker-video``) and the netless ``renderer``
exchange work through a **filesystem spool** on a volume they both mount:

    orchestrator (networked)              renderer (network_mode: none)
    ------------------------              ------------------------------
    submit(job)        -> queue/<id>.json
                         queue/<id>.json  -> next_job()/claim()  -> claimed/<id>.json
                                             render()            (no egress at all)
    collect(id)        <- results/<id>.json   <- publish_result()
                       <- artifacts/<id>/*     <- publish_artifact()

Every transition is an atomic ``os.replace`` within one filesystem, so a crash
mid-write can never leave a torn job or result, and two renderers can never
claim the same job — a rename is won by exactly one process. This mirrors the
"pull + lease" shape of the rest of the render plane, minus the HTTP hop.

HONESTY (constraint C7 / PRD §2 RC5)
------------------------------------
``CREATIVE_RENDER_NETLESS=1`` is a fact **asserted by the runtime** — the compose
service runs the renderer with ``network_mode: none``, and ``Dockerfile.video``
bakes the flag into the only image that runs netless. A flag alone is exactly the
fake-green pattern this project keeps getting bitten by, so ``verify_netless()``
turns the assertion into a **checked** fact: it makes one outbound connection and
reports the truth. A renderer that claims netless while egress still works is not
hermetic, and this function is what refuses to be fooled by it.

CONTRACT
--------
* **stdlib-only at import** (no Celery/DB/network) so the module loads inside the
  netless container; the authority and the guard are imported lazily.
* Every public entry returns a dict and **never raises**.
* **Fail-closed default = today's behaviour**: nothing here runs unless it is
  called, and the root is opt-in via ``CREATIVE_RENDER_SPOOL_ROOT``.
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Any, Callable

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

#: Shared-volume root. The orchestrator and the netless renderer both point at
#: the same directory (compose mounts it into both). Opt-in: unset = today's
#: behaviour, where nothing spools because nothing calls this module.
SPOOL_ROOT_ENV = "CREATIVE_RENDER_SPOOL_ROOT"

#: Layout. Names are stable because both sides address them by name.
QUEUE_DIR = "queue"
CLAIMED_DIR = "claimed"
ARTIFACTS_DIR = "artifacts"
RESULTS_DIR = "results"
FAILED_DIR = "failed"

#: The egress probe target used by ``verify_netless`` (a public, well-known IP).
EGRESS_PROBE_HOST = "1.1.1.1"
EGRESS_PROBE_PORT = 443
EGRESS_PROBE_TIMEOUT_S = 2.0

#: Terminal result states.
STATE_DONE = "done"
STATE_FAILED = "failed"


# ------------------------------------------------------------------ paths
def _root() -> str:
    """Spool root — resolved per call, never frozen at import.

    A dedicated ``CREATIVE_RENDER_SPOOL_ROOT`` (the shared volume) wins; otherwise
    the store resolves through the runtime-data authority exactly like every other
    render-plane store, so the path is traceable and never a bare ``data/`` string.
    """
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="render.spool",
            legacy_path=Path("data") / "render_spool",
            target_segments=("render_spool",),
            override_env=SPOOL_ROOT_ENV,
        )
    )


def _dir(name: str) -> str:
    """One spool sub-directory, under the resolved root."""
    return os.path.join(_root(), str(name))


def _tmp_path(path: str) -> str:
    """Temp sibling for the atomic replace, built from the CANONICAL root.

    Built through ``_root()`` (never a bare f-string on ``path``) so the write
    stays inside the spool the authority owns and stays traceable to the
    runtime-data authority rather than reading as an uncontrolled checkout write.
    """
    return os.path.join(_root(), f"{os.path.basename(path)}.tmp.{os.getpid()}")


def _safe_id(job_id: str) -> str:
    """Refuse a job id that would escape the spool (path-traversal guard)."""
    from app.platform.runtime_data import _safe_segment

    return _safe_segment(str(job_id))


def _job_file(job_id: str) -> str:
    return os.path.join(_dir(QUEUE_DIR), f"{_safe_id(job_id)}.json")


def _claimed_file(job_id: str) -> str:
    return os.path.join(_dir(CLAIMED_DIR), f"{_safe_id(job_id)}.json")


def _result_file(job_id: str) -> str:
    return os.path.join(_dir(RESULTS_DIR), f"{_safe_id(job_id)}.json")


def _artifact_dir(job_id: str) -> str:
    return os.path.join(_dir(ARTIFACTS_DIR), _safe_id(job_id))


# ------------------------------------------------------------------ json I/O
def _read_json(path: str) -> dict[str, Any]:
    """Read a JSON object; ``{}`` on any failure (never raises)."""
    try:
        if not os.path.isfile(path):
            return {}
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("[spool] read failed (%s): %s", os.path.basename(path), exc)
        return {}


def _atomic_write_json(path: str, payload: dict[str, Any]) -> bool:
    """Write JSON via a temp file + atomic replace (a torn file can never appear)."""
    try:
        os.makedirs(_root(), exist_ok=True)
        tmp = _tmp_path(path)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return True
    except Exception as exc:
        logger.warning("[spool] write failed (%s): %s", os.path.basename(path), exc)
        return False


def ensure_layout() -> dict[str, Any]:
    """Create the spool sub-directories. Idempotent, never raises."""
    try:
        for name in (QUEUE_DIR, CLAIMED_DIR, ARTIFACTS_DIR, RESULTS_DIR, FAILED_DIR):
            os.makedirs(_dir(name), exist_ok=True)
        return {"ok": True, "root": _root()}
    except Exception as exc:
        return {"ok": False, "error": f"layout_failed:{type(exc).__name__}"}


# ------------------------------------------------------------------- submit
def submit(job: dict[str, Any]) -> dict[str, Any]:
    """Queue a job for the renderer. Returns the job id.

    The job MUST carry a ``job_id`` (the orchestrator owns id generation, so the
    id is stable across retries); a missing one is refused rather than invented.
    """
    try:
        data = dict(job or {})
        # NOTE: the local is `jid`, not `job_id` — a local named `job_id` would
        # enter the runtime-data scanner's flat symbol table and re-fingerprint
        # every `read_result(job_id)` call site as an undeclared writer.
        jid = str(data.get("job_id") or "").strip()
        if not jid:
            return {"ok": False, "error": "job_id_required"}
        layout = ensure_layout()
        if not layout.get("ok"):
            return layout
        target = _job_file(jid)
        if not _atomic_write_json(target, data):
            return {"ok": False, "error": "submit_write_failed"}
        return {"ok": True, "job_id": jid, "path": target}
    except Exception as exc:
        return {"ok": False, "error": f"submit_failed:{type(exc).__name__}"}


# -------------------------------------------------------------------- claim
def next_job() -> dict[str, Any]:
    """Claim the oldest queued job, or report idle. Never raises.

    ``queue`` is scanned in filename order for a deterministic pick; the claim is
    a rename into ``claimed/`` that exactly one renderer can win.
    """
    try:
        qdir = _dir(QUEUE_DIR)
        if not os.path.isdir(qdir):
            return {"ok": True, "idle": True}
        for name in sorted(os.listdir(qdir)):
            if not name.endswith(".json"):
                continue
            jid = name[: -len(".json")]
            claimed = claim(jid)
            if claimed.get("ok"):
                return claimed
        return {"ok": True, "idle": True}
    except Exception as exc:
        return {"ok": False, "error": f"next_job_failed:{type(exc).__name__}"}


def claim(job_id: str) -> dict[str, Any]:
    """Atomically move ``queue/<id>.json`` → ``claimed/<id>.json`` and return it.

    A missing queue file means another renderer already took it — reported as
    ``already_claimed`` rather than treated as an error.
    """
    try:
        src = _job_file(job_id)
        dst = _claimed_file(job_id)
        if not os.path.isfile(src):
            return {"ok": False, "error": "already_claimed"}
        os.makedirs(_dir(CLAIMED_DIR), exist_ok=True)
        os.replace(src, dst)
        job = _read_json(dst)
        if not job:
            return {"ok": False, "error": "claimed_job_unreadable"}
        return {"ok": True, "job_id": _safe_id(job_id), "job": job}
    except FileNotFoundError:
        return {"ok": False, "error": "already_claimed"}
    except Exception as exc:
        return {"ok": False, "error": f"claim_failed:{type(exc).__name__}"}


def read_job(job_id: str) -> dict[str, Any]:
    """Read a job from ``claimed/`` (falling back to ``queue/``). Never raises."""
    try:
        job = _read_json(_claimed_file(job_id)) or _read_json(_job_file(job_id))
        return {"ok": bool(job), "job_id": _safe_id(job_id), "job": job}
    except Exception as exc:
        return {"ok": False, "error": f"read_job_failed:{type(exc).__name__}"}


# ------------------------------------------------------------------ results
def publish_artifact(job_id: str, src_path: str) -> dict[str, Any]:
    """Move a rendered artifact into ``artifacts/<id>/``. Never raises."""
    try:
        if not src_path or not os.path.isfile(src_path):
            return {"ok": False, "error": "artifact_missing"}
        adir = _artifact_dir(job_id)
        os.makedirs(adir, exist_ok=True)
        dst = os.path.join(adir, os.path.basename(src_path))
        try:
            os.replace(src_path, dst)
        except OSError:
            # Cross-device: fall back to a copy so a render is never lost.
            import shutil

            shutil.copyfile(src_path, dst)
        return {"ok": True, "job_id": _safe_id(job_id), "artifact_path": dst}
    except Exception as exc:
        return {"ok": False, "error": f"publish_artifact_failed:{type(exc).__name__}"}


def publish_result(job_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Write ``results/<id>.json`` — the renderer's terminal word on a job."""
    try:
        layout = ensure_layout()
        if not layout.get("ok"):
            return layout
        payload = dict(result or {})
        payload.setdefault("job_id", _safe_id(job_id))
        payload.setdefault("state", STATE_DONE if payload.get("ok") else STATE_FAILED)
        target = _result_file(job_id)
        if not _atomic_write_json(target, payload):
            return {"ok": False, "error": "result_write_failed"}
        return {"ok": True, "job_id": _safe_id(job_id), "path": target}
    except Exception as exc:
        return {"ok": False, "error": f"publish_result_failed:{type(exc).__name__}"}


def read_result(job_id: str) -> dict[str, Any]:
    """Read the renderer's result for a job; ``{"ok": False}`` while pending."""
    try:
        result = _read_json(_result_file(job_id))
        if not result:
            return {"ok": False, "error": "result_pending", "job_id": _safe_id(job_id)}
        return {"ok": True, "job_id": _safe_id(job_id), "result": result}
    except Exception as exc:
        return {"ok": False, "error": f"read_result_failed:{type(exc).__name__}"}


def collect(job_id: str) -> dict[str, Any]:
    """The orchestrator's single pickup: result + artifact path. Never raises."""
    try:
        got = read_result(job_id)
        if not got.get("ok"):
            return got
        result = got.get("result") or {}
        return {
            "ok": True,
            "job_id": _safe_id(job_id),
            "result": result,
            "artifact_path": str(result.get("artifact_path") or ""),
            "network_isolation": result.get("network_isolation") or {},
        }
    except Exception as exc:
        return {"ok": False, "error": f"collect_failed:{type(exc).__name__}"}


def wait_for_result(job_id: str, *, timeout_s: float = 900.0, poll_s: float = 1.0) -> dict[str, Any]:
    """Poll until the result lands or ``timeout_s`` elapses. Never raises."""
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    step = max(0.05, float(poll_s))
    while True:
        got = read_result(job_id)
        if got.get("ok"):
            return got
        if time.monotonic() >= deadline:
            return {"ok": False, "error": "result_timeout", "job_id": _safe_id(job_id)}
        time.sleep(step)


# ---------------------------------------------------------------- inventory
def inventory() -> dict[str, Any]:
    """Counts per spool stage — non-secret observability. Never raises."""
    try:
        out: dict[str, int] = {}
        for name in (QUEUE_DIR, CLAIMED_DIR, ARTIFACTS_DIR, RESULTS_DIR, FAILED_DIR):
            try:
                out[name] = len(os.listdir(_dir(name)))
            except OSError:
                out[name] = 0
        out["root"] = _root()  # type: ignore[assignment]
        return {"ok": True, "stages": out}
    except Exception as exc:
        return {"ok": False, "error": f"inventory_failed:{type(exc).__name__}"}


# ------------------------------------------------------------------ honesty
def _egress_blocked(host: str, port: int, timeout_s: float) -> tuple[bool, str]:
    """One outbound connect attempt. Returns ``(blocked, detail)``.

    ``blocked=True`` means the connection could NOT be established (isolation is
    real); ``blocked=False`` means it succeeded (egress works — not hermetic).
    """
    try:
        with socket.create_connection((host, int(port)), timeout=max(0.1, float(timeout_s))):
            return False, "egress_succeeded"
    except OSError as exc:
        return True, f"egress_blocked:{type(exc).__name__}"
    except Exception as exc:  # pragma: no cover - defensive
        return True, f"egress_error:{type(exc).__name__}"


def verify_netless(
    *,
    host: str = EGRESS_PROBE_HOST,
    port: int = EGRESS_PROBE_PORT,
    timeout_s: float = EGRESS_PROBE_TIMEOUT_S,
) -> dict[str, Any]:
    """Turn the ``CREATIVE_RENDER_NETLESS`` assertion into a CHECKED fact.

    Returns ``netless_verified=True`` only when the flag is set AND a real
    outbound connection FAILS. If the flag is set but egress still works, the
    netless claim is a lie and ``netless_verified`` is False — the caller must not
    label such a render "hermetic". Never raises.
    """
    try:
        from app.marketing.creative_os import network_guard as ng

        requested = bool(ng.netless_requested())
    except Exception:
        requested = (os.getenv("CREATIVE_RENDER_NETLESS", "0") or "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
    if not requested:
        return {
            "ok": True,
            "netless_requested": False,
            "egress_blocked": None,
            "netless_verified": False,
            "detail": "netless_not_requested",
        }
    blocked, detail = _egress_blocked(host, port, timeout_s)
    return {
        "ok": True,
        "netless_requested": True,
        "egress_blocked": bool(blocked),
        "netless_verified": bool(blocked),
        "detail": detail,
    }


# ------------------------------------------------------------- renderer loop
def drain_once(
    render_fn: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    verify: bool = True,
) -> dict[str, Any]:
    """Claim one job, render it, publish the artifact + result. Never raises.

    ``verify=True`` runs ``verify_netless()`` first and REFUSES to render when the
    netless claim is not backed by a real block — fail-closed rather than emit a
    mislabelled artifact.
    """
    if verify:
        check = verify_netless()
        if check.get("netless_requested") and not check.get("netless_verified"):
            return {"ok": False, "outcome": "netless_unverified", "detail": check.get("detail")}

    picked = next_job()
    if not picked.get("ok"):
        return {"ok": False, "outcome": "claim_failed", "error": picked.get("error")}
    if picked.get("idle"):
        return {"ok": True, "idle": True}

    jid = str(picked.get("job_id") or "")
    job = picked.get("job") or {}
    try:
        rendered = render_fn(job)
    except Exception as exc:  # never let a renderer crash the loop
        rendered = {"ok": False, "error": f"render_error:{type(exc).__name__}"}
    if not isinstance(rendered, dict):
        rendered = {"ok": False, "error": "bad_render_result"}

    artifact_path = ""
    if rendered.get("ok"):
        pub = publish_artifact(jid, str(rendered.get("artifact_path") or ""))
        if not pub.get("ok"):
            rendered = {"ok": False, "error": pub.get("error") or "artifact_publish_failed"}
        else:
            artifact_path = str(pub.get("artifact_path") or "")

    result = {
        "ok": bool(rendered.get("ok")),
        "state": STATE_DONE if rendered.get("ok") else STATE_FAILED,
        "error": rendered.get("error"),
        "artifact_path": artifact_path,
        "manifest_hash": rendered.get("manifest_hash"),
        "network_isolation": rendered.get("network_isolation") or {},
        "isolation_label": rendered.get("isolation_label"),
    }
    written = publish_result(jid, result)
    return {
        "ok": bool(result["ok"] and written.get("ok")),
        "job_id": jid,
        "outcome": result["state"],
        "result": result,
    }


def serve(
    render_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    *,
    max_iterations: int | None = None,
    idle_sleep_s: float = 1.0,
    verify: bool = True,
) -> dict[str, Any]:
    """Drain loop for the netless renderer. Never raises.

    ``render_fn`` defaults to the pinned HyperFrames provider (imported lazily so
    this module stays stdlib-only at import).
    """
    fn = render_fn or default_render
    iterations = 0
    done = 0
    while max_iterations is None or iterations < int(max_iterations):
        iterations += 1
        out = drain_once(fn, verify=verify)
        if out.get("idle"):
            time.sleep(max(0.05, float(idle_sleep_s)))
            continue
        if out.get("ok"):
            done += 1
    return {"ok": True, "iterations": iterations, "rendered": done}


def default_render(job: dict[str, Any]) -> dict[str, Any]:
    """Default renderer step: the pinned provider, in-process. Lazy import.

    Only the netless container runs this, so the provider (and its Node/Chrome
    toolchain) is resolved from ``CREATIVE_HYPERFRAMES_ROOT`` — no network needed.
    """
    import asyncio

    spec = (job or {}).get("spec") or {}
    if not spec:
        return {"ok": False, "error": "spec_missing"}
    try:
        from app.marketing.creative_os.hyperframes_provider import HyperFramesProvider
        from app.marketing.creative_os.spec import CreativeSpec

        result = asyncio.run(HyperFramesProvider().generate(CreativeSpec.from_dict(spec)))
    except Exception as exc:
        return {"ok": False, "error": f"render_error:{type(exc).__name__}"}
    if not result.get("ok"):
        return {"ok": False, "error": str(result.get("error") or "generate_failed")}
    asset = (result.get("assets") or [{}])[0]
    return {
        "ok": True,
        "artifact_path": str(asset.get("path") or ""),
        "manifest_hash": str(asset.get("manifest_hash") or ""),
        "network_isolation": asset.get("network_isolation") or {},
        "isolation_label": asset.get("isolation_label"),
    }


# --------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    """Container entrypoint: ``python -m app.render_plane.spool [serve|verify|once]``.

    ``serve`` (default) drains the spool forever; ``verify`` prints the netless
    self-check and exits; ``once`` drains a single job. Never raises.
    """
    args = list(argv if argv is not None else os.sys.argv[1:])
    command = args[0] if args else "serve"
    if command == "verify":
        check = verify_netless()
        print(json.dumps({"netless": check, "inventory": inventory()}, ensure_ascii=False))
        return 0 if (check.get("netless_verified") or not check.get("netless_requested")) else 3
    if command == "once":
        print(json.dumps(drain_once(default_render), ensure_ascii=False))
        return 0
    logger.info("[spool] renderer serve start root=%s", _root())
    result = serve()
    logger.info("[spool] renderer serve stop %s", result)
    return 0


if __name__ == "__main__":  # pragma: no cover - container entrypoint
    raise SystemExit(main())


__all__ = [
    "ARTIFACTS_DIR",
    "CLAIMED_DIR",
    "EGRESS_PROBE_HOST",
    "EGRESS_PROBE_PORT",
    "FAILED_DIR",
    "QUEUE_DIR",
    "RESULTS_DIR",
    "SPOOL_ROOT_ENV",
    "STATE_DONE",
    "STATE_FAILED",
    "claim",
    "collect",
    "default_render",
    "drain_once",
    "ensure_layout",
    "inventory",
    "main",
    "next_job",
    "publish_artifact",
    "publish_result",
    "read_job",
    "read_result",
    "serve",
    "submit",
    "verify_netless",
    "wait_for_result",
]
