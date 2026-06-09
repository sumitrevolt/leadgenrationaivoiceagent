---
description: Ek change ko live VPS pe ship karo — verify, push, deploy, health-gate (LeadGen AI loop).
---
# /ship — LeadGen AI deploy loop

Live revenue site **leadsgenai.in** — har deploy verified + health-gated. Detail skills: `ship-checklist`, `leadgen-ops`, `hostinger-deploy`.

## Steps
1. **`/verify full`** — red ho to ship MAT karo.
2. **Commit + push** (Windows git `C:\PROGRA~1\Git\cmd\git.exe`). Commit message SIMPLE rakho — cmd special chars (`()` `+` `/` `—`) "pathspec" error karte → sirf hyphen/comma. **Secrets kabhi commit nahi** (sirf `.env`).
3. **VPS deploy** (Git ssh: `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204`). Complex remote command = **base64-over-ssh** (`&`/`<`/`{{}}` SSH quoting todta): `echo <b64> | base64 -d | bash`. Loop: `cd /opt/leadgen && git fetch origin && git merge --ff-only origin/main && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d app`.
4. **Health gate**: `sleep 12; curl -s /health` → `environment:production`. Naye `@app.get` page-routes Docker rebuild se bake hote — phir bhi route curl-verify karo (200). Config bind-mounts (alertmanager/tempo) = `up -d --force-recreate <svc>`.
5. Unhealthy → rollback (prev image retag ya `git revert`) + re-verify. **Prod kabhi red mat chhodo.**

`$ARGUMENTS`: optional commit message.
