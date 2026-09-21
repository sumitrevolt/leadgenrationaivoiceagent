"""Key Manager Agent — Secure API key management for LeadGen AI.

Manages TypeSafe and other API keys without exposing them to chat/logs.
Owner-only access via admin API and UI.

Security guarantees (P0 hardening, 2026-09-21):
- Keys never in chat, logs, or git history
- Keys ENCRYPTED AT REST via Fernet (KEYS_MASTER_KEY env var, injected on the
  VPS host, external to the store). When no master key is configured, WRITE
  OPERATIONS FAIL CLOSED (503) instead of storing plaintext.
- Legacy plaintext entries are flagged ``ROTATION_REQUIRED`` and re-encrypted
  on the next authorized write (migration path).
- Atomic writes (tmp + os.replace) with 0600 perms on POSIX.
- Audit trail for all access — redacted, no key prefixes/suffixes ever.
- OWNER-ONLY API/UI access: every route requires the ADMIN_API_KEY
  (X-API-Key header) via ``require_api_key`` — fail-closed when unset.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.middleware import require_api_key  # owner-only gate (X-API-Key / ADMIN_API_KEY)

logger = logging.getLogger(__name__)

# Canonical key storage path (outside git, server-side only)
KEYS_DIR = Path("/opt/leadgen/secrets")
KEYS_FILE = KEYS_DIR / "keys.json"
AUDIT_LOG = KEYS_DIR / "audit.log"

# Value marker for encrypted-at-rest payloads. Legacy entries without this
# marker are plaintext and must be flagged ROTATION_REQUIRED.
_ENCRYPTED_MARKER = "fm1:"  # "format v1"


class PlaintextStorageError(RuntimeError):
    """Raised when a write would persist a key unencrypted (fail-closed)."""


class KeyStoreUnreadableError(RuntimeError):
    """Raised when the key store exists but cannot be parsed.

    Returning an empty dict in this situation would let the next set_key()
    overwrite every other stored key — silent multi-key data loss.
    """


class KeyManagerAgent:
    """Manages API keys securely without exposing to chat/logs."""

    def __init__(self):
        self.keys_file = KEYS_FILE
        self.audit_log = AUDIT_LOG
        self._ensure_dirs()

    # ── master key / Fernet ─────────────────────────────────────────

    @staticmethod
    def _fernet() -> Any | None:
        """Load the Fernet cipher from the KEYS_MASTER_KEY env var.

        The master key is injected by the host/secret store — it must NEVER
        live in keys.json or be derivable from the store.
        """
        raw = os.environ.get("KEYS_MASTER_KEY", "").strip()
        if not raw:
            return None
        try:
            from cryptography.fernet import Fernet

            return Fernet(raw.encode())
        except Exception:
            logger.error("KEYS_MASTER_KEY is set but is not a valid Fernet key")
            return None

    def _encrypt_value(self, plain: str) -> str:
        f = self._fernet()
        if f is None:
            raise PlaintextStorageError(
                "KEYS_MASTER_KEY not configured (or invalid) — refusing to store key in plaintext"
            )
        return _ENCRYPTED_MARKER + f.encrypt(plain.encode()).decode()

    def _decrypt_value(self, stored: str) -> str | None:
        if not stored:
            return None
        if not stored.startswith(_ENCRYPTED_MARKER):
            return None  # legacy plaintext — caller must treat as ROTATION_REQUIRED
        f = self._fernet()
        if f is None:
            return None  # master key gone; value is unreadable, not plaintext
        try:
            return f.decrypt(stored[len(_ENCRYPTED_MARKER) :]).decode()
        except Exception:
            return None

    def _is_encrypted(self, stored: str | None) -> bool:
        return bool(stored and stored.startswith(_ENCRYPTED_MARKER))

    def _ensure_dirs(self) -> None:
        """Create secrets directory if missing."""
        try:
            KEYS_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Fallback to app directory if /opt/leadgen not accessible
            self.keys_file = Path("data/secrets/keys.json")
            self.audit_log = Path("data/secrets/audit.log")
            self.keys_file.parent.mkdir(parents=True, exist_ok=True)

    def _log_audit(
        self, action: str, service: str, actor: str, success: bool, note: str = ""
    ) -> None:
        """Log audit event (never logs key values)."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "service": service,
            "actor": actor,
            "success": success,
            "note": note,
        }
        try:
            with open(self.audit_log, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

    def _load_keys(self) -> dict[str, Any]:
        """Load keys from JSON file.

        Raises KeyStoreUnreadableError when the file exists but cannot be
        parsed. Returning {} here would make the next set_key() overwrite every
        other stored key (silent multi-key data loss).
        """
        if not self.keys_file.exists():
            return {}
        try:
            with open(self.keys_file) as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load key store: %s", type(e).__name__)
            raise KeyStoreUnreadableError(
                "Key store exists but could not be parsed; refusing to continue "
                "so existing keys are not silently overwritten."
            ) from e

    def _save_keys(self, keys: dict[str, Any]) -> None:
        """Save keys atomically (tmp + os.replace) to avoid partial-file corruption.

        On POSIX the temp file is chmod 0600 before replace. Windows silently
        skips the chmod (best-effort).
        """
        tmp_path = self.keys_file.with_suffix(".json.tmp")
        try:
            with open(tmp_path, "w") as f:
                json.dump(keys, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass  # Windows / non-POSIX
            os.replace(tmp_path, self.keys_file)
        except Exception as e:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            logger.error(f"Failed to save keys: {e}")
            raise

    def get_key_status_public(self, service: str) -> dict[str, Any]:
        """Redacted key state for owner dashboard/Telegram.

        Returns ONLY non-identifying fields:
            key_slot | storage | rotation_required | last_verified
        Never a prefix, suffix, fingerprint, or raw value.
        """
        keys = self._load_keys()
        stored = keys.get(service, {}).get("value", "")
        present = bool(stored)
        encrypted = self._is_encrypted(stored)
        return {
            "key_slot": service,
            "storage": "encrypted" if encrypted else ("legacy_plaintext" if present else "absent"),
            "rotation_required": present and not encrypted,
            "last_verified": keys.get(service, {}).get("last_verified"),
        }

    def verify_key(self, service: str) -> dict[str, Any]:
        """Verify key status without exposing value.

        Returns redacted state only:
            {
                "present": bool,
                "storage": "encrypted" | "legacy_plaintext" | "absent",
                "rotation_required": bool,   # legacy plaintext entry
                "last_verified": str | None,
                "smoke_test": bool | None
            }

        No key prefix, suffix, or fingerprint is ever returned.
        """
        keys = self._load_keys()
        key_data = keys.get(service, {})
        stored = key_data.get("value", "")

        present = bool(stored)
        encrypted = self._is_encrypted(stored)
        result: dict[str, Any] = {
            "present": present,
            "storage": "encrypted" if encrypted else ("legacy_plaintext" if present else "absent"),
            "rotation_required": present and not encrypted,
            "last_verified": key_data.get("last_verified"),
            "smoke_test": None,
        }

        # Smoke test requires a readable value: encrypted entries with a live
        # master key, or legacy plaintext (which is flagged for rotation).
        if present:
            plain = self._decrypt_value(stored) if encrypted else stored
            if plain:
                try:
                    from app.platform.typesafe_integration import get_typesafe_client

                    client = get_typesafe_client()
                    resp = client.initialize()
                    result["smoke_test"] = resp.success
                    result["last_verified"] = datetime.now(timezone.utc).isoformat()

                    key_data["last_verified"] = result["last_verified"]
                    keys[service] = key_data
                    self._save_keys(keys)

                    self._log_audit("verify", service, "system", resp.success)
                except Exception as e:
                    result["smoke_test"] = False
                    logger.error(f"Smoke test failed for {service}: {e}")
                    self._log_audit("verify", service, "system", False, str(e))

        return result

    def set_key(self, service: str, key: str, actor: str = "owner") -> dict[str, Any]:
        """Set API key (called from VPS/admin UI, NOT from chat).

        P0 hardening: the value is ALWAYS encrypted at rest. If no usable
        master key is configured the write fails closed instead of persisting
        plaintext. Legacy plaintext entries left on disk are left untouched
        and surfaced as ROTATION_REQUIRED by verify/status.
        """
        if not key or len(key) < 8:
            raise ValueError("Key too short")

        # Fail closed: never persist plaintext.
        encrypted = self._encrypt_value(key)

        keys = self._load_keys()
        keys[service] = {
            "value": encrypted,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_verified": None,
        }
        self._save_keys(keys)

        self._log_audit("set", service, actor, True, "Key set (encrypted at rest)")

        return {
            "success": True,
            "service": service,
            "stored": "encrypted",
            "message": "Key stored encrypted at rest (never exposed in plaintext)",
        }

    def rotate_key(self, service: str, new_key: str, actor: str = "owner") -> dict[str, Any]:
        """Rotate API key (old value is discarded; new value encrypted at rest)."""
        # Verify old key exists
        keys = self._load_keys()
        if service not in keys:
            raise ValueError(f"Service {service} not found")

        # Set new key
        result = self.set_key(service, new_key, actor)

        self._log_audit("rotate", service, actor, True, "Key rotated (previous value discarded)")

        return result

    def delete_key(self, service: str, actor: str = "owner") -> dict[str, Any]:
        """Delete API key (mark as INERT)."""
        keys = self._load_keys()
        if service in keys:
            del keys[service]
            self._save_keys(keys)
            self._log_audit("delete", service, actor, True)
            return {"success": True, "service": service}
        return {"success": False, "service": service, "reason": "not_found"}

    def get_audit_log(self, service: str | None = None, limit: int = 50) -> list[dict]:
        """Get audit log (last N entries)."""
        if not self.audit_log.exists():
            return []

        try:
            with open(self.audit_log) as f:
                entries = [json.loads(line) for line in f if line.strip()]
        except Exception:
            return []

        # Filter by service if specified
        if service:
            entries = [e for e in entries if e.get("service") == service]

        # Return last N entries
        return entries[-limit:]

    def deploy_to_env(self, service: str) -> dict[str, Any]:
        """Deploy key to /opt/leadgen/.env (called after set/rotate).

        The .env file is the runtime injection point for the worker process;
        plaintext on disk here is the expected secret mechanism (0600, outside
        git). The value is decrypted from encrypted storage for the write.
        """
        keys = self._load_keys()
        key_data = keys.get(service)

        if not key_data or not key_data.get("value"):
            return {"success": False, "reason": "no_key"}

        stored = key_data["value"]
        plain = self._decrypt_value(stored) if self._is_encrypted(stored) else stored
        if not plain:
            # Cannot read the value (master key gone or corrupted) — fail closed,
            # never deploy an empty/garbage credential.
            return {"success": False, "reason": "value_unreadable"}

        env_file = Path("/opt/leadgen/.env")
        if not env_file.exists():
            return {"success": False, "reason": "env_file_missing"}

        # Read existing .env
        content = env_file.read_text()

        # Replace or append key
        env_var = f"{service.upper()}_API_KEY"
        pattern = rf"^{env_var}=.*$"

        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, f"{env_var}={plain}", content, flags=re.MULTILINE)
        else:
            content += f"\n{env_var}={plain}\n"

        # Backup before write.
        # NOTE: with_suffix() on a dotfile like ".env" yields ".env.env.bak"
        # (pathlib treats the whole name as the stem) — build the name explicitly.
        backup = env_file.with_name(env_file.name + ".bak")
        shutil.copy2(env_file, backup)

        # Write updated .env
        env_file.write_text(content)
        try:
            os.chmod(env_file, 0o600)
        except OSError:
            pass

        self._log_audit("deploy", service, "system", True, f"Deployed to {env_file}")

        return {
            "success": True,
            "service": service,
            "env_file": str(env_file),
            "backup": str(backup),
            "message": "Key deployed to .env (restart container required)",
        }


# Singleton instance
_key_manager: KeyManagerAgent | None = None


def get_key_manager() -> KeyManagerAgent:
    """Get or create singleton KeyManagerAgent."""
    global _key_manager
    if _key_manager is None:
        _key_manager = KeyManagerAgent()
    return _key_manager


# FastAPI router for admin access.
# P0 hardening (2026-09-21): EVERY route requires the owner admin API key
# (ADMIN_API_KEY env / X-API-Key header) via the existing require_api_key
# middleware — fail-closed 401 when the key is unset or wrong.

router = APIRouter(prefix="/api/admin/keys", tags=["Admin - Key Manager"])


def _owner() -> Any:
    """Return the owner-gate Depends instance.

    ``require_api_key()`` already returns a ``Depends(...)`` that raises 401
    when ADMIN_API_KEY is absent or the X-API-Key header doesn't match, and
    returns the client dict on success. Used directly as the route default —
    no extra ``Depends()`` wrap (which would double-wrap and break FastAPI).
    """
    return require_api_key()


def _handle_store_errors(fn):
    """Map key-store exceptions to clean owner-facing HTTP responses.

    Without this, a short key (ValueError) or an unparseable store would
    surface as an opaque 500. Must be applied UNDER the router decorator.
    """

    @functools.wraps(fn)
    def _wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except KeyStoreUnreadableError:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Key store unreadable; refusing to continue so existing keys are "
                    "not silently overwritten. Inspect the store and retry."
                ),
            )
        except PlaintextStorageError:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Key storage not ready: KEYS_MASTER_KEY is not configured or invalid. "
                    "Refusing to persist a key in plaintext. Configure the host master key "
                    "and retry."
                ),
            )
        except ValueError as e:
            detail = str(e)
            status = 404 if "not found" in detail.lower() else 400
            raise HTTPException(status_code=status, detail=detail)

    return _wrapped


@router.get("/status/{service}")
@_handle_store_errors
def get_key_status(
    service: str,
    km: KeyManagerAgent = Depends(get_key_manager),
    _owner_client: dict = _owner(),
):
    """Get redacted key status (no value, no prefix, no fingerprint)."""
    return km.verify_key(service)


@router.get("/redacted/{service}")
@_handle_store_errors
def get_key_redacted(
    service: str,
    km: KeyManagerAgent = Depends(get_key_manager),
    _owner_client: dict = _owner(),
):
    """Owner-visible logical slot health for dashboard/Telegram (non-identifying)."""
    return km.get_key_status_public(service)


@router.post("/set")
@_handle_store_errors
def set_key(
    payload: dict,
    km: KeyManagerAgent = Depends(get_key_manager),
    _owner_client: dict = _owner(),
):
    """Set key (owner-only, from admin UI; stored encrypted at rest)."""
    service = payload.get("service")
    key = payload.get("key")
    if not service or not key:
        raise HTTPException(status_code=400, detail="service and key required")
    return km.set_key(service, key, actor="admin_ui")


@router.post("/rotate")
@_handle_store_errors
def rotate_key(
    payload: dict,
    km: KeyManagerAgent = Depends(get_key_manager),
    _owner_client: dict = _owner(),
):
    """Rotate key (owner-only; new value encrypted at rest)."""
    service = payload.get("service")
    new_key = payload.get("new_key")
    if not service or not new_key:
        raise HTTPException(status_code=400, detail="service and new_key required")
    return km.rotate_key(service, new_key, actor="admin_ui")


@router.post("/deploy/{service}")
@_handle_store_errors
def deploy_key(
    service: str,
    km: KeyManagerAgent = Depends(get_key_manager),
    _owner_client: dict = _owner(),
):
    """Deploy key to .env file (owner-only)."""
    return km.deploy_to_env(service)


@router.get("/audit/{service}")
@_handle_store_errors
def get_audit(
    service: str,
    limit: int = 50,
    km: KeyManagerAgent = Depends(get_key_manager),
    _owner_client: dict = _owner(),
):
    """Get audit log for service (owner-only)."""
    return km.get_audit_log(service, limit)


@router.get("/audit")
@_handle_store_errors
def get_all_audit(
    limit: int = 100,
    km: KeyManagerAgent = Depends(get_key_manager),
    _owner_client: dict = _owner(),
):
    """Get all audit log (owner-only)."""
    return km.get_audit_log(None, limit)


# Export for direct use
KeyManager = KeyManagerAgent
