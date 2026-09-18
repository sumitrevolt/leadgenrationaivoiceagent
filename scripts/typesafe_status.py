#!/usr/bin/env python3
"""TypeSafe credential STATUS + local activation tool (2026-09-18).

WHY THIS EXISTS
---------------
`app/platform/typesafe_integration.py` (added 7317f990) shipped a live ~100-char
API key as an `os.getenv(...)` FALLBACK DEFAULT. That is why TypeSafe "worked
locally without configuration" — it was not configuration, it was a committed
credential. 979c2229 removed the literal (correct security fix), so the module
now reads the key ONLY from the process environment:

  1. TYPESAFE_API_KEY      (canonical)
  2. TYPEsafe_API_KEY      (legacy)
  3. ""                    -> INERT (fail-closed, never silently authenticated)

Result: on a machine with no exported variable and no loader, the client is
INERT even if a key file is lying around — nothing in the app calls
`load_dotenv`, so a `.env` key is invisible to `os.getenv`.

This tool exists so the credential state is a *measured fact*, not a guess:

  python scripts/typesafe_status.py                  # state only, no network
  python scripts/typesafe_status.py --probe          # live System One judgment
  python scripts/typesafe_status.py --set-key-stdin  # activate locally (hidden input)
  python scripts/typesafe_status.py --probe --json    # machine-readable

SECURITY CONTRACT (do not weaken)
---------------------------------
* The key VALUE is never printed, logged, put in argv, or written to a report.
  Only a sha256 fingerprint prefix (12 hex) is shown, so the owner can tell two
  keys apart without exposing either.
* `--set-key-stdin` reads through getpass: nothing lands in shell history.
* `--set-key-stdin` refuses non-repo targets and prod-looking env files — the
  VPS `.env` is owner-/runbook-managed (`scripts/env_set.py`), not this tool.
* Reporting states are exactly: PRESENT / ABSENT / INVALID / ROTATION_REQUIRED.

Exit codes: 0 ok · 2 ABSENT · 3 INVALID · 4 ROTATION_REQUIRED · 1 other error.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parent.parent

_CANONICAL_ENV = "TYPESAFE_API_KEY"
_LEGACY_ENV = "TYPEsafe_API_KEY"
_DEFAULT_MODEL = "jev-latest"

STATE_PRESENT = "PRESENT"
STATE_ABSENT = "ABSENT"
STATE_INVALID = "INVALID"
STATE_ROTATION = "ROTATION_REQUIRED"

# Single source of truth = app/platform/typesafe_integration.py (so the script,
# wiring_gaps() and the module can never drift apart). Degraded mode keeps the
# CLI usable even if the app import chain is broken — but it SAYS so.
_TRIPWIRE_LOADED = True
try:  # the app module owns the trip-wire; the script must never fork its own copy
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.platform.typesafe_integration import COMPROMISED_FINGERPRINTS as _APP_TRIPWIRE
    from app.platform.typesafe_integration import fingerprint as _app_fingerprint
except Exception:  # pragma: no cover - degraded mode is surfaced in notes/JSON
    _TRIPWIRE_LOADED = False
    _APP_TRIPWIRE: dict[str, str] = {}
    _app_fingerprint = None


# Diagnostic-only local files. NOT credential inputs: the app never loads them,
# so a key that lives only here is still ABSENT to every os.getenv() caller.
_DIAGNOSTIC_ENV_FILES = (".env.production.local",)


def fingerprint(value: str) -> str:
    """sha256[:12] of a credential — safe to print/log. NEVER the credential itself."""
    if _app_fingerprint is not None:
        return _app_fingerprint(value)
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


COMPROMISED_FINGERPRINTS: dict[str, str] = dict(_APP_TRIPWIRE)


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal dotenv parse (KEY=VALUE, quotes stripped, comments ignored)."""
    out: dict[str, str] = {}
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        val = val.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


@dataclass
class KeyResolution:
    """Where the credential came from, and what state that puts us in."""

    state: str
    source: str = "none"
    fingerprint: str = ""
    model: str = _DEFAULT_MODEL
    notes: list[str] = field(default_factory=list)
    key: str = ""  # never serialized

    def public(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("key", None)
        return d


def resolve_key(
    env: Mapping[str, str] | None = None,
    env_files: Iterable[Path] | None = None,
    diagnostic_files: Iterable[Path] | None = None,
) -> KeyResolution:
    """Resolve the credential the way the integration does, then classify it.

    Read order (mirrors `_get_api_key()`): canonical env -> legacy env -> repo
    `.env` (convenience for local tooling, matching scripts/fire_calls.py).
    """
    env = os.environ if env is None else env
    env_files = list(env_files) if env_files is not None else [ROOT / ".env"]
    diagnostic_files = (
        list(diagnostic_files)
        if diagnostic_files is not None
        else [ROOT / name for name in _DIAGNOSTIC_ENV_FILES]
    )

    key = ""
    source = "none"
    for name in (_CANONICAL_ENV, _LEGACY_ENV):
        val = (env.get(name) or "").strip()
        if val:
            key, source = val, f"env:{name}"
            break
    if not key:
        for path in env_files:
            vals = parse_env_file(path)
            for name in (_CANONICAL_ENV, _LEGACY_ENV):
                val = (vals.get(name) or "").strip()
                if val:
                    key, source = val, str(path)
                    break
            if key:
                break

    model = (env.get("TYPESAFE_MODEL") or "").strip() or _DEFAULT_MODEL
    notes: list[str] = []
    if not _TRIPWIRE_LOADED:
        notes.append(
            "compromised-fingerprint trip-wire UNAVAILABLE (app import failed) — "
            "treat PRESENT as unverified"
        )
    for path in diagnostic_files:
        vals = parse_env_file(path)
        parked = (vals.get(_CANONICAL_ENV) or vals.get(_LEGACY_ENV) or "").strip()
        if parked and fingerprint(parked) != fingerprint(key):
            notes.append(
                f"{path.name} holds a TypeSafe key (fp {fingerprint(parked)}) "
                "but nothing loads that file -> invisible to os.getenv()"
            )

    if not key:
        return KeyResolution(state=STATE_ABSENT, source="none", model=model, notes=notes)

    fp = fingerprint(key)
    state = STATE_ROTATION if fp in COMPROMISED_FINGERPRINTS else STATE_PRESENT
    if state == STATE_ROTATION:
        notes.append(f"fingerprint {fp} = {COMPROMISED_FINGERPRINTS[fp]} -> rotate")
    if source in (str(ROOT / ".env"), f"env:{_LEGACY_ENV}"):
        notes.append(
            "app processes read os.getenv only (main.py has no load_dotenv) — "
            "run uvicorn with --env-file .env, or export the variable"
        )
    return KeyResolution(state=state, source=source, fingerprint=fp, model=model, notes=notes, key=key)


def probe(key: str, model: str = _DEFAULT_MODEL, timeout: float = 30.0) -> dict[str, Any]:
    """Live System One judgment through the canonical client (never logs the key)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.platform.typesafe_integration import Choice, Noul, Score, TypeSafeClient

    client = TypeSafeClient(api_key=key, model=model)
    resp = client.system_one(
        {"task": "typesafe_status_probe", "note": "credential + endpoint reachability probe"},
        {
            "reachable": Noul("Did this request reach the TypeSafe evaluation endpoint?"),
            "path": Choice(
                "What did this request prove?",
                {"live_key": "Authentication accepted and a judgment was returned", "other": "Something else"},
            ),
            "health": Score("How healthy is this credential path?", ["broken", "degraded", "healthy"]),
        },
    )
    status = None
    if resp.error:
        m = re.match(r"HTTP (\d{3})", resp.error)
        if m:
            status = int(m.group(1))
    return {
        "success": bool(resp.success),
        "http_status": status,
        "requested_model": model,
        "resolved_model": resp.model,
        "latency_sec": round(resp.latency_sec, 3),
        "answer_keys": sorted(resp.answers.keys()),
        "value": resp.value,
        "confidence": resp.confidence if resp.success else None,
        "error": (resp.error or "")[:200],
    }


def probe_state(res: KeyResolution, result: dict[str, Any]) -> str:
    """Fold a probe result into the credential state."""
    if result.get("success"):
        return STATE_ROTATION if res.fingerprint in COMPROMISED_FINGERPRINTS else STATE_PRESENT
    status = result.get("http_status")
    if status in (401, 403):
        return STATE_INVALID
    if status is None:
        return STATE_INVALID if result.get("error") else STATE_ABSENT
    return STATE_INVALID


def _assert_local_target(path: Path) -> None:
    """Refuse anything that is not a repo-local, non-production env file."""
    resolved = path.resolve()
    if ROOT.resolve() not in resolved.parents:
        raise SystemExit(
            f"REFUSED: {resolved} is outside the repo — this tool never writes a "
            "server/production .env (use the VPS runbook + scripts/env_set.py)"
        )
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for marker in ("app_env=production", "environment=production", "env=production"):
            if marker in text:
                raise SystemExit(f"REFUSED: {path} looks like a production env file ({marker})")


def set_key(path: Path, key: str) -> str:
    """Idempotently write TYPESAFE_API_KEY (value never echoed). Returns backup path."""
    _assert_local_target(path)
    backup = ""
    lines: list[str] = []
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{path}.bak_typesafe_{stamp}"
        n = 1
        while Path(backup).exists():  # same-second activations must not clobber a backup
            backup = f"{path}.bak_typesafe_{stamp}_{n}"
            n += 1
        shutil.copy(path, backup)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    line = f"{_CANONICAL_ENV}={key}"
    seen = False
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        head = s.split("=", 1)[0].strip() if ("=" in s and not s.startswith("#")) else ""
        if head in (_CANONICAL_ENV, _LEGACY_ENV):
            if not seen:
                out.append(line)
                seen = True
            continue
        out.append(ln)
    if not seen:
        out.append(line)

    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows / restricted FS — best effort only
    return backup


def read_key_stdin() -> str:
    """Hidden prompt when interactive, plain stdin when piped. Never echoes."""
    if sys.stdin is not None and sys.stdin.isatty():
        return (getpass.getpass("Paste TypeSafe API key (hidden, not echoed/history): ") or "").strip()
    return (sys.stdin.read() or "").strip()


def render(res: KeyResolution, result: dict[str, Any] | None = None) -> str:
    lines = [f"TypeSafe credential state: {res.state}"]
    if res.fingerprint:
        lines.append(f"fingerprint: {res.fingerprint}")
    lines.append(f"source: {res.source}")
    lines.append(f"model (requested): {res.model}")
    if result:
        lines.append(f"probe success: {result['success']}")
        lines.append(f"probe http_status: {result['http_status']}")
        lines.append(f"model (resolved): {result['resolved_model']}")
        lines.append(f"latency_sec: {result['latency_sec']}")
        lines.append(f"answer keys: {', '.join(result['answer_keys']) or '-'}")
        if result.get("error"):
            lines.append(f"error: {result['error']}")
    for note in res.notes:
        lines.append(f"note: {note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TypeSafe credential status / local activation")
    ap.add_argument("--probe", action="store_true", help="live System One request (network)")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable output")
    ap.add_argument("--set-key-stdin", action="store_true", help="read a key (hidden) and write local .env")
    ap.add_argument("--file", default=str(ROOT / ".env"), help="target env file for --set-key-stdin")
    ap.add_argument("--no-probe", action="store_true", help="skip the post-write probe")
    args = ap.parse_args(argv)

    target = Path(args.file)
    backup = ""
    if args.set_key_stdin:
        key = read_key_stdin()
        if len(key) < 20 or any(c.isspace() for c in key):
            print("REFUSED: empty/whitespace/short key", file=sys.stderr)
            return 1
        backup = set_key(target, key)
        os.environ[_CANONICAL_ENV] = key
        res = resolve_key()
        print(f"wrote {_CANONICAL_ENV} -> {target} (fingerprint {res.fingerprint})")
        if backup:
            print(f"backup: {Path(backup).name}")
        print("next: run uvicorn with --env-file .env (or export the variable) so the app sees it")
    else:
        res = resolve_key()

    result = None
    wants_probe = args.probe or (args.set_key_stdin and not args.no_probe)
    if wants_probe and res.key:
        result = probe(res.key, res.model)
        res.state = probe_state(res, result)

    if args.as_json:
        print(json.dumps({"credential": res.public(), "probe": result}, indent=2))
    else:
        print(render(res, result))

    return {
        STATE_PRESENT: 0,
        STATE_ABSENT: 2,
        STATE_INVALID: 3,
        STATE_ROTATION: 4,
    }.get(res.state, 1)


if __name__ == "__main__":
    sys.exit(main())
