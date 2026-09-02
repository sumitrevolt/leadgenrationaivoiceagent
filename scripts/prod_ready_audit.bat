@echo off
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o StrictHostKeyChecking=no root@72.61.245.204

echo [1] Container health...
%SSH% "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep leadgen" > C:\Users\Ratanshila\Documents\leadgenrationaiagent\scripts\prod_ready.log 2>&1

echo [2] App health + route count...
%SSH% "curl -s http://localhost:8000/health && echo '' && curl -s http://localhost:8000/openapi.json | python3 -c \"import sys,json; d=json.load(sys.stdin); print('ROUTES:', len(d.get('paths',{})))\"" >> C:\Users\Ratanshila\Documents\leadgenrationaiagent\scripts\prod_ready.log 2>&1

echo [3] Key env flags status...
%SSH% "python3 -c \"import subprocess; lines=open('/opt/leadgen/.env').readlines(); flags=['RAZORPAY_KEY_ID','RAZORPAY_KEY_SECRET','RAZORPAY_WEBHOOK_SECRET','OUTREACH_DAILY_CAP','REPLY_AGENT','REPLY_AUTO_SEND','SALES_ENGINE','DUNNING_ENGINE','GROQ_API_KEY','OPENROUTER_API_KEY','POLLINATIONS_API_KEY','GSTIN','EXOTEL_SID']; env={l.split('=')[0].strip():l.split('=',1)[1].strip() for l in lines if '=' in l and not l.startswith('#')}; [print(f, '=', ('SET('+str(len(env[f]))+'ch)' if f in env and env[f] else 'MISSING')) for f in flags]\"" >> C:\Users\Ratanshila\Documents\leadgenrationaiagent\scripts\prod_ready.log 2>&1

echo [4] Razorpay keys test...
%SSH% "docker exec leadgen_app python3 -c \"import os,httpx,base64; k=os.environ.get('RAZORPAY_KEY_ID',''); s=os.environ.get('RAZORPAY_KEY_SECRET',''); auth=base64.b64encode(f'{k}:{s}'.encode()).decode(); r=httpx.get('https://api.razorpay.com/v1/plans',headers={'Authorization':f'Basic {auth}'},timeout=8); print('RAZORPAY:', r.status_code, 'OK' if r.status_code==200 else r.text[:80])\"" >> C:\Users\Ratanshila\Documents\leadgenrationaiagent\scripts\prod_ready.log 2>&1

echo [5] Self-improve runs last 5...
%SSH% "docker exec leadgen_app python3 -c \"import json,os; f='/app/data/self_improve_runs.jsonl'; runs=open(f).readlines()[-5:] if os.path.exists(f) else []; [print(json.loads(r).get('action','?'), json.loads(r).get('at','')[:16]) for r in runs]\"" >> C:\Users\Ratanshila\Documents\leadgenrationaiagent\scripts\prod_ready.log 2>&1

echo [6] Prospects + deals + signups summary...
%SSH% "docker exec leadgen_app python3 -c \"from app.platform import prospector; from app.marketing import sales_pipeline; from app.api import customer_auth; ps=prospector.list_prospects(limit=9999); print('prospects:', len(ps)); deals=sales_pipeline.list_deals(); print('deals:', len(deals)); print('deal_stages:', {d.get('stage') for d in deals}); logins=customer_auth.list_logins() if hasattr(customer_auth,'list_logins') else []; print('signups/logins:', len(logins))\" 2>/dev/null || echo 'summary error'" >> C:\Users\Ratanshila\Documents\leadgenrationaiagent\scripts\prod_ready.log 2>&1

echo done
