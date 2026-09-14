"""WhatsApp Cloud API verifier — run this AFTER pasting Meta credentials into ``.env``.

Owner runbook: ``docs/integrations/WHATSAPP_CLOUD_SETUP.md``
Run from the repo root:  ``python scripts/whatsapp_cloud_verify.py``

Exit codes
    0 = the Meta Graph API call for the phone number succeeded
    1 = config incomplete (itemised checklist printed — where to get each value)
    2 = API/network failure (Meta rejected the call or was unreachable)
    3 = the script cannot import the app (wrong cwd / broken env)

SECRETS: the business token, app secret and verify token are NEVER printed — only
presence + length. This output is meant to be pasted into a chat/screenshot, so it
must stay safe to share.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GRAPH_ROOT = "https://graph.facebook.com"

# (settings attribute, env var name, one-line "where to get it")
REQUIRED: list[tuple[str, str, str]] = [
    (
        "whatsapp_business_token",
        "WHATSAPP_BUSINESS_TOKEN",
        "Meta app > WhatsApp > API Setup > mint a PERMANENT token as a System User "
        "with the whatsapp_business_messaging permission",
    ),
    (
        "whatsapp_phone_number_id",
        "WHATSAPP_PHONE_NUMBER_ID",
        "Meta app > WhatsApp > API Setup > 'Phone number ID' (the numeric ID, NOT the "
        "phone number itself)",
    ),
    (
        "whatsapp_app_secret",
        "WHATSAPP_APP_SECRET",
        "Meta app > App settings > Basic > App secret (verifies webhook signatures)",
    ),
    (
        "whatsapp_verify_token",
        "WHATSAPP_VERIFY_TOKEN",
        "a random string YOU choose; paste the SAME value into Meta's webhook config. "
        'Generate: python -c "import secrets;print(secrets.token_urlsafe(32))"',
    ),
]


def _get(
    version: str, node: str, token: str, params: dict[str, str] | None = None
) -> tuple[bool, dict[str, Any]]:
    """GET one Graph node. Returns (ok, json). Never raises. Token goes in the header only."""
    import httpx

    url = f"{GRAPH_ROOT}/{version}/{str(node).lstrip('/')}"
    shown = ", ".join(f"{k}={v}" for k, v in (params or {}).items()) or "-"
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get(url, params=params or {}, headers={"Authorization": f"Bearer {token}"})
    except Exception as exc:  # noqa: BLE001 - script boundary, report and continue
        print(f"  x network error: {exc}")
        return False, {}
    try:
        data = r.json()
    except Exception:
        data = {}
    if r.status_code // 100 != 2:
        err = (data.get("error") or {}) if isinstance(data, dict) else {}
        print(f"  x HTTP {r.status_code} on {url} ({shown})")
        if err.get("message"):
            print(f"    Meta says: {err.get('message')}")
            print(
                f"    (code={err.get('code')} type={err.get('type')} subcode={err.get('error_subcode')})"
            )
        else:
            print(f"    body: {r.text[:300]}")
        return False, {}
    print(f"  ok GET {url} ({shown})")
    return True, data if isinstance(data, dict) else {}


def _digits(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def main() -> int:
    print("WhatsApp Cloud API verifier")
    print("=" * 62)
    try:
        from app.config import settings
    except Exception as exc:  # noqa: BLE001 - script boundary
        print(f"FATAL: cannot import app.config.settings ({exc}) — run from the repo root.")
        return 3
    try:
        from app.integrations.whatsapp import GRAPH_API_VERSION
    except Exception as exc:  # noqa: BLE001 - script boundary
        print(f"FATAL: cannot import GRAPH_API_VERSION ({exc}) — run from the repo root.")
        return 3

    vals = {attr: str(getattr(settings, attr, "") or "").strip() for attr, _env, _hint in REQUIRED}

    # ---- config gate (BEFORE any network call) ----------------------------
    print("\nCredentials (values never printed — length only):")
    missing: list[tuple[str, str]] = []
    for attr, env_name, hint in REQUIRED:
        present = bool(vals[attr])
        print(
            f"  {'ok  ' if present else 'MISS'} {env_name:<30} {'len ' + str(len(vals[attr])) if present else 'MISSING'}"
        )
        if not present:
            missing.append((env_name, hint))

    provider = str(getattr(settings, "whatsapp_provider", "") or "").strip().lower() or "cloud"
    base = str(getattr(settings, "public_base_url", "") or "https://leadsgenai.in").rstrip("/")
    print(f"\n  active provider : WHATSAPP_PROVIDER={provider}")
    print(f"  graph version   : {GRAPH_API_VERSION}   (override: WHATSAPP_GRAPH_VERSION)")
    print(f"  webhook URL (recommended) : {base}/api/webhooks/whatsapp")
    print(f"  webhook URL (alternative) : {base}/api/wa/webhook")

    if missing:
        print("\n" + "=" * 62)
        print("CLOUD API NOT CONFIGURED — fill these into .env, then re-run:")
        for env_name, hint in missing:
            print(f"\n  * {env_name}")
            print(f"      where: {hint}")
        print("\n  Full owner runbook: docs/integrations/WHATSAPP_CLOUD_SETUP.md")
        return 1

    token = vals["whatsapp_business_token"]
    phone_id = vals["whatsapp_phone_number_id"]

    # ---- 1) the phone-number node (this one decides the exit code) --------
    print("\n1) Phone number node")
    ok, data = _get(
        GRAPH_API_VERSION,
        phone_id,
        token,
        {"fields": "display_phone_number,verified_name,quality_rating"},
    )
    if not ok:
        print("\nRESULT: FAILED — Meta rejected the phone-number call (creds wrong/expired?).")
        return 2

    display = str(data.get("display_phone_number") or "")
    print(f"     display_phone_number : {display or '(absent)'}")
    print(f"     verified_name        : {data.get('verified_name') or '(absent)'}")
    print(f"     quality_rating       : {data.get('quality_rating') or '(absent)'}")
    print(f"     id (confirmed)       : {data.get('id') or phone_id}")

    # ---- 2) WABA + subscribed apps (best-effort, never gates exit) --------
    print("\n2) WABA / subscribed apps (best-effort)")
    waba = str(getattr(settings, "whatsapp_business_account_id", "") or "").strip()
    if not waba:
        print(
            "  skipped — WHATSAPP_BUSINESS_ACCOUNT_ID unset (optional; set it to see subscribed apps)"
        )
    else:
        ok_w, wdata = _get(GRAPH_API_VERSION, waba, token, {"fields": "id,name"})
        if ok_w:
            print(f"     WABA id={wdata.get('id') or waba} name={wdata.get('name') or '(absent)'}")
        else:
            print("     WABA lookup failed — non-fatal (check WHATSAPP_BUSINESS_ACCOUNT_ID).")
        ok_s, sdata = _get(GRAPH_API_VERSION, f"{waba}/subscribed_apps", token)
        if ok_s:
            apps = sdata.get("data") or []
            names = [
                str((a.get("whatsapp_business_api_data") or {}).get("name") or a.get("name") or "?")
                for a in apps
                if isinstance(a, dict)
            ]
            print(f"     subscribed apps: {len(apps)} {names}")
            if not apps:
                print(
                    "     ! no app subscribed to this WABA — set the webhook URL + subscribe 'messages'"
                )
        else:
            print("     subscribed-apps lookup failed — non-fatal.")

    # ---- 3) configured business number vs Meta's display number ----------
    print("\n3) WHATSAPP_BUSINESS_NUMBER vs Meta display number")
    want = _digits(getattr(settings, "whatsapp_business_number", ""))
    got = _digits(display)
    if not want:
        print("  skipped — WHATSAPP_BUSINESS_NUMBER unset.")
    elif not got:
        print("  ! no display_phone_number returned; cannot compare.")
    elif want == got:
        print(f"  ok match (***{want[-4:]})")
    elif want.endswith(got) or got.endswith(want):
        print(
            f"  ~ near-match: configured ***{want[-4:]} vs Meta {display} (country-code/format difference?)"
        )
    else:
        print(f"  ! MISMATCH: configured ***{want[-4:]} but Meta reports {display}")
        print("    The Cloud number is NOT the number the rest of the app is configured with.")

    # ---- verdict ----------------------------------------------------------
    print("\n" + "=" * 62)
    print("RESULT: OK — the Cloud credentials work.")
    print(f"  1. Meta webhook callback URL : {base}/api/webhooks/whatsapp")
    print(f"     (alternative, same token) : {base}/api/wa/webhook")
    print("     verify token             : WHATSAPP_VERIFY_TOKEN (len printed above)")
    print("  2. Subscribe the webhook to the 'messages' field.")
    if provider != "cloud":
        print(
            f"  3. SWITCH: WHATSAPP_PROVIDER is '{provider}' — set it to 'cloud' and restart the app container."
        )
    else:
        print("  3. Provider already 'cloud' — restart the app container so new creds load.")
    print("  4. Keep WHATSAPP_AUTO_SEND=0 until the canary allowlist is set (ban-safety, §5).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
