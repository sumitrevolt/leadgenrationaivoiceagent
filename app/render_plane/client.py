"""Worker-side HTTP client for the render plane (T02).

The local worker dials the VPS; the VPS never dials the worker. The auth token is
read from the environment at call time and is **never** logged or returned — error
strings are passed through :func:`_redact`, which strips the token if a transport
ever echoed it back.

Every public method returns a dict and never raises.
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

BASE_URL_ENV = "RENDER_PLANE_BASE_URL"
TOKEN_ENV = "RENDER_PLANE_WORKER_TOKEN"
TOKEN_HEADER = "X-Render-Plane-Token"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def base_url() -> str:
    """VPS base URL, resolved at call time (never frozen at import)."""
    return (os.getenv(BASE_URL_ENV, "") or DEFAULT_BASE_URL).strip().rstrip("/")


def worker_token() -> str:
    """The shared worker token. Read at call time; never logged."""
    return (os.getenv(TOKEN_ENV) or "").strip()


def _redact(text: str) -> str:
    """Remove the token from any string before it can reach a log or a response."""
    out = str(text or "")
    token = worker_token()
    if token and token in out:
        out = out.replace(token, "***")
    return out[:300]


class RenderPlaneClient:
    """Thin, never-raising HTTP client for the render-plane API."""

    def __init__(self, *, base: str | None = None, token: str | None = None, timeout_s: float = 30.0):
        self._base = (base if base is not None else base_url()).rstrip("/")
        self._token = token if token is not None else worker_token()
        self._timeout = float(timeout_s)

    # ---------------------------------------------------------------- plumbing
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers[TOKEN_HEADER] = self._token
        return headers

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base}{path}"
        try:
            import httpx
        except Exception as exc:  # pragma: no cover - httpx is a hard dep in practice
            return {"ok": False, "error": f"httpx_unavailable:{type(exc).__name__}"}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.request(method, url, headers=self._headers(), json=payload)
            try:
                data = resp.json()
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {"data": data}
            if resp.status_code >= 400 and "ok" not in data:
                data = {"ok": False, "error": f"http_{resp.status_code}"}
            data.setdefault("status_code", resp.status_code)
            return data
        except Exception as exc:
            # Redact: a transport error string must never carry the token.
            return {"ok": False, "error": f"transport_error:{type(exc).__name__}:{_redact(str(exc))}"}

    # ------------------------------------------------------------------- calls
    def lease_next(self, worker: str, *, lease_seconds: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"worker": str(worker)}
        if lease_seconds is not None:
            payload["lease_seconds"] = int(lease_seconds)
        return self._request("POST", "/api/render-plane/lease", payload)

    def heartbeat(
        self, job_id: str, worker: str, *, attempt: int = 0, lease_token: str = ""
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/render-plane/heartbeat",
            {
                "job_id": str(job_id),
                "worker": str(worker),
                "attempt": int(attempt or 0),
                "lease_token": str(lease_token or ""),
            },
        )

    def complete(
        self,
        *,
        job_id: str,
        worker: str,
        revision: int = 0,
        attempt: int = 0,
        sha256: str = "",
        manifest_hash: str = "",
        artifact_path: str = "",
        artifact_bytes: int = 0,
        network_isolation: dict[str, Any] | None = None,
        lease_token: str = "",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/render-plane/complete",
            {
                "job_id": str(job_id),
                "worker": str(worker),
                "revision": int(revision or 0),
                "attempt": int(attempt or 0),
                "sha256": str(sha256 or ""),
                "manifest_hash": str(manifest_hash or ""),
                "artifact_path": str(artifact_path or ""),
                "artifact_bytes": int(artifact_bytes or 0),
                "network_isolation": network_isolation or {},
                "lease_token": str(lease_token or ""),
            },
        )

    def fail(
        self,
        *,
        job_id: str,
        worker: str,
        error: str = "",
        retryable: bool = False,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/render-plane/fail",
            {
                "job_id": str(job_id),
                "worker": str(worker),
                "error": str(error or "")[:400],
                "retryable": bool(retryable),
            },
        )

    def status(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/render-plane/status/{str(job_id)}")

    def fetch(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/render-plane/fetch/{str(job_id)}")


__all__ = [
    "BASE_URL_ENV",
    "DEFAULT_BASE_URL",
    "TOKEN_ENV",
    "TOKEN_HEADER",
    "RenderPlaneClient",
    "base_url",
    "worker_token",
]
