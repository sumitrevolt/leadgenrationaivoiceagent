"""Armed-flags verifier — deploy ke baad ek-shot check.

Gated automation flags ka state verify karta hai AFTER a deploy so "code ship ho
gaya" aur "flag actually armed hai" kabhi confuse na ho. Checks:

  A. Flag manifest registry — ONBOARD_WIZARD_APPLY / POST_CALL_SUMMARY documented
     hain (automation_flag_manifest) → 0/2 missing.
  B. Local .env state — ONBOARD_WIZARD_APPLY, POST_CALL_SUMMARY, AUTO_QUALIFY_CALLS,
     WHATSAPP_AUTO_SEND, WHATSAPP_SEND_ALLOWLIST set/unset (fail-closed semantics).
  C. Live endpoint probe (OPTIONAL — --url + --token diye to) —
       GET  /api/onboard-wizard/business-types   → expect 200 (read-only, hamesha live)
       GET  /api/onboard-wizard/preview/salon    → expect 200 (read-only)
       POST /api/onboard-wizard/apply            → expect 423 (flag unarmed) ya 200/422
       (423 = INERT correct; 422 = validation; 200 = ARMED)
  D. Verdict — go/no-go summary + exit code (0 = ready, 1 = problem, 2 = warning).

Usage:
    python scripts/verify_armed_flags.py                        # local .env + manifest
    python scripts/verify_armed_flags.py --env /opt/leadgen/.env
    python scripts/verify_armed_flags.py --url https://leadsgenai.in --token <admin> --apply-client-id <id>

Exit code 0 = ALL good · 1 = problem (missing flag, broken endpoint) · 2 = warning
(flag unset = INERT correct — check manually agar feature chahiye).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBLEMS: list[str] = []
WARNINGS: list[str] = []

# Windows cp1252 console pe unicode (✓/⚠) crash karta hai — ASCII-only output.
_OK = "[ok]"
_WARN = "[warn]"
_ERR = "[!!]"

# [flag, criticality] — critical = fail-closed outbound gate (missing = PROBLEM
# agar POST_CALL_SUMMARY armed hai); required = should be present in manifest.
FLAG_MANIFEST_EXPECTED = ("ONBOARD_WIZARD_APPLY", "POST_CALL_SUMMARY")
# .env me check karne wale flags + unka "armed" matlab
ENV_FLAGS: dict[str, dict[str, str]] = {
    "ONBOARD_WIZARD_APPLY": {"kind": "wizard", "armed": "1"},
    "POST_CALL_SUMMARY": {"kind": "summary", "armed": "1"},
    "AUTO_QUALIFY_CALLS": {"kind": "summary", "armed": "1"},
    "WHATSAPP_AUTO_SEND": {"kind": "summary", "armed": "1"},
    "WHATSAPP_SEND_ALLOWLIST": {"kind": "summary", "armed": "*"},  # non-empty = armed
}


def _read_env(path: pathlib.Path) -> dict[str, str]:
    """Simple .env parser (no inline comments — project rule). Never raises."""
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip()
                # strip optional quotes
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                out[k] = v
    except OSError:
        pass
    return out


def check_manifest() -> None:
    """Flag registry (automation_flag_manifest) me dono flags documented hain?"""
    try:
        sys.path.insert(0, str(ROOT))
        from app.platform import automation_flag_manifest as afm

        for name in FLAG_MANIFEST_EXPECTED:
            try:
                desc = afm.describe_flag(name)
                if desc is None:
                    PROBLEMS.append(f"manifest: {name} registry me NAHI hai")
                else:
                    gov = str(getattr(desc, "governance", "")).split(".")[-1]
                    print(f"  {_OK} manifest {name} (governance={gov})")
            except Exception as exc:
                PROBLEMS.append(f"manifest: {name} lookup failed ({exc})")
    except Exception as exc:
        PROBLEMS.append(f"manifest import failed: {exc}")


def check_env(path: pathlib.Path) -> dict[str, str]:
    """Local .env me flags — wizard arming + summary arming separately."""
    env = _read_env(path)
    print(f"  .env source: {path} ({'FOUND' if path.exists() else 'MISSING'})")

    # --- wizard ---
    wz = env.get("ONBOARD_WIZARD_APPLY", "").strip().lower() in ("1", "true", "yes")
    print(f"  {_OK} ONBOARD_WIZARD_APPLY={'ON (armed)' if wz else 'unset (INERT)'}")
    if not wz:
        WARNINGS.append(
            "ONBOARD_WIZARD_APPLY unset - wizard auto-setup INERT (catalog/preview hamesha live)"
        )

    # --- summary chain (4 gates) ---

    pc = env.get("POST_CALL_SUMMARY", "").strip().lower() in ("1", "true", "yes")
    aq = env.get("AUTO_QUALIFY_CALLS", "").strip().lower() in ("1", "true", "yes")
    wa = env.get("WHATSAPP_AUTO_SEND", "").strip().lower() in ("1", "true", "yes")
    al = (env.get("WHATSAPP_SEND_ALLOWLIST", "") or "").strip()
    print(f"  {_OK} POST_CALL_SUMMARY={'ON' if pc else 'OFF'}")
    print(f"  {_OK} AUTO_QUALIFY_CALLS={'ON' if aq else 'OFF'}")
    print(f"  {_OK} WHATSAPP_AUTO_SEND={'ON' if wa else 'OFF'}")
    print(f"  {_OK} WHATSAPP_SEND_ALLOWLIST={'set (' + al[:40] + ')' if al else 'EMPTY'}")

    if pc and not aq:
        PROBLEMS.append(
            "POST_CALL_SUMMARY=1 par AUTO_QUALIFY_CALLS OFF - summary kabhi nahi bhejega (flow gate)"
        )
    if pc and not wa:
        PROBLEMS.append(
            "POST_CALL_SUMMARY=1 par WHATSAPP_AUTO_SEND=0 - sender fail-closed, sab sends BLOCKED"
        )
    if pc and not al:
        PROBLEMS.append(
            "POST_CALL_SUMMARY=1 par WHATSAPP_SEND_ALLOWLIST EMPTY - canary gate: koi send nahi hoga"
        )
    if aq and not pc:
        WARNINGS.append(
            "AUTO_QUALIFY_CALLS=1 par POST_CALL_SUMMARY OFF - calls qualify honge, summary nahi bhejega"
        )
    return env


def _http(method: str, url: str, token: str = "", body: dict | None = None) -> tuple[int, dict]:
    """Minimal urllib HTTP call — returns (status, parsed-json-or-{})."""
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode("utf-8")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310 — fixed https URL
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {}
    except Exception as exc:
        PROBLEMS.append(f"network: {url} — {exc}")
        return 0, {}


def check_live(base_url: str, token: str, apply_client_id: str) -> None:
    """Live endpoint probe — read-only 200s + apply 423/200 signal."""
    base = (base_url or "").rstrip("/")
    if not base:
        return

    print(f"  live probe: {base}")

    # 1) business-types — read-only, hamesha 200 (flag ke bina)
    st, j = _http("GET", f"{base}/api/onboard-wizard/business-types", token)
    n = len(j.get("business_types") or []) if isinstance(j, dict) else 0
    if st == 200 and n:
        print(f"  {_OK} GET /onboard-wizard/business-types -> 200 ({n} types)")
    elif st == 200:
        WARNINGS.append("business-types 200 par empty list — catalog empty?")
    else:
        PROBLEMS.append(f"business-types -> {st} (expect 200)")

    # 2) preview — read-only, 200
    st, j = _http("GET", f"{base}/api/onboard-wizard/preview/salon", token)
    niche = (j.get("template") or {}).get("niche") if isinstance(j, dict) else ""
    if st == 200 and niche:
        print(f"  {_OK} GET /onboard-wizard/preview/salon -> 200 (niche={niche})")
    else:
        PROBLEMS.append(f"preview/salon -> {st} (expect 200)")

    # 3) apply — 423 = INERT correct, 200 = ARMED, 422 = validation (token bad?)
    if not apply_client_id:
        WARNINGS.append(
            "--apply-client-id nahi diya - apply endpoint probe SKIP (423/200 signal check nahi hua)"
        )
        return
    st, j = _http(
        "POST",
        f"{base}/api/onboard-wizard/apply",
        token,
        {"client_id": apply_client_id, "business_type": "salon"},
    )
    if st == 423:
        print(f"  {_OK} POST /onboard-wizard/apply -> 423 (flag unarmed = INERT correct)")
    elif st == 200:
        applied = (j.get("applied") or []) if isinstance(j, dict) else []
        print(
            f"  {_WARN} POST /onboard-wizard/apply -> 200 ARMED (applied={applied}) — verify client pe applied fields"
        )
        WARNINGS.append(
            "apply returned 200 — wizard auto-setup LIVE (expected sirf jab ONBOARD_WIZARD_APPLY=1)"
        )
    elif st == 422:
        PROBLEMS.append("apply → 422 — admin token / payload check karo (auth pass hua ya nahi?)")
    else:
        PROBLEMS.append(f"apply → {st} (expect 423 unarmed ya 200 armed)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy ke baad armed-flags verification")
    ap.add_argument("--env", default=str(ROOT / ".env"), help=".env path (default: repo .env)")
    ap.add_argument("--url", default="", help="Live base URL (optional — endpoint probe ke liye)")
    ap.add_argument("--token", default="", help="Admin Bearer token (optional — probe auth)")
    ap.add_argument(
        "--apply-client-id", default="", help="Apply probe ke liye dummy client id (optional)"
    )
    args = ap.parse_args()

    print("== Armed-flags verification ==")
    print("[A] manifest registry")
    check_manifest()
    print("[B] .env state")
    check_env(pathlib.Path(args.env))
    print("[C] live endpoints")
    check_live(args.url, args.token, args.apply_client_id)
    print("-" * 50)

    if PROBLEMS:
        print("[!] PROBLEMS (exit 1):")
        for p in PROBLEMS:
            print(f"    - {p}")
        return 1
    if WARNINGS:
        print("  [i] WARNINGS (exit 2):")
        for w in WARNINGS:
            print(f"    - {w}")
        return 2
    print("[OK] ALL ARMED-FLAG CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
