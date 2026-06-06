#!/usr/bin/env bash
# ==========================================================================
# LeadGen AI — One-command VPS deploy (Ubuntu, run as root)
# Usage on the VPS:
#   curl -fsSL https://raw.githubusercontent.com/sumitrevolt/leadgenrationaivoiceagent/main/deploy_vps.sh | bash
# Optional (set Gemini key inline):
#   curl -fsSL https://raw.githubusercontent.com/sumitrevolt/leadgenrationaivoiceagent/main/deploy_vps.sh | GEMINI_API_KEY=YOUR_KEY bash
# ==========================================================================
set -u
APP_DIR=/opt/leadgen
REPO=https://github.com/sumitrevolt/leadgenrationaivoiceagent.git
DOMAIN="${DOMAIN:-leadsgenai.in}"
GEMINI_API_KEY="${GEMINI_API_KEY:-}"

echo "==================================================================="
echo "  LeadGen AI VPS deploy starting (domain: $DOMAIN)"
echo "==================================================================="

echo "===STEP 1: system packages==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git curl ca-certificates debian-keyring debian-archive-keyring apt-transport-https ffmpeg || true

echo "===STEP 2: install Caddy (auto-HTTPS reverse proxy)==="
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy || true
fi

echo "===STEP 3: get the code==="
if [ -d "$APP_DIR/.git" ]; then
  cd "$APP_DIR" && git fetch --all && git reset --hard origin/main
else
  rm -rf "$APP_DIR"
  git clone "$REPO" "$APP_DIR"
  cd "$APP_DIR"
fi

echo "===STEP 4: python venv + dependencies (few minutes)==="
cd "$APP_DIR"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip -q
# install full requirements minus heavy browser scrapers (not needed for serving)
grep -v -E "^(playwright|selenium)" requirements.txt > /tmp/req.txt || cp requirements.txt /tmp/req.txt
pip install -r /tmp/req.txt -q || pip install -r requirements-core.txt -q
pip install -q "python-jose[cryptography]" "passlib[bcrypt]" aiosmtplib python-multipart apscheduler || true

echo "===STEP 5: .env config==="
if [ ! -f .env ]; then cp .env.example .env 2>/dev/null || touch .env; fi
SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
set_env() { local k="$1" v="$2"; if grep -q "^$k=" .env; then sed -i "s|^$k=.*|$k=$v|" .env; else echo "$k=$v" >> .env; fi; }
# Keep existing secrets across re-deploys (a fresh secret on every deploy
# would log everyone out / invalidate JWTs). Generate only when missing.
if ! grep -qE "^SECRET_KEY=.{32,}" .env; then
  set_env SECRET_KEY "$SECRET"
fi
if ! grep -qE "^JWT_SECRET_KEY=.{32,}" .env; then
  set_env JWT_SECRET_KEY "$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")"
fi
set_env APP_ENV production
set_env DEBUG false
set_env LOG_LEVEL INFO
set_env DATABASE_URL "sqlite:///$APP_DIR/leadgen.db"
set_env CORS_ORIGINS "[\"https://$DOMAIN\",\"https://www.$DOMAIN\"]"
set_env DEFAULT_LLM gemini-2.5-flash
set_env LLM_PROVIDER gemini
set_env TIMEZONE Asia/Kolkata
set_env WORKING_HOURS_START 09:00
set_env WORKING_HOURS_END 21:00
set_env TELEPHONY_PROVIDER simulation
if [ -n "$GEMINI_API_KEY" ]; then set_env GEMINI_API_KEY "$GEMINI_API_KEY"; fi
# Strip inline comments (KEY=value  # note) — pydantic-settings can't parse them.
sed -i 's/[[:space:]]\+#.*$//' .env

echo "===STEP 6: seed demo database==="
export DATABASE_URL="sqlite:///$APP_DIR/leadgen.db"
.venv/bin/python scripts/seed_demo_data.py --force || echo "(seed skipped/failed, continuing)"

echo "===STEP 7: systemd service (keeps app running 24/7)==="
cat > /etc/systemd/system/leadgen.service <<EOF
[Unit]
Description=LeadGen AI Voice Agent
After=network.target

[Service]
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --timeout-keep-alive 30
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable leadgen
systemctl restart leadgen

echo "===STEP 8: Caddy reverse proxy + auto HTTPS==="
# Free ports 80/443 if the VPS template's Traefik is holding them.
docker stop traefik-traefik-1 2>/dev/null || true
docker update --restart=no traefik-traefik-1 2>/dev/null || true
cat > /etc/caddy/Caddyfile <<EOF
http://72.61.245.204 {
    reverse_proxy 127.0.0.1:8000
}
$DOMAIN, www.$DOMAIN {
    reverse_proxy 127.0.0.1:8000
}
EOF
systemctl restart caddy 2>/dev/null || caddy reload --config /etc/caddy/Caddyfile 2>/dev/null || true

echo ""
echo "==================================================================="
echo "  DEPLOY DONE"
echo "-------------------------------------------------------------------"
sleep 4
echo "App service status:"; systemctl is-active leadgen
echo "Health check:"; curl -s -m 10 http://127.0.0.1:8000/health || echo "(starting...)"
echo ""
echo "  Direct (works now):   http://72.61.245.204:8000/app/test-call"
echo "  Domain (after DNS):   https://$DOMAIN/app/test-call"
echo ""
echo "  Add Gemini key later: nano $APP_DIR/.env  (set GEMINI_API_KEY=...) then: systemctl restart leadgen"
echo "==================================================================="
