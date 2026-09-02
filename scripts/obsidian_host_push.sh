#!/usr/bin/env bash
# Obsidian Second Brain — nightly host-side git push.
# Agents write markdown into the bind-mounted vault from the container; the
# container has no git/SSH, so the HOST does the push (deploy key lives here).
# Cron: 45 20 * * *  (20:45 UTC = 02:15 IST)
set -euo pipefail
VAULT=/opt/leadgen/data/obsidian_staging
[ -d "$VAULT/.git" ] || { echo "$(date -u) vault git missing — skip"; exit 0; }
cd "$VAULT"
export GIT_SSH_COMMAND='ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/root/.ssh/known_hosts'
git add -A
git -c user.email='admin@leadsgenai.in' -c user.name='LeadsGenAI VPS' commit --allow-empty -m "brain: nightly sync $(date -u +%Y-%m-%d)" >/dev/null 2>&1 || true
# self-heal: integrate remote changes before pushing (prevents 'fetch first' lockup)
git fetch origin 2>/dev/null || true
git merge --no-edit -m "brain: auto-merge remote before push" origin/main 2>/dev/null || true
if git push 2>&1; then
  echo "$(date -u) obsidian push OK"
else
  echo "$(date -u) obsidian push FAILED" >&2
  exit 1
fi
