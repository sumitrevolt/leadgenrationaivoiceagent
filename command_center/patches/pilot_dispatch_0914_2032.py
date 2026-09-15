import json, os
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
now = datetime.now(IST)
ts = now.strftime('%Y-%m-%dT%H:%M:%S+05:30')
ts_short = now.strftime('%H:%M')

base = r'C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data'

# ---------- TASKS.JSON ----------
tasks_path = os.path.join(base, 'tasks.json')
with open(tasks_path, encoding='utf-8') as f:
    tasks = json.load(f)

evidence_map = {
    'OPS-144': ts_short + ' IST RE-CHECK: Loop STILL DEAD (proc 0, crontab 0). LLM chain 0/9.',
    'ENG-144': ts_short + ' IST RE-CHECK: LLM chain STILL 0/9. 14 days.',
    'OWNER-145': ts_short + ' IST ESCALATION: LLM 0/9 14d. Revenue BLOCKED.',
    'SAL-143': ts_short + ' IST RE-CHECK: Jiya 0 replies 36h. DID blocked.',
    'HNT-141': ts_short + ' IST RE-CHECK: DB uncontacted mobile = 1. Pool EXHAUSTED.',
    'GRD-142': ts_short + ' IST RE-CHECK: LLM audit PENDING. Output not received.',
    'OPS-145': ts_short + ' IST RE-CHECK: venv path broken. Loop DOWN.',
}

for t in tasks:
    if t['id'] in evidence_map:
        t['evidence'] = (t.get('evidence', '') + ' ||| ' + evidence_map[t['id']]).strip(' |||')
        t['updated_at'] = ts

# Status updates
for t in tasks:
    if t['id'] in ['OPS-144', 'ENG-144', 'OWNER-145', 'SAL-143', 'HNT-141', 'GRD-142', 'OPS-145']:
        if t['status'] in ['🆕 NEW', '🟠 NEEDS DECISION', '🔴 BLOCKED']:
            pass  # keep status, evidence updated

new_tasks = [
    {
        'id': 'SAL-146',
        'objective': 'P0 JIYA RETENTION FOLLOW-UP (WA ONLY). Yesterday 08:32 IST WA sent (3EB090D6E980D47A52448B), 0 replies in 36h. TASK: (1) Send 2nd WA retention msg via WAHA :3002/api/sendText — "Hi Jiya, final reminder: 30-day free pause OR 40% off (₹899/mo) — reply YES to activate. Offer expires tonight." (2) If no reply by tomorrow 09:00 IST, mark CHURNED in DB. Evidence: WA msg ID + screenshot OR DB churn flag.',
        'status': '🆕 NEW',
        'owner': 'sales',
        'priority': 'P0',
        'deadline': '2026-09-15T09:00:00+05:30',
        'assigned_at': ts,
        'updated_at': ts,
        'acceptance': '',
        'evidence': ts_short + ' IST: SAL-143 stale 36h no reply. Escalated. WAHA route: container http://waha:3000/api/sendText OR host :3002.'
    },
    {
        'id': 'HNT-146',
        'objective': 'P0 LEAD POOL REFRESH. DB has only 1 uncontacted mobile lead (was 10,587). Pool EXHAUSTED. TASK: (1) Google Maps scrape: 50 B2B leads (niche=makeover/beauty salon, city=Pune/Mumbai, min_rating=4.0). (2) DND-scrub against NDNC. (3) Write to /opt/leadgen/data/qualified_leads_20260915.csv. (4) Insert into DB leads table (status=new, source=gmaps_20260915). Evidence: CSV path + row count + DB INSERT count.',
        'status': '🆕 NEW',
        'owner': 'hunter',
        'priority': 'P0',
        'deadline': '2026-09-15T12:00:00+05:30',
        'assigned_at': ts,
        'updated_at': ts,
        'acceptance': '',
        'evidence': ts_short + ' IST: DB uncontacted mobile = 1. Pool exhausted. HNT-141 stale.'
    },
    {
        'id': 'PLT-146',
        'objective': 'P0 VOBIZ EGRESS ROOT CAUSE + FAILOVER. api.vobiz.in UNREACHABLE (HTTP 000, TCP block, 14+ days). TASK: (1) Test DNS: nslookup api.vobiz.in from VPS. (2) Test curl with timeout 10s + verbose. (3) If egress blocked: check iptables, check Caddy reverse_proxy config. (4) If unfixable: activate Jio SIP fallback (RMS Tech Rajnikant 080-47652298). Evidence: DNS test + curl verbose + root-cause verdict OR Jio SIP DID proof.',
        'status': '🆕 NEW',
        'owner': 'platform',
        'priority': 'P0',
        'deadline': '2026-09-15T12:00:00+05:30',
        'assigned_at': ts,
        'updated_at': ts,
        'acceptance': '',
        'evidence': ts_short + ' IST: Vobiz API still unreachable. PLT-141 stale.'
    },
    {
        'id': 'ENG-146',
        'objective': 'P0 LLM CHAIN FIX. ALL 9 FREE PROVIDERS FAILED (Groq TPD, Mistral 429, Gemini 20/day, Cerebras pay, SambaNova pay, NVIDIA dead, Ollama conn, OpenRouter paid). TASK: (1) Test ANY new free LLM API (Together AI, Fireworks, Deepinfra, etc.) with simple curl. (2) If found: add to /opt/leadgen/.env + free_ai.py chat() chain. (3) If none: implement rule-based fallback script (no LLM) — pre-recorded voice prompts for common scenarios. Evidence: Working provider test proof OR fallback script commit sha.',
        'status': '🆕 NEW',
        'owner': 'engineering',
        'priority': 'P0',
        'deadline': '2026-09-15T18:00:00+05:30',
        'assigned_at': ts,
        'updated_at': ts,
        'acceptance': '',
        'evidence': ts_short + ' IST: ENG-144 stale 14d. LLM chain 0/9 STILL. Expanded scope.'
    },
    {
        'id': 'GRD-146',
        'objective': 'P1 LLM CHAIN AUDIT. Guardian output llm_chain_status.json NOT received. TASK: (1) Test all 9 free providers from VPS with curl. (2) Check if any new free provider works. (3) Verify ENG-146 fallback script if LLM still 0/9. (4) Output llm_chain_status.json to command_center/data/. Evidence: Provider test results + verdict.',
        'status': '🆕 NEW',
        'owner': 'guardian',
        'priority': 'P1',
        'deadline': '2026-09-15T18:00:00+05:30',
        'assigned_at': ts,
        'updated_at': ts,
        'acceptance': '',
        'evidence': ts_short + ' IST: GRD-142 stale. Reassigned.'
    },
    {
        'id': 'OPS-146',
        'objective': 'P1 LOOP VENV PATH FIX + PREP. Loop venv path STILL broken (/opt/leadgen/venv/bin/python missing). Loop DOWN 14d. TASK: (1) Fix crontab to use /usr/bin/python3 or /app/.venv/bin/python3. (2) Verify DATABASE_URL exports correctly at loop start. (3) Add circuit-breaker: if DID not owned, stop + alert. (4) Prep for LLM+DID fix restart. Evidence: crontab entry + venv path proof + circuit-breaker script.',
        'status': '🆕 NEW',
        'owner': 'operations',
        'priority': 'P1',
        'deadline': '2026-09-15T18:00:00+05:30',
        'assigned_at': ts,
        'updated_at': ts,
        'acceptance': '',
        'evidence': ts_short + ' IST: OPS-145 stale. venv path still broken.'
    },
    {
        'id': 'BRD-146',
        'objective': 'P2 FUNNEL SNAPSHOT. BRD-141 stale. TASK: (1) psql query: clients count, active subs, total leads, new leads (last 7d), total calls (last 7d), active campaigns. (2) Write to /opt/leadgen/data/funnel_snapshot_20260914.json. (3) Update command_center/data/bots.json + pinned.json. Evidence: JSON file path + row counts.',
        'status': '🆕 NEW',
        'owner': 'board',
        'priority': 'P2',
        'deadline': '2026-09-15T12:00:00+05:30',
        'assigned_at': ts,
        'updated_at': ts,
        'acceptance': '',
        'evidence': ts_short + ' IST: BRD-141 stale. Reassigned.'
    },
]

tasks.extend(new_tasks)

with open(tasks_path, 'w', encoding='utf-8') as f:
    json.dump(tasks, f, ensure_ascii=False, indent=2)
    f.write('\n')
print(f'TASKS: {len(tasks)} total ({len(new_tasks)} new) @ {ts}')

# ---------- BOTS.JSON ----------
bots_path = os.path.join(base, 'bots.json')
with open(bots_path, encoding='utf-8') as f:
    bots = json.load(f)

bots[0]['status'] = ts_short + ' IST REV-COMMAND: loop DEAD 14d; LLM 0/9; Vobiz TCP-000; DB leads=1; Jiya 0 reply 36h. 7 new tasks assigned.'
bots[0]['current_task'] = 'REV-COMMAND ' + ts_short
bots[0]['updated_at'] = ts

bots[1]['status'] = '🆕 SUC-146 STANDBY. Jiya retention DAYTIME-GATED. SAL-146 handling WA follow-up.'
bots[1]['current_task'] = 'SUC-146'
bots[1]['updated_at'] = ts

bots[2]['status'] = '🆕 SAL-146 P0: Jiya 2nd WA retention msg (36h no reply). WAHA :3002/api/sendText. Deadline 09:00 IST.'
bots[2]['current_task'] = 'SAL-146'
bots[2]['updated_at'] = ts

bots[3]['status'] = '🆕 HNT-146 P0: DB pool EXHAUSTED (1 uncontacted). Google Maps 50 B2B leads. Deadline 12:00 IST.'
bots[3]['current_task'] = 'HNT-146'
bots[3]['updated_at'] = ts

bots[4]['status'] = '🆕 GRD-146 P1: LLM chain audit (9 providers + new). Deadline 18:00 IST.'
bots[4]['current_task'] = 'GRD-146'
bots[4]['updated_at'] = ts

bots[5]['status'] = '🆕 ENG-146 P0: LLM chain fix — test new free providers OR rule-based fallback. Deadline 18:00 IST.'
bots[5]['current_task'] = 'ENG-146'
bots[5]['updated_at'] = ts

bots[6]['status'] = '🆕 PLT-146 P0: Vobiz egress root cause (DNS+iptables) OR Jio SIP fallback. Deadline 12:00 IST.'
bots[6]['current_task'] = 'PLT-146'
bots[6]['updated_at'] = ts

bots[7]['status'] = '🆕 OPS-146 P1: Loop venv path fix + prep for LLM+DID restart. Deadline 18:00 IST.'
bots[7]['current_task'] = 'OPS-146'
bots[7]['updated_at'] = ts

bots[8]['status'] = '🆕 BRD-146 P2: Funnel snapshot + state.js refresh. Deadline 12:00 IST.'
bots[8]['current_task'] = 'BRD-146'
bots[8]['updated_at'] = ts

with open(bots_path, 'w', encoding='utf-8') as f:
    json.dump(bots, f, ensure_ascii=False, indent=2)
    f.write('\n')
print(f'BOTS: {len(bots)} refreshed @ {ts}')

# ---------- PINNED.JSON ----------
pinned_path = os.path.join(base, 'pinned.json')
with open(pinned_path, encoding='utf-8') as f:
    pinned = json.load(f)

pinned['last_updated'] = ts
pinned['text'] = (
    'PILOT ' + ts_short + ' IST IS-RUN sweep: VPS healthy (95245ce8, uptime 2h04m). '
    'ALL containers Up. DB: 23,907 total leads, 1 uncontacted mobile (pool EXHAUSTED). '
    'Loop DEAD 14d (proc 0, crontab 0). LLM chain 0/9 (14d). Vobiz egress TCP-000 (14d). '
    'Jiya retention: WA sent 08:32 IST yesterday, 0 replies in 36h. '
    'Revenue path = WA follow-up (SAL-146) + lead refresh (HNT-146) ONLY.'
)
pinned['priority_tasks'] = [
    'SAL-146 (Jiya 2nd WA retention — P0 — 09:00 IST)',
    'HNT-146 (Lead pool refresh — P0 — 12:00 IST)',
    'PLT-146 (Vobiz egress root cause — P0 — 12:00 IST)',
    'ENG-146 (LLM chain fix — P0 — 18:00 IST)',
    'OPS-146 (Loop venv path — P1 — 18:00 IST)',
    'GRD-146 (LLM audit — P1 — 18:00 IST)',
    'BRD-146 (Funnel snapshot — P2 — 12:00 IST)',
]
pinned['bottleneck'] = (
    '#1 LLM chain 0/9 (14d) → voice agent mute → no close | '
    '#2 Vobiz egress TCP-000 (14d) → no outbound calls | '
    '#3 DB lead pool EXHAUSTED (1 uncontacted) → no new prospects | '
    '#4 Jiya 0 reply 36h → sole payer churn-risk'
)
pinned['action'] = (
    ts_short + ': SAL-146 WA follow-up → HNT-146 Google Maps refresh → '
    'PLT-146 DNS+iptables root cause → ENG-146 new free LLM test → '
    'OPS-146 venv path fix → GRD-146 audit → BRD-146 funnel snapshot'
)
pinned['next_expected_payment'] = (
    'SAL-146 Jiya 2nd WA reply → UPI ₹899 (low prob, 36h silence) | '
    'HNT-146 new leads → future close (not today)'
)
pinned['vps_status'] = (
    'VPS UP /health 200 prod 95245ce8 (uptime 2h04m); '
    'ALL containers Up; '
    'call_loop DEAD 14d (proc 0, crontab 0, venv path broken); '
    'LLM chain 0/9 (14d); '
    'Vobiz egress TCP-000 (14d); '
    'DB: 23,907 leads, 1 uncontacted mobile (pool EXHAUSTED); '
    'Jiya retention: WA sent 08:32 IST yesterday, 0 replies 36h; '
    'WAHA :3002 session=default WORKING'
)
pinned['verified_collected'] = 1999
pinned['gap'] = 498001
pinned['pipeline_value'] = 0
pinned['hot_opportunities'] = [
    'SAL-146 Jiya 2nd WA retention ₹899 (36h no reply — low prob)',
    'HNT-146 Google Maps 50 B2B leads (pool exhausted — critical)',
    'ENG-146 LLM chain fix (unblocks voice closes — 14d blocker)',
]
pinned['evidence_as_of'] = ts

with open(pinned_path, 'w', encoding='utf-8') as f:
    json.dump(pinned, f, ensure_ascii=False, indent=2)
    f.write('\n')
print(f'PINNED: refreshed @ {ts}')

# ---------- MESSAGES.JSONL ----------
ledger_path = os.path.join(base, 'messages.jsonl')
lines = [
    {'ts': ts, 'from': 'PILOT', 'to': 'ALL', 'task_id': 'REV-COMMAND-0914-2032', 'type': 'REVENUE_COMMAND', 'priority': 'P0',
     'msg': '🎯 REVENUE COMMAND ' + ts_short + ' IST (Sep 14): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV-0001) | GAP ₹4,98,001 | PIPELINE: ₹0 (Jiya 36h no reply, DB pool exhausted) | HOT: SAL-146 Jiya 2nd WA (low prob) + HNT-146 lead refresh (critical) | BOTTLENECK: LLM 0/9 (14d) → Vobiz TCP-000 (14d) → DB leads=1 (14d) → Jiya silent 36h | ACTION: 7 new tasks assigned (SAL/HNT/PLT/ENG/GRD/OPS/BRD-146) | NEXT: SAL-146 WA 09:00 IST → HNT-146 CSV 12:00 → PLT-146 DNS root cause 12:00 → ENG-146 LLM fix 18:00 → OPS-146 venv fix 18:00 → GRD-146 audit 18:00 → BRD-146 snapshot 12:00'},
    {'ts': ts, 'from': 'PILOT', 'to': 'sales', 'task_id': 'SAL-146', 'type': 'ASSIGN', 'priority': 'P0',
     'msg': '@sales SAL-146 P0 HARD 12h (deadline 09:00 IST Sep 15): Jiya = sole payer ₹1,999, 36h no reply to retention WA. TASK: (1) Send 2nd WA retention msg via WAHA :3002/api/sendText — "Hi Jiya, final reminder: 30-day free pause OR 40% off (₹899/mo) — reply YES to activate. Offer expires tonight." (2) If no reply by 09:00 IST Sep 15, mark CHURNED in DB. Evidence: WA msg ID + screenshot OR DB churn flag. ACK SAL-146 NOW.'},
    {'ts': ts, 'from': 'PILOT', 'to': 'hunter', 'task_id': 'HNT-146', 'type': 'ASSIGN', 'priority': 'P0',
     'msg': '@hunter HNT-146 P0 HARD 16h (deadline 12:00 IST Sep 15): DB lead pool EXHAUSTED — only 1 uncontacted mobile lead (was 10,587). TASK: (1) Google Maps scrape: 50 B2B leads (niche=makeover/beauty salon, city=Pune+Mumbai, min_rating=4.0, has_website=true). (2) DND-scrub against NDNC. (3) Write to /opt/leadgen/data/qualified_leads_20260915.csv. (4) INSERT into DB leads table (status=new, source=gmaps_20260915). Evidence: CSV path + row count + DB INSERT count. ACK HNT-146 NOW.'},
    {'ts': ts, 'from': 'PILOT', 'to': 'platform', 'task_id': 'PLT-146', 'type': 'ASSIGN', 'priority': 'P0',
     'msg': '@platform PLT-146 P0 HARD 16h (deadline 12:00 IST Sep 15): Vobiz egress UNREACHABLE (HTTP 000, TCP block, 14+ days). TASK: (1) DNS test: nslookup api.vobiz.in from VPS. (2) curl -v --max-time 10 https://api.vobiz.in/Call/ — capture full output. (3) If egress blocked: iptables -L -n, check Caddy reverse_proxy. (4) If unfixable: CALL RMS Tech Rajnikant 080-47652298 — ask for 10ch DID (₹499/mo) — record proof. Evidence: DNS+curl verbose + root-cause verdict OR Jio/RMS DID proof. ACK PLT-146 NOW.'},
    {'ts': ts, 'from': 'PILOT', 'to': 'engineering', 'task_id': 'ENG-146', 'type': 'ASSIGN', 'priority': 'P0',
     'msg': '@engineering ENG-146 P0 HARD 22h (deadline 18:00 IST Sep 15): LLM chain 0/9 (14d). ALL free providers failed (Groq TPD, Mistral 429, Gemini 20/day, Cerebras pay, SambaNova pay, NVIDIA dead, Ollama conn, OpenRouter paid). TASK: (1) Test ANY new free LLM API (Together AI, Fireworks, Deepinfra, HuggingFace) with simple curl. (2) If found: add to /opt/leadgen/.env + free_ai.py chat() chain. (3) If none: implement rule-based fallback script (no LLM) — pre-recorded voice prompts for common scenarios. Evidence: Working provider test proof OR fallback script commit sha. ACK ENG-146 NOW.'},
    {'ts': ts, 'from': 'PILOT', 'to': 'operations', 'task_id': 'OPS-146', 'type': 'ASSIGN', 'priority': 'P1',
     'msg': '@operations OPS-146 P1 HARD 22h (deadline 18:00 IST Sep 15): Loop venv path STILL broken (/opt/leadgen/venv/bin/python missing). Loop DOWN 14d. TASK: (1) Fix crontab to use /usr/bin/python3 or /app/.venv/bin/python3. (2) Verify DATABASE_URL exports correctly at loop start. (3) Add circuit-breaker: if DID not owned → stop + alert. (4) Prep for LLM+DID fix restart. Evidence: crontab entry + venv path proof + circuit-breaker script. ACK OPS-146 NOW.'},
    {'ts': ts, 'from': 'PILOT', 'to': 'guardian', 'task_id': 'GRD-146', 'type': 'ASSIGN', 'priority': 'P1',
     'msg': '@guardian GRD-146 P1 HARD 22h (deadline 18:00 IST Sep 15): LLM chain audit STILL PENDING. TASK: (1) Test all 9 free providers from VPS with curl. (2) Check if any new free provider works. (3) Verify ENG-146 fallback script if LLM still 0/9. (4) Output llm_chain_status.json to command_center/data/. Evidence: Provider test results + PASS/FAIL verdict. ACK GRD-146 NOW.'},
    {'ts': ts, 'from': 'PILOT', 'to': 'board', 'task_id': 'BRD-146', 'type': 'ASSIGN', 'priority': 'P2',
     'msg': '@board BRD-146 P2 HARD 16h (deadline 12:00 IST Sep 15): Funnel snapshot STALE. TASK: (1) psql query: clients count, active subs, total leads, new leads (last 7d), total calls (last 7d), active campaigns. (2) Write to /opt/leadgen/data/funnel_snapshot_20260914.json. (3) Update command_center/data/bots.json + pinned.json. (4) Push to VPS /opt/leadgen/command_center/data/. Evidence: JSON file path + row counts + VPS md5 match. ACK BRD-146 NOW.'},
]

with open(ledger_path, 'a', encoding='utf-8') as f:
    for ln in lines:
        f.write(json.dumps(ln, ensure_ascii=False) + '\n')
print(f'LEDGER: {len(lines)} lines appended @ {ts}')
