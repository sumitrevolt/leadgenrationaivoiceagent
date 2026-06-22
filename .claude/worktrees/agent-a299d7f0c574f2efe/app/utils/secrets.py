"""
app/utils/secrets.py
--------------------
SOPS + age encrypted secrets loader — never-raise, gated behind USE_SOPS=1.

Default behaviour (USE_SOPS unset or 0):
    - load_encrypted_env() is a no-op, returns False.
    - get_secret(name) is just os.getenv(name, default).
    - Zero behaviour change from current plain-.env flow.

Opt-in (set USE_SOPS=1 in .env or environment):
    - load_encrypted_env() shells out to `sops -d` on the encrypted file,
      parses the dotenv output, and injects vars into os.environ.
    - Call once at app startup (e.g. top of main.py, before other imports
      that read os.getenv).

Requirements:
    - sops binary in PATH (installed via scripts/sops_setup.sh).
    - SOPS_AGE_KEY_FILE env var pointing to ~/.config/sops/age/keys.txt.
    - SOPS_ENC_FILE env var (default: secrets/.env.enc.yaml relative to CWD,
      or /opt/leadgen/secrets/.env.enc.yaml on VPS).
    - SOPS_CONFIG_FILE env var (default: .sops.yaml in CWD).

NEVER raises on import or on any function call.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_enabled() -> bool:
    """Return True only when USE_SOPS=1 is explicitly set."""
    return os.getenv("USE_SOPS", "0").strip() == "1"


def _find_enc_file() -> Path | None:
    """Locate the encrypted env file, checking env var then common paths."""
    env_val = os.getenv("SOPS_ENC_FILE", "").strip()
    candidates = []
    if env_val:
        candidates.append(Path(env_val))
    # Common VPS location
    candidates.append(Path("/opt/leadgen/secrets/.env.enc.yaml"))
    # Relative to CWD (dev/local)
    candidates.append(Path.cwd() / "secrets" / ".env.enc.yaml")

    for p in candidates:
        if p.exists():
            return p
    return None


def _find_sops_config() -> Path | None:
    """Locate .sops.yaml config file."""
    env_val = os.getenv("SOPS_CONFIG_FILE", "").strip()
    candidates = []
    if env_val:
        candidates.append(Path(env_val))
    candidates.append(Path("/opt/leadgen/.sops.yaml"))
    candidates.append(Path.cwd() / ".sops.yaml")

    for p in candidates:
        if p.exists():
            return p
    return None


def _parse_dotenv_output(text: str) -> dict[str, str]:
    """Parse sops dotenv output into a dict. Handles quotes, blank lines, comments."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        # Strip surrounding quotes (single or double)
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        if key:
            result[key] = val
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_encrypted_env(
    enc_file: str | None = None,
    sops_config: str | None = None,
    overwrite_existing: bool = False,
) -> bool:
    """
    Decrypt the SOPS-encrypted env file and load vars into os.environ.

    Parameters
    ----------
    enc_file        : Path to encrypted file. Auto-detected if None.
    sops_config     : Path to .sops.yaml. Auto-detected if None.
    overwrite_existing : If False (default), existing os.environ keys are kept
                         (plain .env loaded earlier wins). Set True to let
                         encrypted file override.

    Returns
    -------
    True  — vars loaded successfully.
    False — disabled, files missing, or any error (always graceful).
    """
    try:
        if not _is_enabled():
            logger.debug("secrets: USE_SOPS not set — skipping encrypted load.")
            return False

        # Verify sops binary exists
        if not shutil.which("sops"):
            logger.warning(
                "secrets: USE_SOPS=1 but 'sops' binary not found in PATH. "
                "Run scripts/sops_setup.sh on the VPS."
            )
            return False

        # Locate encrypted file
        _enc = Path(enc_file) if enc_file else _find_enc_file()
        if _enc is None or not _enc.exists():
            logger.warning(
                "secrets: USE_SOPS=1 but encrypted file not found. "
                "Run scripts/sops_encrypt_env.sh first."
            )
            return False

        # Locate sops config
        _cfg = Path(sops_config) if sops_config else _find_sops_config()

        # Build sops command
        cmd = [
            "sops",
            "--input-type",
            "yaml",
            "--output-type",
            "dotenv",
            "--decrypt",
        ]
        if _cfg and _cfg.exists():
            cmd += ["--config", str(_cfg)]
        cmd.append(str(_enc))

        # Build subprocess env — forward SOPS_AGE_KEY_FILE if set
        proc_env = os.environ.copy()

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            env=proc_env,
        )

        if result.returncode != 0:
            logger.warning(
                "secrets: sops decrypt failed (rc=%d): %s",
                result.returncode,
                result.stderr.strip()[:300],
            )
            return False

        parsed = _parse_dotenv_output(result.stdout)
        if not parsed:
            logger.warning("secrets: sops decrypted OK but no vars found.")
            return False

        loaded = 0
        for k, v in parsed.items():
            if overwrite_existing or k not in os.environ:
                os.environ[k] = v
                loaded += 1

        logger.info("secrets: loaded %d vars from encrypted env (%s).", loaded, _enc.name)
        return True

    except subprocess.TimeoutExpired:
        logger.warning("secrets: sops decrypt timed out after 15s.")
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("secrets: unexpected error during load — %s", exc)
        return False


def get_secret(name: str, default: str = "") -> str:
    """
    Thin wrapper around os.getenv — use instead of os.getenv for secret keys
    so callers are explicit about secrets vs config.

    Never raises.
    """
    try:
        return os.getenv(name, default)
    except Exception:  # noqa: BLE001
        return default


# ---------------------------------------------------------------------------
# Dev/debug helper — not imported by production paths
# ---------------------------------------------------------------------------


def _print_status() -> None:  # pragma: no cover
    """Print secrets subsystem status. For debugging only."""
    enabled = _is_enabled()
    enc = _find_enc_file()
    cfg = _find_sops_config()
    sops_bin = shutil.which("sops")
    age_bin = shutil.which("age")
    key_file = os.getenv("SOPS_AGE_KEY_FILE", "~/.config/sops/age/keys.txt")

    print(f"USE_SOPS         : {os.getenv('USE_SOPS', 'unset')}")
    print(f"Enabled          : {enabled}")
    print(f"sops binary      : {sops_bin or 'NOT FOUND'}")
    print(f"age binary       : {age_bin or 'NOT FOUND'}")
    print(f"Encrypted file   : {enc or 'NOT FOUND'}")
    print(f"SOPS config      : {cfg or 'NOT FOUND'}")
    print(f"Age key file     : {key_file}")


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    _print_status()
