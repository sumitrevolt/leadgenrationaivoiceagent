#!/usr/bin/env bash
# One-time VPS setup: clone leadsgenai-brain repo as the Obsidian vault directory.
# Run once on VPS: bash scripts/setup_obsidian_vault.sh
#
# Prerequisites:
#   1. Create a private GitHub repo: https://github.com/new  (name: leadsgenai-brain)
#   2. Add VPS SSH key to GitHub: cat ~/.ssh/id_rsa.pub  → GitHub → Settings → SSH Keys
#   3. Set OBSIDIAN_GIT_REMOTE in /opt/leadgen/.env (see below)
#   4. Set OBSIDIAN_SYNC=1 in /opt/leadgen/.env
#
# After this script:
#   On Windows — clone the same repo as your Obsidian vault folder.
#   Install Obsidian Git plugin, set auto-pull every 30 min.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/leadgen}"
VAULT_DIR="$APP_DIR/data/obsidian_staging"

# --- Read remote from env or arg ---
REMOTE="${OBSIDIAN_GIT_REMOTE:-${1:-}}"
if [[ -z "$REMOTE" ]]; then
  echo "[setup_obsidian_vault] ERROR: set OBSIDIAN_GIT_REMOTE env or pass repo URL as arg."
  echo "  Example: bash scripts/setup_obsidian_vault.sh git@github.com:sumitrevolt/leadsgenai-brain.git"
  exit 1
fi

echo "[setup_obsidian_vault] Remote: $REMOTE"
echo "[setup_obsidian_vault] Vault:  $VAULT_DIR"

# --- Clone or reinitialise ---
if [[ -d "$VAULT_DIR/.git" ]]; then
  echo "[setup_obsidian_vault] Vault already a git repo — pulling latest."
  git -C "$VAULT_DIR" pull --ff-only || true
else
  if [[ -d "$VAULT_DIR" ]]; then
    echo "[setup_obsidian_vault] Existing staging dir found — init + add remote."
    git -C "$VAULT_DIR" init
    git -C "$VAULT_DIR" remote add origin "$REMOTE" 2>/dev/null || git -C "$VAULT_DIR" remote set-url origin "$REMOTE"
  else
    echo "[setup_obsidian_vault] Cloning fresh..."
    git clone "$REMOTE" "$VAULT_DIR"
  fi
fi

# --- Create initial folder structure ---
for folder in Leads Clients Agents Decisions Campaigns System Skills Sessions Inbox; do
  mkdir -p "$VAULT_DIR/$folder"
  if [[ ! -f "$VAULT_DIR/$folder/.gitkeep" ]]; then
    touch "$VAULT_DIR/$folder/.gitkeep"
  fi
done

# --- .gitignore for Obsidian internals ---
cat > "$VAULT_DIR/.gitignore" <<'EOF'
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.trash/
*.tmp
EOF

# --- README ---
cat > "$VAULT_DIR/README.md" <<'EOF'
# LeadsGenAI Second Brain

This vault is auto-populated by VPS agents. Do not edit manually in this repo
— use Obsidian locally after pulling. The nightly push job syncs changes.

## Folders

| Folder | Contents |
|--------|---------|
| Leads/ | Per-prospect call/qualification timeline |
| Clients/ | Per-client activity and KB notes |
| Agents/ | Per-staff daily action logs |
| Decisions/ | LLM Council verdicts and ADRs |
| Campaigns/ | Campaign results and A/B outcomes |
| System/ | Prod-check results, health snapshots |
| Sessions/ | Daily digest summaries |
| Skills/ | Key skill docs mirrored from .claude/skills/ |
| Inbox/ | Raw agent outputs not yet categorized |
EOF

# --- Initial commit + push ---
git -C "$VAULT_DIR" add -A
git -C "$VAULT_DIR" commit --allow-empty -m "brain: initial vault structure" || true
git -C "$VAULT_DIR" push -u origin main 2>/dev/null || git -C "$VAULT_DIR" push -u origin master 2>/dev/null || true

echo ""
echo "[setup_obsidian_vault] DONE."
echo ""
echo "Next steps:"
echo "  1. Add to /opt/leadgen/.env:"
echo "       OBSIDIAN_SYNC=1"
echo "       OBSIDIAN_GIT_REMOTE=$REMOTE"
echo "  2. Restart app: docker compose -f docker-compose.vps.yml up -d --no-deps app"
echo "  3. On Windows: git clone $REMOTE <your-obsidian-vault-path>"
echo "  4. Install Obsidian Git plugin → auto-pull every 30 min"
echo "  5. Verify: python -c \"import os; os.environ['OBSIDIAN_SYNC']='1'; from app.platform.obsidian_sync import write_system_health; print(write_system_health('test', '# OK'))\""
