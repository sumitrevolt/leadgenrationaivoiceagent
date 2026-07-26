#!/usr/bin/env bash
# Hostinger Managed Hermes Agent — one-time bootstrap inside the Hermes sandbox.
# Phase-1 = read-only daily project health reporter. No write access to main repo or VPS.
# Naming: Hostinger ka "Hermes Agent" cloud product (NOT our internal infra_handler Hermes).
# Docs: docs/HOSTINGER_HERMES_SETUP.md

set -e
set -o pipefail

REPO_URL="${REPO_URL:-https://github.com/sumitrevolt/leadgenrationaivoiceagent.git}"
LOCAL_DIR="${LOCAL_DIR:-$HOME/leadgen}"
CONFIG_DIR="$HOME/.hermes"
CONFIG_FILE="$CONFIG_DIR/config.env"

echo "===== Hostinger Hermes bootstrap (read-only Phase-1) ====="
echo "Target dir: $LOCAL_DIR"
echo "Config:     $CONFIG_FILE"
echo ""

# ------------------------------------------------------- bootstrap safety gate
# This script used to branch on `[ -d "$LOCAL_DIR/.git" ]` and, when a checkout
# already existed, run `git reset --hard origin/main` against it. LOCAL_DIR is
# an environment variable, so `LOCAL_DIR=/opt/leadgen` pointed that reset at the
# production checkout, which still holds the live invoice, consent and
# suppression ledgers and 182 MB of DPDP call recordings. The comment at the top
# of this file says "sandbox", and the DEFAULT is a sandbox -- but a default is
# not a restriction, and a comment is not an enforcement mechanism.
#
# Bootstrap is now FRESH-HOST ONLY. An existing installation is refused outright
# rather than upgraded in place: bootstrap must not become a second deployment
# implementation. Operators with an existing install use the protected release
# parent (scripts/deploy_vps.sh) or an explicitly protected recovery path.
#
# Exit codes (distinct from the release parent's 90/91 so logs are unambiguous):
#   92 = refused, target already has an installation
#   93 = invalid target (relative, traversal, UNC, control chars, not a dir)
#   94 = classifier/preflight unavailable
#
# This runs BEFORE any mkdir, clone, fetch, reset, pip install or config write.
_bootstrap_preflight="$(dirname "$0")/runtime_data_preflight.py"
if [ ! -r "$_bootstrap_preflight" ]; then
    echo "FATAL: bootstrap preflight not found or unreadable: $_bootstrap_preflight"
    echo "       Refusing to bootstrap unguarded."
    exit 94
fi

_bootstrap_py="${PYTHON_BIN:-python3}"
echo "=== bootstrap preflight (check-bootstrap) ==="
# NOT `if ! cmd; then _rc=$?` -- inside that branch `$?` is the status of the
# NEGATED pipeline, i.e. 0, so a refusal would have exited 0 and the caller
# would read it as success. Capture the real status first.
set +e
"$_bootstrap_py" "$_bootstrap_preflight" check-bootstrap --target "$LOCAL_DIR"
_rc=$?
set -e
if [ "$_rc" -ne 0 ]; then
    echo ""
    echo "FATAL: bootstrap preflight REFUSED this target (rc=$_rc)."
    echo "       No clone, fetch, reset or config write has been performed."
    exit "$_rc"
fi
echo "=== preflight passed — target proven fresh ==="

# 1. Clone repo (fresh target only — the reset branch is gone by design).
echo "[1/4] Cloning repo..."
git clone --depth 50 "$REPO_URL" "$LOCAL_DIR"
cd "$LOCAL_DIR"

# 2. Lean Python deps (only what hostinger_hermes_daily_report.py needs).
#    No FastAPI/Postgres/Qdrant/ML — Hermes is read-only, not running the app.
echo "[2/4] Installing lean deps..."
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "ERROR: python not found in sandbox"
    exit 1
fi

# httpx for async, requests as fallback (stdlib smtplib for email)
$PY -m pip install --quiet --user --upgrade httpx requests 2>&1 | tail -2 || true

# 3. Config template
echo "[3/4] Writing config template..."
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_FILE" ]; then
    cat > "$CONFIG_FILE" <<'EOF'
# Hostinger Hermes daily-report config. Edit this, then re-run bootstrap.
# Docs: docs/HOSTINGER_HERMES_SETUP.md

# Email recipient
NOTIFY_EMAIL=admin@leadsgenai.in

# SMTP (Hostinger mail — copy creds from main project .env on VPS)
SMTP_HOST=smtp.hostinger.com
SMTP_PORT=465
SMTP_USERNAME=admin@leadsgenai.in
SMTP_PASSWORD=

# Optional: ntfy push for instant alerts
NTFY_URL=
NTFY_TOPIC=
NTFY_TOKEN=

# Probe target
HEALTH_URL=https://leadsgenai.in/health
READY_URL=https://leadsgenai.in/health/ready
EOF
    echo "      Template written to $CONFIG_FILE — edit credentials before scheduling."
else
    echo "      Config exists, leaving untouched."
fi
chmod 600 "$CONFIG_FILE"

# 4. Pehla dry-run (no email send)
echo "[4/4] Test-run daily report (dry-run)..."
if [ -f "scripts/hostinger_hermes_daily_report.py" ]; then
    $PY scripts/hostinger_hermes_daily_report.py --dry-run 2>&1 | head -40 || true
else
    echo "      WARN: scripts/hostinger_hermes_daily_report.py not yet in repo"
fi

echo ""
echo "===== Bootstrap done ====="
echo ""
echo "Next steps:"
echo "  1. Edit $CONFIG_FILE — paste SMTP_PASSWORD from main project .env"
echo "  2. Test send: cd $LOCAL_DIR && $PY scripts/hostinger_hermes_daily_report.py"
echo "  3. Schedule (cron):  30 9 * * *  cd $LOCAL_DIR && $PY scripts/hostinger_hermes_daily_report.py >> ~/hermes_daily.log 2>&1"
echo ""
