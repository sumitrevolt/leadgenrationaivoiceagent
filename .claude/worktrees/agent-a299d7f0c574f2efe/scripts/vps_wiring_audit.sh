#!/usr/bin/env bash
set +e
echo "######## 1. FRESH IMPORT WARNINGS (router not mounted / import fail / not defined) ########"
docker exec leadgen_app python -c "import app.main" 2>&1 | grep -iE 'not mounted|not defined|failed|importerror|modulenotfound|could not|disabled|skip' | grep -ivE 'OTel disabled|MCP exposure disabled|sqlite checkpointer' | head -30
echo "   (agar upar khaali = koi router/import warning nahi)"

echo ""
echo "######## 2. ROUTER MOUNT COUNT (include_router calls vs registered) ########"
docker exec leadgen_app python -c "
from app.main import app
from fastapi import APIRouter
paths=set()
for r in app.routes:
    p=getattr(r,'path','')
    if p.startswith('/api/'): paths.add(p.split('/')[2] if len(p.split('/'))>2 else p)
print('  /api prefixes mounted:', len(paths))
print('  prefixes:', sorted(paths))
" 2>&1 | grep -vE 'OTel|Sentry|Middleware|Exception|Billing|Email|WhatsApp|Campaign|Scraper|langgraph|Tenant|MCP|database|vector|feedback|pipeline|trainer|optimizer' | tail -8

echo ""
echo "######## 3. INTEGRATION HEALTH (kaunsi integration broken) ########"
docker exec leadgen_app python -c "
try:
    from app.platform import integration_health as ih
    s = ih.snapshot() if hasattr(ih,'snapshot') else (ih.status() if hasattr(ih,'status') else {})
    print('  integration_health:', str(s)[:400])
except Exception as e: print('  ih err', str(e)[:80])
" 2>&1 | grep -vE 'OTel|Sentry|Middleware|Exception|Billing|Email|WhatsApp|Campaign|Scraper|langgraph|Tenant|MCP|database|vector|feedback|pipeline|trainer|optimizer|initialized' | tail -4

echo ""
echo "######## 4. ALL 12 STAFF JOBS — trigger + success check ########"
docker exec leadgen_app python -c "
import asyncio
from app.platform import team_scheduler as ts
jobs=['growth','ops','reply_triage','watchdog','onboard','content','digest','blog','prospect','email_outreach','qa','trainer','standup']
async def go():
    for j in jobs:
        try:
            r = await asyncio.wait_for(ts._run_job_inner(j) if hasattr(ts,'_run_job_inner') else ts._run_job(j), timeout=40)
            print(f'  {j:16s} OK -> {str(r)[:45]}')
        except asyncio.TimeoutError:
            print(f'  {j:16s} TIMEOUT(>40s, heavy — likely ok async)')
        except Exception as e:
            print(f'  {j:16s} ERR -> {str(e)[:60]}')
asyncio.run(go())
" 2>&1 | grep -E '^  [a-z]' | tail -16

echo ""
echo "######## 5. DLQ after job sweep (naye failures?) ########"
docker exec leadgen_redis redis-cli LLEN dlq:failed_tasks
echo "######## DONE ########"
