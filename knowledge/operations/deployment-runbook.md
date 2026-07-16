---
type: Runbook
title: Deployment runbook
description: Canonical VPS deploy path — APP_VERSION mandatory, no blind reset.
tags: [deploy, vps, docker]
timestamp: 2026-07-17T00:00:00Z
resource: scripts/deploy_vps.sh
---

# Deployment runbook

1. Push to `origin/main` from Windows (`C:\PROGRA~1\Git\cmd\git.exe`).
2. SSH with Git OpenSSH: `C:\PROGRA~1\Git\usr\bin\ssh.exe -i ~/.ssh/id_rsa root@72.61.245.204`.
3. Canonical: `cd /opt/leadgen && setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &` then poll `/tmp/dep.log`.
4. Script enforces `APP_VERSION=<sha>` (refuse `:latest`), deploys all 5 app-image services, verifies `/health.version` + skew + smoke.
5. Never `git reset --hard` blind on VPS (tree chronically dirty). Never `--remove-orphans` on Postiz compose.

Full detail: `memory/playbooks.md` + skill `hostinger-deploy`.
