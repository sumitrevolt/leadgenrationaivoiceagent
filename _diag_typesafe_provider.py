"""Diagnostic: redacted provider-fallback root cause analysis.

Per owner Wave 8 continuation §1 (DIAGNOSE provider_fallback):
- Inspect canonical client, endpoint, requested model, HTTP status,
  exception category, response schema, timeout, retry behavior, credential source.
- Use secure, redacted diagnostics. NEVER print API keys.
- Compare with WorkBuddy's prior jev-latest success (progress.md:521).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

# REDACTED credential fingerprint (NEVER the raw value).
def _fp(env_var: str) -> dict[str, str]:
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return {"env": env_var, "state": "ABSENT"}
    return {
        "env": env_var,
        "state": "PRESENT",
        "fingerprint": "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
    }


def main() -> int:
    print("=== REDACTED DIAGNOSTIC: TypeSafe provider_fallback root cause ===\n")

    # Step 1: Credential fingerprint.
    print("STEP 1: Credential fingerprint")
    for env in ("TYPESAFE_API_KEY", "TYPESAFE_MODEL"):
        print("  ", _fp(env))
    print()

    # Step 2: Client configuration.
    from app.platform.typesafe_integration import (
        TYPEsafe_BASE_URL,
        _DEFAULT_MODEL,
        get_typesafe_client,
    )

    client = get_typesafe_client()
    print("STEP 2: Client config")
    print(f"  base_url={TYPEsafe_BASE_URL}")
    print(f"  default_model={_DEFAULT_MODEL}")
    print(f"  client.enabled={getattr(client, 'enabled', False)}")
    print(f"  client.model={getattr(client, 'model', None)}")
    print()

    # Step 3: Authenticated endpoint test (minimal Choice question).
    print("STEP 3: Minimal authenticated call (single Choice)")
    from app.platform.typesafe_integration import Choice

    state = {
        "purpose": "diag_provider_fallback",
        "task_id": "diag-1",
        "tenant_scope": "platform",
        "evidence_refs": ["data/diag.jsonl"],
    }
    questions = {
        "q": Choice(
            "Is this a successful live API call?",
            {
                "yes": "Provider returned a valid verdict with answer=yes",
                "no": "Provider returned a valid verdict with answer=no",
            },
        )
    }

    started = time.time()
    response = client.system_one(
        state,
        questions,
        connect_timeout_sec=5.0,
        read_timeout_sec=10.0,
        max_attempts=1,  # bounded diagnostic — do not retry
    )
    elapsed = time.time() - started

    print(f"  elapsed_sec={elapsed:.2f}")
    print(f"  success={response.success}")
    print(f"  error={response.error!r}")
    print(f"  model={response.model!r}")
    print(f"  latency_sec={response.latency_sec:.2f}")
    print(f"  attempts={response.attempts}")
    print(f"  result_keys={list((response.result or {}).keys())[:8]}")
    print()

    # Step 4: Classify failure by error prefix.
    print("STEP 4: Failure classification")
    err = response.error or ""
    if response.success:
        classification = "REAL_SUCCESS"
    elif err.startswith("INERT"):
        classification = "INERT (no API key)"
    elif err.startswith("INVALID_QUESTION_TYPE"):
        classification = "INVALID_QUESTION_TYPE (client-side bug)"
    elif err.startswith("TIMEOUT"):
        classification = "TIMEOUT (network — increase timeout)"
    elif err.startswith("NETWORK"):
        classification = "NETWORK (DNS/connect/TLS — check connectivity)"
    elif err.startswith("INVALID_JSON"):
        classification = "INVALID_JSON (provider returned non-JSON — likely wrong endpoint or auth)"
    elif err.startswith("HTTP_401") or err.startswith("HTTP_403"):
        classification = "HTTP_401/403 (auth failure — key invalid or wrong scope)"
    elif err.startswith("HTTP_404"):
        classification = "HTTP_404 (endpoint wrong — provider moved)"
    elif err.startswith("HTTP_429"):
        classification = "HTTP_429 (rate limited)"
    elif err.startswith("HTTP_5"):
        classification = f"HTTP_5xx (server error — {err[:80]})"
    elif err.startswith("UNEXPECTED"):
        classification = "UNEXPECTED (client-side bug)"
    else:
        classification = f"UNKNOWN ({err[:80]})"
    print(f"  classification={classification}")
    print()

    # Step 5: Connectivity probe (separate from auth).
    print("STEP 5: Connectivity probe (no auth, just TCP+TLS to endpoint)")
    import socket
    import urllib.parse

    parsed = urllib.parse.urlparse(TYPEsafe_BASE_URL)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=5.0) as s:
            print(f"  TCP {host}:{port} = REACHABLE")
            print(f"  TLS handshake would happen on first request")
    except Exception as exc:
        print(f"  TCP {host}:{port} = UNREACHABLE ({type(exc).__name__}: {exc})")
    print()

    # Step 6: WorkBuddy comparison.
    print("STEP 6: WorkBuddy comparison (progress.md:521)")
    print("  WorkBuddy prior session: TYPESAFE_API_KEY PRESENT, jev-latest resolved jev-1.13.0,")
    print("    1 Choice call returned reason=typesafe_judgment, confidence=0.94.")
    print("  Current session: TYPESAFE_API_KEY PRESENT, jev-latest, classification=" + classification)
    print()

    print("=== END DIAGNOSTIC ===")
    return 0 if response.success else 1


if __name__ == "__main__":
    sys.exit(main())
