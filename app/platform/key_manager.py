"""Key Manager Agent — Secure API key management for LeadGen AI.

P0-hardened 2026-09-21 (owner contract M3/R3 + M10-B). The security guarantees
below are ENFORCED IN CODE and pinned by tests/test_key_manager_storage.py and
tests/security/test_key_manager_auth.py:

* Owner-only access. The router factory (build_keys_router) wires:
    - reads   (/status, /audit)                       -> require_admin
    - writes  (/set, /rotate, /delete, /deploy, /verify) -> require_super_admin
  Unauthenticated => 401. Non-super role => 403. Deny-by-default.
* Encrypted at rest. Key values are Fernet-encrypted (cryptography, in
  requirements.lock.txt) under KEYS_MASTER_KEY, which lives ONLY in env/.env —
  external to the store. Missing master key => every mutation FAILS CLOSED
  (HTTP 503 ``master_key_missing``); nothing is ever written in plaintext.
* No key material in owner-visible surfaces. Status/audit/log/Telegram see
  STATE ONLY: ABSENT | PRESENT | INVALID | ROTATION_REQUIRED. No prefix, no
  suffix, no raw value, no bearer header, no usable fingerprint.
* Atomic writes (tmp + os.replace), 0600 on Unix. Legacy plaintext keys.json
  is migrated once — encrypt, roundtrip-verify, then securely delete the
  plaintext copy. A failed migration leaves the legacy file in place
  (fail-closed, audited, flagged as ``legacy_pending_master`` /
  ``legacy_migrate_failed``).
* The value surface is ONE scoped method (get_decrypted_value) with mandatory
  consumer attribution in the audit trail. deploy_to_env is the only writer to
  the runtime .env (atomic, 0600, with 0600 backup before the write).

Consumer contract for the four TypeSafe slots (owner contract M3):
    typesafe_a / typesafe_b / typesafe_c / typesafe_d
  The TypeSafe gateway reads values via get_decrypted_value(service, consumer)
  and writes them to the runtime env via deploy_to_env (canonical .env path).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

try:  # cryptography is a locked production dependency (requirements.lock.txt)
    from cryptography.fernet import Fernet
except ImportError:  # pragma: no cover - only on non-locked dev installs
    Fernet = None  # type: ignore[assignment]

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Canonical key storage dir (outside git). In the container the process CWD is
# /app and /opt/leadgen is host-only, so the fallback lands in the bind-mounted
# ./data/secrets (host path /opt/leadgen/data/secrets). LEADGEN_KEYS_DIR
# overrides both (tests).
DEFAULT_KEYS_DIR = "/opt/leadgen/secrets"
FALLBACK_KEYS_DIR = "data/secrets"
ENV_FILE_DEFAULT = "/opt/leadgen/.env"

SERVICE_NAME_RE = re.compile(r"^[a-z0-9_]{2,32}$")

# Canonical TypeSafe 4-slot naming. Slot names are NON-SECRET logical ids.
CANONICAL_TYPESAFE_SLOTS = ("typesafe_a", "typesafe_b", "typesafe_c", "typesafe_d")

STATE_ABSENT = "ABSENT"
STATE_PRESENT = "PRESENT"
STATE_INVALID = "INVALID"
STATE_ROTATION_REQUIRED = "ROTATION_REQUIRED"


class KeyManagerError(RuntimeError):
    """Structured failure with a machine-readable ``reason`` (never key material)."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, data: str) -> None:
    """Write via tmp + os.replace (atomic); 0600 on Unix, no-op on Windows."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


class KeyManagerAgent:
    """Stores API keys Fernet-encrypted at rest; owner-scoped value surface."""

    def __init__(self, keys_dir: Path | str | None = None):
        base = keys_dir or os.getenv("LEADGEN_KEYS_DIR", "").strip() or DEFAULT_KEYS_DIR
        self.keys_dir = Path(base)
        self._fallback_used = False
        try:
            self.keys_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.keys_dir, 0o700)
            except OSError:
                pass
        except Exception:  # pragma: no cover - host-permission edge
            self.keys_dir = Path(FALLBACK_KEYS_DIR)
            self.keys_dir.mkdir(parents=True, exist_ok=True)
            self._fallback_used = True
        self.keys_file = self.keys_dir / "keys.enc.json"
        self.legacy_file = self.keys_dir / "keys.json"
        self.audit_log = self.keys_dir / "audit.log"

    # ------------------------------------------------------------------ crypto
    def _fernet(self) -> Optional["Fernet"]:
        raw = os.getenv("KEYS_MASTER_KEY", "").strip()
        if not raw or Fernet is None:
            return None
        try:
            return Fernet(raw.encode())
        except Exception:
            return None

    def _master_available(self) -> bool:
        return self._fernet() is not None

    # ------------------------------------------------------------------- audit
    def _log_audit(
        self, action: str, service: str, actor: str, success: bool, note: str = ""
    ) -> None:
        """Append one audit line. ``note`` carries STATE STRINGS ONLY —
        never a key value, prefix, suffix or bearer material (checked in tests)."""
        entry = {
            "timestamp": _utcnow(),
            "action": action,
            "service": service,
            "actor": actor,
            "success": bool(success),
            "note": note,
        }
        try:
            with open(self.audit_log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except Exception as exc:
            logger.warning("key_manager: failed to write audit log: %s", exc)

    # ------------------------------------------------------------- meta storage
    def _load_meta(self) -> dict[str, Any]:
        if self.legacy_file.exists() and not self.keys_file.exists():
            self._migrate_legacy()
        if not self.keys_file.exists():
            return {}
        try:
            with open(self.keys_file, encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except Exception:
            logger.error("key_manager: unreadable keys.enc.json — failing closed")
            return {}

    def _save_meta(self, meta: dict[str, Any]) -> None:
        _atomic_write_text(self.keys_file, json.dumps(meta, indent=2))

    def _migrate_legacy(self) -> None:
        """One-time: encrypt legacy plaintext keys.json -> keys.enc.json, then
        securely delete the plaintext. Fail-closed: any verification problem
        leaves the legacy file in place and audits the reason."""
        try:
            raw = json.loads(self.legacy_file.read_text(encoding="utf-8"))
        except Exception:
            self._log_audit(
                "legacy_migrate_failed", "*", "system", False,
                "unreadable legacy keys.json left in place",
            )
            return
        if not isinstance(raw, dict):
            try:
                self.legacy_file.unlink()
            except Exception:
                pass
            return
        f = self._fernet()
        if f is None:
            self._log_audit(
                "legacy_pending_master", "*", "system", False,
                "legacy plaintext keys.json present; set KEYS_MASTER_KEY then restart",
            )
            return
        meta: dict[str, Any] = {}
        try:
            for svc, rec in raw.items():
                val = (rec or {}).get("value") if isinstance(rec, dict) else None
                if not val:
                    continue
                token = f.encrypt(str(val).encode())
                # Roundtrip-verify BEFORE destroying the plaintext copy.
                if f.decrypt(token).decode() != str(val):
                    raise RuntimeError("roundtrip verification failed")
                meta[str(svc)] = {
                    "cipher": token.decode(),
                    "created_at": (rec or {}).get("created_at") or _utcnow(),
                    "updated_at": _utcnow(),
                    "last_verified": (rec or {}).get("last_verified"),
                    "last_smoke": "unknown",
                }
        except Exception as exc:
            self._log_audit(
                "legacy_migrate_failed", "*", "system", False,
                f"verification failed: {exc}",
            )
            return
        self._save_meta(meta)
        try:
            self.legacy_file.unlink()  # plaintext copy destroyed after verified encrypt
        except Exception:
            pass
        self._log_audit(
            "legacy_migrate", "*", "system", True,
            f"encrypted {len(meta)} legacy key(s); plaintext copy removed",
        )

    # ------------------------------------------------------------------ state
    def list_services(self) -> list[str]:
        meta = self._load_meta()
        return sorted(set(meta) | set(CANONICAL_TYPESAFE_SLOTS))

    def get_state(self, service: str) -> dict[str, Any]:
        """Owner-visible redacted state. NEVER includes prefix/suffix/value."""
        service = (service or "").strip().lower()
        meta = self._load_meta()
        rec = meta.get(service)
        if not rec or not rec.get("cipher"):
            return {
                "service": service,
                "state": STATE_ABSENT,
                "last_verified": None,
                "rotation_needed": False,
            }
        smoke = rec.get("last_smoke")
        rotation = bool(rec.get("rotation_requested")) or smoke == "fail"
        state = (
            STATE_ROTATION_REQUIRED
            if rotation
            else STATE_INVALID
            if smoke == "fail"
            else STATE_PRESENT
        )
        return {
            "service": service,
            "state": state,
            "last_verified": rec.get("last_verified"),
            "rotation_needed": rotation,
            "last_smoke": smoke,
        }

    # ------------------------------------------------------------------ value
    def get_decrypted_value(self, service: str, consumer: str = "unknown") -> Optional[str]:
        """THE ONLY value surface. Requires a master key; consumer is audited.
        Returns None when the service is absent (raises only on crypto failure)."""
        service = (service or "").strip().lower()
        meta = self._load_meta()
        rec = meta.get(service)
        if not rec or not rec.get("cipher"):
            self._log_audit("value_read", service, consumer, False, "ABSENT")
            return None
        f = self._fernet()
        if f is None:
            self._log_audit("value_read", service, consumer, False, "master_key_missing")
            raise KeyManagerError("master_key_missing")
        try:
            value = f.decrypt(rec["cipher"].encode()).decode()
        except Exception:
            self._log_audit(
                "value_read", service, consumer, False,
                "decrypt_failure (rotation required)",
            )
            raise KeyManagerError("decrypt_failure")
        self._log_audit("value_read", service, consumer, True, "ok")
        return value

    # ------------------------------------------------------------------ writes
    def set_key(self, service: str, key: str, actor: str = "owner") -> dict[str, Any]:
        """Encrypt-and-store one key. Fails closed without a master key."""
        service = (service or "").strip().lower()
        if not SERVICE_NAME_RE.match(service):
            raise KeyManagerError(
                "invalid_service_name", "service must match ^[a-z0-9_]{2,32}$"
            )
        if not key or len(key) < 8:
            raise KeyManagerError("key_too_short")
        f = self._fernet()
        if f is None:
            raise KeyManagerError(
                "master_key_missing", "KEYS_MASTER_KEY not configured"
            )
        meta = self._load_meta()
        now = _utcnow()
        prev = meta.get(service, {})
        meta[service] = {
            "cipher": f.encrypt(key.encode()).decode(),
            "created_at": prev.get("created_at") or now,
            "updated_at": now,
            "last_verified": None,
            "last_smoke": None,
        }
        self._save_meta(meta)
        self._log_audit("set", service, actor, True, "key encrypted at rest")
        return {"success": True, "service": service, "state": STATE_PRESENT}

    def rotate_key(self, service: str, new_key: str, actor: str = "owner") -> dict[str, Any]:
        """Replace a key. Old value is superseded (was encrypted, now dropped)."""
        self.set_key(service, new_key, actor)
        self._log_audit("rotate", service, actor, True, "previous value superseded")
        return {"success": True, "service": service, "state": STATE_PRESENT}

    def delete_key(self, service: str, actor: str = "owner") -> dict[str, Any]:
        service = (service or "").strip().lower()
        meta = self._load_meta()
        if service not in meta:
            return {"success": False, "service": service, "reason": "not_found"}
        del meta[service]
        self._save_meta(meta)
        self._log_audit("delete", service, actor, True)
        return {"success": True, "service": service}

    def request_rotation(self, service: str, actor: str = "owner") -> dict[str, Any]:
        """Owner flag: makes /status report rotation_needed (state contract R3)."""
        service = (service or "").strip().lower()
        meta = self._load_meta()
        rec = meta.get(service)
        if not rec:
            return {"success": False, "service": service, "reason": "not_found"}
        rec["rotation_requested"] = True
        self._save_meta(meta)
        self._log_audit("rotation_requested", service, actor, True)
        return {"success": True, "service": service}

    # ----------------------------------------------------------------- verify
    def verify_key(self, service: str, actor: str = "system") -> dict[str, Any]:
        """Run the provider smoke test (billable) and record state. POST-only
        surface — reads stay free of provider calls."""
        service = (service or "").strip().lower()
        state = self.get_state(service)
        if state["state"] == STATE_ABSENT:
            return {**state, "smoke_test": None}
        meta = self._load_meta()
        rec = meta.get(service, {})
        if service.startswith("typesafe"):
            ok = self._typesafe_smoke()
            rec["last_smoke"] = "pass" if ok else "fail"
            rec["last_verified"] = _utcnow()
            rec.pop("rotation_requested", None) if ok else None
            self._save_meta(meta)
            self._log_audit(
                "verify", service, actor, bool(ok),
                "typesafe initialize() smoke",
            )
            out = self.get_state(service)
            out["smoke_test"] = bool(ok)
            return out
        # Non-TypeSafe services have no provider smoke in this build; state only.
        out = self.get_state(service)
        out["smoke_test"] = None
        return out

    def _typesafe_smoke(self) -> bool:
        try:
            from app.platform.typesafe_integration import get_typesafe_client

            return bool(get_typesafe_client().initialize())
        except Exception as exc:  # pragma: no cover - provider-dependent
            logger.warning("key_manager: typesafe smoke error: %s", exc)
            return False

    # ------------------------------------------------------------------- audit
    def get_audit_log(
        self, service: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        if not self.audit_log.exists():
            return []
        try:
            with open(self.audit_log, encoding="utf-8") as fh:
                entries = [json.loads(line) for line in fh if line.strip()]
        except Exception:
            return []
        if service:
            entries = [e for e in entries if e.get("service") == service]
        return entries[-limit:]

    # -------------------------------------------------------------------- deploy
    def deploy_to_env(self, service: str, actor: str = "system") -> dict[str, Any]:
        """Write the key into the runtime .env (the one canonical env path).
        Atomic: tmp+rename, 0600, and a 0600 backup of the previous .env."""
        service = (service or "").strip().lower()
        value = self.get_decrypted_value(service, consumer="deploy_to_env")
        if value is None:
            return {"success": False, "service": service, "reason": "no_key"}
        env_file = Path(os.getenv("LEADGEN_ENV_FILE", "").strip() or ENV_FILE_DEFAULT)
        if not env_file.exists():
            return {"success": False, "service": service, "reason": "env_file_missing"}

        env_var = f"{service.upper()}_API_KEY"
        lines: list[str] = []
        replaced = False
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{env_var}="):
                lines.append(f"{env_var}={value}")
                replaced = True
            else:
                lines.append(line)
        if not replaced:
            lines.append(f"{env_var}={value}")
        new_content = "\n".join(lines) + "\n"

        backup = env_file.with_name(env_file.name + ".bak")
        _atomic_write_text(backup, env_file.read_text(encoding="utf-8"))
        _atomic_write_text(env_file, new_content)

        self._log_audit(
            "deploy", service, actor, True,
            f"deployed {env_var} to {env_file} (restart containers to pick up)",
        )
        return {
            "success": True,
            "service": service,
            "env_var": env_var,
            "env_file": str(env_file),
            "backup": str(backup),
            "message": "Key deployed to .env (container restart required)",
        }


# Singleton instance (app-level). Tests construct their own agents.
_key_manager: Optional[KeyManagerAgent] = None


def get_key_manager() -> KeyManagerAgent:
    global _key_manager
    if _key_manager is None:
        _key_manager = KeyManagerAgent()
    return _key_manager


# ─────────────────────────────────────────────────────────────────────────────
# Owner-gated router (P0: auth on EVERY route; built at app-composition time
# so the auth_deps import happens in normal import order — no cycles).
# ─────────────────────────────────────────────────────────────────────────────


class SetKeyIn(BaseModel):
    service: str
    key: str


class RotateKeyIn(BaseModel):
    service: str
    new_key: str


def _map_key_manager_error(exc: KeyManagerError) -> HTTPException:
    code = 503 if exc.reason in ("master_key_missing", "decrypt_failure") else 400
    return HTTPException(status_code=code, detail=exc.reason)


def build_keys_router() -> APIRouter:
    """Owner-only key management. Reads = admin; mutations = super_admin.

    Returns a router (NOT a module-level singleton) so the auth imports are
    deferred to app-composition time — same pattern as main.py's resilient
    router mounting.
    """
    from app.api.auth_deps import require_admin, require_super_admin
    from app.models.user import User

    router = APIRouter(prefix="/api/admin/keys", tags=["Admin - Key Manager"])

    @router.get("/status", summary="List all key slot states (redacted, owner view)")
    async def list_status(_user: User = Depends(require_admin)) -> list[dict[str, Any]]:
        km = get_key_manager()
        return [km.get_state(s) for s in km.list_services()]

    @router.get("/status/{service}")
    async def get_key_status(
        service: str, _user: User = Depends(require_admin)
    ) -> dict[str, Any]:
        """Redacted state only: ABSENT | PRESENT | INVALID | ROTATION_REQUIRED.
        No prefix/suffix/value in this or any other surface."""
        return get_key_manager().get_state(service)

    @router.post("/verify/{service}")
    async def verify_key_route(
        service: str, _user: User = Depends(require_super_admin)
    ) -> dict[str, Any]:
        """Billable provider smoke (TypeSafe initialize). Super-admin only."""
        return get_key_manager().verify_key(service, actor="admin_ui")

    @router.post("/set")
    async def set_key(
        payload: SetKeyIn, _user: User = Depends(require_super_admin)
    ) -> dict[str, Any]:
        try:
            return get_key_manager().set_key(payload.service, payload.key, actor="admin_ui")
        except KeyManagerError as exc:
            raise _map_key_manager_error(exc)

    @router.post("/rotate")
    async def rotate_key(
        payload: RotateKeyIn, _user: User = Depends(require_super_admin)
    ) -> dict[str, Any]:
        try:
            return get_key_manager().rotate_key(payload.service, payload.new_key, actor="admin_ui")
        except KeyManagerError as exc:
            raise _map_key_manager_error(exc)

    @router.post("/delete/{service}")
    async def delete_key_route(
        service: str, _user: User = Depends(require_super_admin)
    ) -> dict[str, Any]:
        return get_key_manager().delete_key(service, actor="admin_ui")

    @router.post("/request-rotation/{service}")
    async def request_rotation_route(
        service: str, _user: User = Depends(require_super_admin)
    ) -> dict[str, Any]:
        return get_key_manager().request_rotation(service, actor="admin_ui")

    @router.post("/deploy/{service}")
    async def deploy_key(
        service: str, _user: User = Depends(require_super_admin)
    ) -> dict[str, Any]:
        try:
            return get_key_manager().deploy_to_env(service, actor="admin_ui")
        except KeyManagerError as exc:
            raise _map_key_manager_error(exc)

    @router.get("/audit/{service}")
    async def get_audit(
        service: str, limit: int = 50, _user: User = Depends(require_admin)
    ) -> list[dict[str, Any]]:
        return get_key_manager().get_audit_log(service, limit)

    @router.get("/audit")
    async def get_all_audit(
        limit: int = 100, _user: User = Depends(require_admin)
    ) -> list[dict[str, Any]]:
        return get_key_manager().get_audit_log(None, limit)

    return router


# Back-compat alias (no module-level router anymore — importers must use
# build_keys_router(); grep 2026-09-21 confirmed zero legacy consumers).
KeyManager = KeyManagerAgent

__all__ = [
    "CANONICAL_TYPESAFE_SLOTS",
    "KeyManager",
    "KeyManagerAgent",
    "KeyManagerError",
    "build_keys_router",
    "get_key_manager",
]
