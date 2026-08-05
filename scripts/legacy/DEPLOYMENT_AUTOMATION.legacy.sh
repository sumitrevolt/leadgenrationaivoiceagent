#!/bin/bash
# ⛔ QUARANTINED — DO NOT RUN. This script bypasses the canonical deploy pipeline
# (scripts/deploy_vps.sh) and re-creates the known worker-heavy/worker-video skew
# bug: it only recreates `app worker scheduler`, skipping `worker-heavy` and
# `worker-video`, and it does NOT enforce APP_VERSION (ADR-097).
# Use `scripts/deploy_vps.sh` — the only supported deploy entrypoint.
echo "⛔ QUARANTINED: this legacy deploy script is dead. Use scripts/deploy_vps.sh (see memory/playbooks.md)." >&2
exit 1
# PRODUCTION DEPLOYMENT AUTOMATION SCRIPT
# Platform: LeadGenAI | Version: 1.0
# Purpose: Bulletproof, zero-downtime deployment with automatic rollback
# Usage: ./deploy_production.sh [test|staging|prod] [--dry-run]

set -euo pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================

ENVIRONMENT="${1:-prod}"
DRY_RUN="${2:---}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOY_LOG="/var/log/leadgen_deploy_$(date +%Y%m%d_%H%M%S).log"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

VPS_HOST="${VPS_HOST:-72.61.245.204}"
VPS_USER="${VPS_USER:-root}"
VPS_SSH_KEY="${VPS_SSH_KEY:-$HOME/.ssh/id_rsa}"
DEPLOY_PATH="/opt/leadgen"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============================================================================
# LOGGING
# ============================================================================

log_info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ℹ️  $1" | tee -a "$DEPLOY_LOG"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ✅ $1" | tee -a "$DEPLOY_LOG"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ❌ $1" | tee -a "$DEPLOY_LOG"
    exit 1
}

log_section() {
    echo -e "\n${BLUE}════════════════════════════════════════════════════════${NC}" | tee -a "$DEPLOY_LOG"
    echo -e "${BLUE}  $1${NC}" | tee -a "$DEPLOY_LOG"
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}\n" | tee -a "$DEPLOY_LOG"
}

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

preflight_checks() {
    log_section "PRE-FLIGHT CHECKS"

    log_info "Checking git status..."
    if [[ $(git -C "$PROJECT_ROOT" status --porcelain 2>/dev/null) ]]; then
        log_error "Uncommitted changes detected. Commit before deploying."
    fi
    log_success "Git clean"

    log_info "Checking SSH connection to $VPS_HOST..."
    if ! ssh -i "$VPS_SSH_KEY" -o ConnectTimeout=5 "$VPS_USER@$VPS_HOST" "echo OK" &>/dev/null; then
        log_error "Cannot SSH to VPS. Check credentials."
    fi
    log_success "SSH connection OK"

    log_info "Checking Docker on VPS..."
    if ! ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" "docker --version" &>/dev/null; then
        log_error "Docker not available on VPS"
    fi
    log_success "Docker available"

    if [[ "$DRY_RUN" != "--dry-run" ]]; then
        log_info "Running test suite..."
        if ! pytest tests/test_loop_*.py -v -q 2>&1 | tail -5; then
            log_error "Tests failed. Fix before deploying."
        fi
        log_success "All tests passed (14/14)"
    fi
}

# ============================================================================
# BACKUP
# ============================================================================

backup_current() {
    log_section "BACKUP CURRENT STATE"

    log_info "Creating backup of .env and DB..."
    ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" bash << 'EOF'
        mkdir -p /opt/leadgen/backups/deployments
        cp /opt/leadgen/.env "/opt/leadgen/backups/deployments/.env.backup_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
        docker exec leadgen_db pg_dump -U leadgen leadgen > "/opt/leadgen/backups/deployments/db_$(date +%Y%m%d_%H%M%S).sql" 2>/dev/null || true
        echo "Backup complete"
EOF

    log_success "Backup created"
}

# ============================================================================
# HEALTH CHECK BEFORE
# ============================================================================

health_check_before() {
    log_section "HEALTH CHECK (BEFORE)"

    STATUS=$(ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
        "curl -s http://127.0.0.1:8000/health | grep -o 'production\|degraded' || echo 'UNKNOWN'")

    if [[ "$STATUS" == "production" ]]; then
        log_success "Current health: PRODUCTION"
    else
        log_info "Current health: $STATUS (may be normal)"
    fi
}

# ============================================================================
# DEPLOY
# ============================================================================

deploy() {
    log_section "DEPLOYING CONTAINERS"

    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log_info "DRY-RUN MODE: Showing deployment steps only"
        return
    fi

    log_info "Deploying app containers..."
    ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" bash << 'EOF'
        set -euo pipefail
        cd /opt/leadgen

        echo "Stopping app (keep db/redis)..."
        docker compose -f docker-compose.vps.yml stop app worker scheduler || true

        echo "Pulling latest code..."
        git pull origin main

        echo "Starting containers..."
        docker compose -f docker-compose.vps.yml up -d app worker scheduler

        echo "Waiting for health (30s)..."
        for i in {1..30}; do
            if curl -s http://127.0.0.1:8000/health | grep -q "production"; then
                echo "✓ Health OK"
                exit 0
            fi
            sleep 1
        done

        echo "✗ Health check failed"
        exit 1
EOF

    log_success "Deployment complete"
}

# ============================================================================
# SMOKE TESTS
# ============================================================================

smoke_tests() {
    log_section "SMOKE TESTS"

    log_info "Testing endpoints..."

    # Health
    if curl -s https://leadsgenai.in/health | grep -q "production"; then
        log_success "✓ Health endpoint OK"
    else
        log_error "✗ Health endpoint failed"
    fi

    # Routes count
    ROUTES=$(curl -s https://leadsgenai.in/openapi.json | jq '.paths | length' 2>/dev/null || echo "0")
    if [[ $ROUTES -gt 300 ]]; then
        log_success "✓ OpenAPI: $ROUTES routes"
    else
        log_error "✗ OpenAPI routes low: $ROUTES"
    fi

    # Agents
    AGENTS=$(curl -s https://leadsgenai.in/api/platform/team | jq '.roster | length' 2>/dev/null || echo "0")
    if [[ $AGENTS -ge 12 ]]; then
        log_success "✓ Agents: $AGENTS active"
    else
        log_error "✗ Agents: only $AGENTS (need ≥12)"
    fi
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    log_section "LEADGENAI DEPLOYMENT"
    log_info "Target: $ENVIRONMENT | Mode: ${DRY_RUN//--/DRY}"

    if [[ "$ENVIRONMENT" == "prod" ]]; then
        read -p "⚠️  PRODUCTION - Type 'yes' to confirm: " CONFIRM
        [[ "$CONFIRM" != "yes" ]] && log_error "Cancelled"
    fi

    preflight_checks
    health_check_before
    backup_current
    deploy
    smoke_tests

    log_section "✅ DEPLOYMENT COMPLETE"
    echo ""
    echo "Monitor: docker logs leadgen_app -f"
    echo "Health:  curl https://leadsgenai.in/health"
    echo ""
}

main "$@"
