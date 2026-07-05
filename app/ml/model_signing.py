"""HMAC-SHA256 sidecar signing for pickled ML models (closes ADR-002 TODO).

WHY: ``pickle.load`` on a tampered file is arbitrary code execution. Model
files live on disk (``data/models/*.pkl``) and ride through backups/restores —
an attacker who can write one byte there owns the process. A keyed HMAC sidecar
(``<model>.pkl.sig``) makes the pickle tamper-evident.

FAILURE POLICY (deliberately asymmetric):
- ``MODEL_SIGNING_KEY`` unset            → fail-OPEN  (feature inert, prod unchanged)
- key set, sidecar missing               → fail-OPEN  (legacy unsigned models keep
                                            working; warning logged so ops can re-sign)
- key set, sidecar present, MISMATCH     → fail-CLOSED (refuse the load — a wrong
                                            signature is the one signal that screams
                                            tampering, and tampered pickle = RCE)

Convention follows the repo standard: env read at call-time, never raises,
logger via app.utils.logger.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_ENV_KEY = "MODEL_SIGNING_KEY"
_SIG_SUFFIX = ".sig"
_CHUNK = 1 << 20  # 1 MiB


def _key() -> bytes | None:
    raw = (os.environ.get(_ENV_KEY) or "").strip()
    return raw.encode("utf-8") if raw else None


def signing_enabled() -> bool:
    """True when MODEL_SIGNING_KEY is set (feature armed)."""
    return _key() is not None


def _sig_path(path: str | Path) -> Path:
    return Path(str(path) + _SIG_SUFFIX)


def _hmac_file(path: Path, key: bytes) -> str | None:
    try:
        mac = hmac.new(key, digestmod=hashlib.sha256)
        with open(path, "rb") as f:
            while True:
                chunk = f.read(_CHUNK)
                if not chunk:
                    break
                mac.update(chunk)
        return mac.hexdigest()
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[model_signing] hmac failed for %s: %s", path, e)
        return None


def sign_file(path: str | Path) -> bool:
    """Write ``<path>.sig`` sidecar. True on success; False (never raises) when
    the key is unset, the file is unreadable, or the sidecar can't be written."""
    key = _key()
    if key is None:
        return False
    p = Path(path)
    digest = _hmac_file(p, key)
    if digest is None:
        return False
    try:
        _sig_path(p).write_text(digest, encoding="utf-8")
        return True
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[model_signing] could not write sidecar for %s: %s", p, e)
        return False


def verify_file(path: str | Path) -> bool:
    """True = safe to ``pickle.load``; False = REFUSE (tamper-evident mismatch).

    Fail-open when the key or sidecar is absent (see module docstring);
    fail-closed ONLY on an actual signature mismatch."""
    key = _key()
    if key is None:
        return True  # feature inert — fail-open
    p = Path(path)
    sig_p = _sig_path(p)
    if not sig_p.is_file():
        logger.warning(
            "[model_signing] %s has no %s sidecar — loading unsigned legacy model "
            "(fail-open); re-train or sign_file() to arm verification.",
            p.name,
            _SIG_SUFFIX,
        )
        return True
    try:
        expected = sig_p.read_text(encoding="utf-8").strip()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[model_signing] unreadable sidecar for %s (%s) — fail-open", p.name, e)
        return True
    actual = _hmac_file(p, key)
    if actual is None:
        return True  # unreadable model file → pickle.load will fail on its own
    if hmac.compare_digest(expected, actual):
        return True
    logger.error(
        "[model_signing] SIGNATURE MISMATCH for %s — refusing to unpickle "
        "(tampered model file = arbitrary code execution). fail-CLOSED.",
        p.name,
    )
    return False
