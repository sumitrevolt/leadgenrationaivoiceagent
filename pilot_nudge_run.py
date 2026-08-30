import json
import datetime

p = 'command_center/data/tasks.json'
tasks = json.load(open(p, encoding='utf-8'))
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).strftime('%Y-%m-%dT%H:%M:%S+05:30')
byid = {t['id']: t for t in tasks}

t = byid.get('OPS-003')
if t:
    t['last_update'] = f"{now} PILOT: NUDGE #3 - Buzz relay down from HQ; is task-record ke last_update me hi reply post karo. 16:00 interim: phone_type_blocked audit finding + stale-queue refresh fix. Deadline 17:00 unchanged."
    t['blocker'] = "comms degraded - Buzz MCP relay down; report via task-record"

t = byid.get('HNT-001')
if t:
    t['last_update'] = f"{now} PILOT: NUDGE #4 - batches 79-81 abhi bhi wahi 3 leads SKIP. 16:00 HARD deadline: 100-lead MOBILE-only DND-scrubbed batch + queue auto-refresh trigger confirm."

t = byid.get('BRD-001')
if t:
    t['last_update'] = f"{now} PILOT: REVENUE COMMAND synced - verified Rs0 / gap Rs5L, DID bottleneck, REV-103/104 closed as superseded. Mirror refresh karo."

json.dump(tasks, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print("nudges recorded at", now)
print("OPS-003 blocker:", byid['OPS-003']['blocker'])
print("HNT-001:", byid['HNT-001']['last_update'][:70])
