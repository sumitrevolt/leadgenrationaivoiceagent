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

# 1. Clone or pull repo
if [ -d "$LOCAL_DIR/.git" ]; then
    echo "[1/4] Repo exists, pulling latest..."
    cd "$LOCAL_DIR"
    git fetch origin -q
    git reset --hard origin/main
    echo "      HEAD: $(git log -1 --oneline)"
else
    echo "[1/4] Cloning repo..."
    git clone --depth 50 "$REPO_URL" "$LOCAL_DIR"
    cd "$LOCAL_DIR"
fi

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
