#!/usr/bin/env bash
# fix_dry_run.sh — turn OFF the leftover social canary dry-run gate.
#
# ROOT CAUSE: data/social_engine.json {"dry_run": true} — a 2026-07-11 canary
# gate ("safe E2E validation ... meant for staging + first-customer canary")
# that was never turned back off. With it on, the engine drains the queue,
# FABRICATES PublishResult(ok=True) and marks jobs `published` — while never
# calling Postiz. That is why 6 self-brand jobs read "published" with an empty
# post_id and nothing ever appeared on social.
#
# Safe: `enabled` stays true (unchanged), only `dry_run` flips. The file is
# bind-mounted and read at CALL time, so no container restart is needed.
# Reversible: restore the .bak, or set SOCIAL_DRY_RUN=1 (env wins over file).
set +e
F=/opt/leadgen/data/social_engine.json
echo "===BEFORE==="
cat "$F"; echo

cp -a "$F" "$F.bak-dryrun-$(date +%Y%m%d-%H%M%S)" && echo "backup: $(ls -1 $F.bak-dryrun-* | tail -1)"

python3 - <<'PY'
import json
p = "/opt/leadgen/data/social_engine.json"
d = json.load(open(p))
d["dry_run"] = False          # only this key changes
d["enabled"] = bool(d.get("enabled", True))
json.dump(d, open(p, "w"), indent=None)
print("written:", d)
PY

echo "===AFTER (file)==="
cat "$F"; echo

echo "===LIVE GATE (read at call time — no restart needed)==="
docker exec leadgen_app python3 -c "
from app.social_engine import engine
print('enabled =', engine.enabled(), '| dry_run =', engine._dry_run_enabled())
" 2>&1 | grep -v '"level"'
docker exec leadgen_worker python3 -c "
from app.social_engine import engine
print('worker: enabled =', engine.enabled(), '| dry_run =', engine._dry_run_enabled())
" 2>&1 | grep -v '"level"'

echo "===PROVIDER PATH PROOF (read-only GET — does Postiz actually answer?)==="
docker exec leadgen_app python3 -c "
import asyncio
from app.marketing import postiz_publish as p
print('base =', p._base())
try:
    plats = asyncio.run(p._fetch_integration_platforms())
    print('integrations resolved =', len(plats))
    for k, v in list(plats.items())[:6]:
        print('   ', k[:12], '->', v)
except Exception as e:
    print('fetch err:', type(e).__name__, str(e)[:120])
" 2>&1 | grep -v '"level"'
echo "===FIX_DONE==="
