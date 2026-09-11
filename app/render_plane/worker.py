"""Local render-worker loop (T02): journal → lease → render → upload → complete.

The worker is the only component that runs on the render box. It **pulls** work
(the VPS never dials in), renders locally under ``network_guard``, and reports
completion idempotently. A local **journal** of in-flight jobs lets a restarted
worker reconcile what it was doing: a job it still owns is resumed, a job whose
lease was reclaimed (``state != leased``) is abandoned rather than double-rendered.

The render and upload steps are **injectable** so the loop is testable without a
renderer, a network, or a VPS. Every public entry returns a dict and never raises.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

JOURNAL_ENV = "RENDER_PLANE_JOURNAL_ROOT"
_ACTIVE_STATES = ("leased", "rendering", "uploading")


# ------------------------------------------------------------------ journal
def _journal_dir() -> str:
    """Per-worker journal directory — resolved per call, never frozen.

    Honours the subsystem root convention: a dedicated ``RENDER_PLANE_JOURNAL_ROOT``
    wins, otherwise ``CREATIVE_LEDGER_ROOT`` (the creative_os test fixture) keeps
    the journal isolated with the rest of the subsystem.
    """
    from app.platform import runtime_data_authority as _auth

    override = JOURNAL_ENV
    if not os.getenv(override) and os.getenv("CREATIVE_LEDGER_ROOT"):
        override = "CREATIVE_LEDGER_ROOT"
    return str(
        _auth.resolve_store_path(
            store_id="render.plane_jobs",
            legacy_path=Path("data") / "render_plane" / "journal",
            target_segments=("render_plane", "journal"),
            override_env=override,
        )
    )


def _safe_stem(value: str) -> str:
    from app.platform.runtime_data import _safe_segment

    return _safe_segment(value)


def journal_path(worker_id: str) -> str:
    """Absolute path of a worker's journal file (call-time resolved).

    Raises ``RuntimeDataError`` for an unsafe worker id — a deliberate
    path-traversal guard, mirroring ``learning_store.learning_path``.
    """
    from app.platform.runtime_data import RuntimeDataError

    try:
        stem = _safe_stem(worker_id)
    except RuntimeDataError:
        raise
    except Exception as exc:
        raise RuntimeDataError(f"unsafe worker id: {worker_id!r}") from exc
    return os.path.join(_journal_dir(), f"{stem}.json")


class RenderWorker:
    """One local render worker. Construct with a client; run ``run_once`` in a loop."""

    def __init__(
        self,
        worker_id: str,
        *,
        client: Any | None = None,
        render_fn: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
        upload_fn: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
        max_output_mb: int | None = None,
    ) -> None:
        self.worker_id = str(worker_id or "").strip() or "worker-unknown"
        if client is None:
            from app.render_plane.client import RenderPlaneClient

            client = RenderPlaneClient()
        self.client = client
        self.render_fn = render_fn or _default_render
        self.upload_fn = upload_fn or _default_upload
        self.max_output_mb = int(max_output_mb or _max_output_mb())

    # ------------------------------------------------------------- journal I/O
    def _journal_file(self) -> str | None:
        try:
            return journal_path(self.worker_id)
        except Exception as exc:
            logger.warning("[render_plane] journal path unavailable: %s", exc)
            return None

    def _read_journal(self) -> dict[str, Any]:
        path = self._journal_file()
        if not path or not os.path.isfile(path):
            return {"inflight": {}}
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and isinstance(data.get("inflight"), dict):
                return data
        except Exception as exc:
            logger.warning("[render_plane] journal read failed: %s", exc)
        return {"inflight": {}}

    def _write_journal(self, data: dict[str, Any]) -> bool:
        path = self._journal_file()
        if not path:
            return False
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            os.replace(tmp, path)
            return True
        except Exception as exc:
            logger.warning("[render_plane] journal write failed: %s", exc)
            return False

    def _note_inflight(self, job_id: str, attempt: int) -> None:
        data = self._read_journal()
        data.setdefault("inflight", {})[str(job_id)] = {"attempt": int(attempt or 0)}
        self._write_journal(data)

    def _clear_inflight(self, job_id: str) -> None:
        data = self._read_journal()
        inflight = data.setdefault("inflight", {})
        if str(job_id) in inflight:
            inflight.pop(str(job_id), None)
            self._write_journal(data)

    # ----------------------------------------------------------------- recovery
    def recover_journal(self) -> dict[str, Any]:
        """Re-read the local journal of in-flight job ids. Never raises."""
        data = self._read_journal()
        inflight = data.get("inflight") or {}
        return {"ok": True, "inflight": inflight, "count": len(inflight)}

    def recover(self) -> dict[str, Any]:
        """Resume jobs we still own; abandon any whose lease was reclaimed.

        This is the guarantee that a restarted worker cannot double-render: if the
        VPS no longer shows the job as leased by us, the attempt is stale and is
        dropped, never re-run blindly.
        """
        rec = self.recover_journal()
        recovered: list[str] = []
        abandoned: list[str] = []
        for job_id in list((rec.get("inflight") or {}).keys()):
            try:
                st = self.client.status(job_id)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("[render_plane] recover status failed: %s", exc)
                continue
            job = st.get("job") or {}
            if (
                job.get("state") in _ACTIVE_STATES
                and str(job.get("lease_owner") or "") == self.worker_id
            ):
                recovered.append(job_id)
            else:
                self._clear_inflight(job_id)
                abandoned.append(job_id)
        return {"ok": True, "recovered": recovered, "abandoned": abandoned}

    # ------------------------------------------------------------------ steps
    def lease_next(self) -> dict[str, Any]:
        """Lease the next queued job via the VPS. Never raises."""
        try:
            return self.client.lease_next(self.worker_id)
        except Exception as exc:
            return {"ok": False, "error": f"lease_error:{type(exc).__name__}"}

    def render(self, job: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
        try:
            out = self.render_fn(job, spec)
            return out if isinstance(out, dict) else {"ok": False, "error": "bad_render_result"}
        except Exception as exc:
            logger.warning("[render_plane] render failed: %s", exc)
            return {"ok": False, "error": f"render_error:{type(exc).__name__}"}

    def upload(self, job: dict[str, Any], artifact_path: str) -> dict[str, Any]:
        try:
            out = self.upload_fn(job, artifact_path)
            return out if isinstance(out, dict) else {"ok": False, "error": "bad_upload_result"}
        except Exception as exc:
            logger.warning("[render_plane] upload failed: %s", exc)
            return {"ok": False, "error": f"upload_error:{type(exc).__name__}"}

    def run_once(self) -> dict[str, Any]:
        """Lease → fetch → render → upload → complete ONE job. Never raises.

        Returns ``{"ok": True, "idle": True}`` when the queue is empty.
        """
        lease = self.lease_next()
        if not lease.get("ok"):
            return {"ok": False, "outcome": "lease_failed", "error": lease.get("error")}
        job = lease.get("job")
        if not job:
            return {"ok": True, "idle": True}

        job_id = str(job.get("job_id") or "")
        attempt = int(job.get("attempt") or 0)
        token = str(lease.get("lease_token") or "")
        self._note_inflight(job_id, attempt)

        try:
            fetched = self.client.fetch(job_id)
            spec = (fetched or {}).get("spec") or {}

            rend = self.render(job, spec)
            if not rend.get("ok"):
                self.client.fail(
                    job_id=job_id,
                    worker=self.worker_id,
                    error=str(rend.get("error") or "render_failed"),
                    retryable=True,
                )
                return {
                    "ok": False,
                    "job_id": job_id,
                    "outcome": "render_failed",
                    "error": rend.get("error"),
                }

            artifact_path = str(rend.get("artifact_path") or "")
            up = self.upload(job, artifact_path)
            if not up.get("ok"):
                self.client.fail(
                    job_id=job_id,
                    worker=self.worker_id,
                    error=str(up.get("error") or "upload_failed"),
                    retryable=True,
                )
                return {
                    "ok": False,
                    "job_id": job_id,
                    "outcome": "upload_failed",
                    "error": up.get("error"),
                }

            done = self.client.complete(
                job_id=job_id,
                worker=self.worker_id,
                revision=int(job.get("revision") or 0),
                attempt=attempt,
                sha256=str(up.get("sha256") or ""),
                manifest_hash=str(rend.get("manifest_hash") or ""),
                artifact_path=str(up.get("artifact_path") or artifact_path),
                artifact_bytes=int(up.get("bytes") or 0),
                network_isolation=rend.get("network_isolation") or {},
                lease_token=token,
            )
            if done.get("ok"):
                self._clear_inflight(job_id)
            return {
                "ok": bool(done.get("ok")),
                "job_id": job_id,
                "outcome": "completed" if done.get("ok") else "complete_rejected",
                "complete": done,
            }
        except Exception as exc:
            logger.warning("[render_plane] run_once failed: %s", exc)
            return {
                "ok": False,
                "job_id": job_id,
                "outcome": "error",
                "error": f"{type(exc).__name__}: {exc}"[:200],
            }

    def run(self, *, max_iterations: int | None = None) -> dict[str, Any]:
        """Run the loop until the queue is idle or ``max_iterations`` is reached."""
        iterations = 0
        completed = 0
        idle = False
        while max_iterations is None or iterations < int(max_iterations):
            iterations += 1
            out = self.run_once()
            if out.get("idle"):
                idle = True
                break
            if out.get("ok"):
                completed += 1
        return {
            "ok": True,
            "iterations": iterations,
            "completed": completed,
            "idle": idle,
            "worker_id": self.worker_id,
        }


# ------------------------------------------------------------------ defaults
def _max_output_mb() -> int:
    try:
        return max(1, min(2048, int(os.getenv("CREATIVE_HYPERFRAMES_MAX_OUTPUT_MB", "220"))))
    except Exception:
        return 220


def _default_render(job: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Default render step: run the pinned HyperFrames provider in-process."""
    import asyncio

    if not spec:
        return {"ok": False, "error": "spec_missing"}
    try:
        from app.marketing.creative_os.hyperframes_provider import HyperFramesProvider
        from app.marketing.creative_os.spec import CreativeSpec

        creative_spec = CreativeSpec.from_dict(spec)
        result = asyncio.run(HyperFramesProvider().generate(creative_spec))
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


def _default_upload(job: dict[str, Any], artifact_path: str) -> dict[str, Any]:
    """Default upload step: compute the verifiable descriptor of the artifact.

    The byte movement itself is performed by the transport / spool (T07); what
    matters here is that the descriptor the worker reports is hash-derived, so the
    VPS can reject a corrupted artifact rather than accept it.
    """
    from app.render_plane import transport

    desc = transport.describe_transfer(artifact_path)
    if not desc.get("ok"):
        return {"ok": False, "error": desc.get("error") or "artifact_unreadable"}
    return {
        "ok": True,
        "artifact_path": str(artifact_path),
        "sha256": desc.get("sha256"),
        "bytes": desc.get("size"),
        "chunks": desc.get("total_chunks"),
    }


__all__ = [
    "JOURNAL_ENV",
    "RenderWorker",
    "journal_path",
]
