import datetime
import json

p = 'command_center/data/tasks.json'
tasks = json.load(open(p, encoding='utf-8'))
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).strftime('%Y-%m-%dT%H:%M:%S+05:30')
byid = {t['id']: t for t in tasks}

# #1 REVENUE GATE — DID/caller-ID ownership. Today 12:00 IST deadline already set (escalation #7).
s = byid.get('SAL-001')
if s:
    s['last_update'] = f"{now} PILOT: RUN TICK (08-29 07:26 IST cron) — VPS healthy, call_loop TRAI-window sleeping till 10:00, regex fix LIVE (18,076 MOBILE leads). YEHI #1 GATE: caller-ID '911171366938 not owned' must clear by 12:00 IST (TRAI 10:00 open, launch-ready). ACC unchanged: Numbers API 200 + owned from-number OR DID activation proof. Escalation #7 active."

# Launch-run owner: ensure OPS-005 armed before 10:00.
o = byid.get('OPS-005')
if o:
    o['last_update'] = f"{now} PILOT: RUN TICK — 07:26 IST verified VPS healthy, loop sleeping (TRAI window 10:00-19:00). 10:00 se pehle loop healthy check karo, phir hourly metrics digest. DID land hote hi launch-ready. ACC: hourly call_loop count + 1 verified connect."

# Board mirror: snapshot current truth.
b = byid.get('BRD-001')
if b:
    b['last_update'] = f"{now} PILOT: REVENUE COMMAND (08-29 07:26) — Target \u20b95,00,000 | Verified \u20b90 | Gap \u20b95,00,000 | Pipeline 0 (calling pre-DID) | Hot: Jiya (only paying cus, P0 retention) | Bottleneck: Vobiz caller-ID ownership (SAL-001) | Action: DID gate 12:00 IST / Jiya email (SUC-001) | Launch 10:00. Mirror refresh karo."

json.dump(tasks, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print("recorded run tick at", now)
print("SAL-001:", byid['SAL-001']['status'], byid['SAL-001']['priority'])
print("OPS-005:", byid['OPS-005']['status'])
print("SUC-001:", byid['SUC-001']['status'])
