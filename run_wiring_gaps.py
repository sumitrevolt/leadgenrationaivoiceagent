#!/usr/bin/env python
"""Run wiring_gaps() self-diagnosis."""
import os
import sys

# Add repo root to Python path
repo_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, repo_root)

# Determine which python to use
venv_python = os.path.join(repo_root, ".venv", "Scripts", "python.exe")
if os.path.exists(venv_python):
    python_exe = venv_python
    print(f"Using venv: {venv_python}")
else:
    python_exe = sys.executable
    print(f"WARNING: .venv not found at {venv_python}")
    print(f"Using system python: {sys.executable}")

print("\n=== ENVIRONMENT VARIABLES ===")
known_env_vars = [
    "BOSS_FULL_AUTONOMY",
    "GSC_ENABLED",
    "CRM_SYNC",
    "META_APP_ID",
    "META_APP_SECRET",
    "POSTIZ_API_KEY",
    "WAHA_API_KEY",
    "WAHA_BASE_URL",
    "WAHA_SESSION",
    "ZOHO_CLIENT_ID",
    "ZOHO_CLIENT_SECRET",
    "ZOHO_REFRESH_TOKEN",
    "HUBSPOT_API_KEY",
    "GSC_SERVICE_ACCOUNT_JSON",
    "GOOGLE_SHEETS_CREDENTIALS",
]
for var in known_env_vars:
    val = os.getenv(var, "MISSING")
    print(f"{var}: {val}")

print("\n=== RUNNING wiring_gaps() ===")
try:
    from app.platform.automation_health import wiring_gaps

    gaps = wiring_gaps()

    if not gaps:
        print("No wiring gaps detected!")
    else:
        print(f"Found {len(gaps)} wiring gap(s):\n")
        for i, gap in enumerate(gaps, 1):
            print(f"{i}. [{gap['key']}]")
            print(f"   Flag ON: {gap['flag_on']}")
            print(f"   Missing: {gap['missing']}")
            print(f"   Note: {gap['note']}")
            print()

except ImportError as e:
    print(f"Import error: {e}")
    print("\nThis may be due to missing dependencies or environment variables.")
    print("Checking for commonly needed env vars that might cause import issues...")
    # Try to give hints based on error message
    err_str = str(e).lower()
    if "zoho" in err_str or "crm_sync" in err_str:
        print("  -> Possible missing Zoho CRM credentials:")
        print("     ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN")
    if "gsc" in err_str or "google" in err_str or "sheets" in err_str:
        print("  -> Possible missing Google service account credentials:")
        print("     GSC_SERVICE_ACCOUNT_JSON, GOOGLE_SHEETS_CREDENTIALS")
    if "postiz" in err_str:
        print("  -> Possible missing Postiz API key:")
        print("     POSTIZ_API_KEY")
    if "whatsapp" in err_str or "waha" in err_str:
        print("  -> Possible missing WhatsApp/Waha credentials:")
        print("     WAHA_API_KEY, WAHA_BASE_URL, WAHA_SESSION")
    if "meta" in err_str or "facebook" in err_str:
        print("  -> Possible missing Meta credentials:")
        print("     META_APP_ID, META_APP_SECRET")
except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()