import datetime
import json

p = 'command_center/data/tasks.json'
with open(p, encoding='utf-8') as f:
    tasks = json.load(f)
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).strftime('%Y-%m-%dT%H:%M:%S+05:30')
byid = {t['id']: t for t in tasks}

def upd(tid, status=None, last_update=None, blocker=None, eta=None, evidence=None):
    t = byid.get(tid)
    if t is None:
        print(f'MISSING {tid}')
        return
    if status:
        t['status'] = status
    if last_update:
        t['last_update'] = last_update
    if blocker is not None:
        t['blocker'] = blocker
    if eta:
        t['eta'] = eta
    if evidence:
        t['evidence'] = evidence

# GATE #1 — sales DID provisioning (live evidence)
upd('SAL-001', last_update=f"{now} PILOT: ESC#15 D-0 14:55 — live call_loop: batches 2-6 (14:38-14:52 IST) SAB FAIL '911171366938 not owned', cumulative 343 'not owned' in log, ok=0 hamesha. ENG-002 spin-fix RELEASE ab working (skip=0 fail=3 RELEASED) => DID hi LAST blocker. TRAI window ~4h left. ACC 17:30 IST: purchased/activated DID proof (Vobiz Numbers items>0 YA Jio/RMS) + .env real number + 1 dial attempt with NOT-owner-free error.")

# success — STALE >31h, redispatch
upd('SUC-001', status='RUNNING', last_update=f"{now} PILOT: RE-DISPATCH ESC#11 — 31h stale (last update 08-29 07:50, koi evidence nahi). Jiya recovery email ABHI bhejo — DID-INDEPENDENT, ₹1,999 only verified revenue at stake. ACC: sent-email proof (log/screenshot) + response EOD 19:00. No more standby/queued state.")

# engineering — continue canonicalize
upd('ENG-002', last_update=f"{now} PILOT: D-0 14:55 — spin-fix hotfix LIVE verified (RELEASED x12 in log). NEXT (this run): (1) canonicalize repo scripts/fire_calls.py sync VPS copy, (2) provider-failover runbook (.env VOBIZ_CALLER_ID swap <10min) for Jio/RMS fallback. ACC: commit sha + runbook file path + container restart proof.")

# guardian — nudge Jiya re-review (DID-independent)
upd('GRD-002', last_update=f"{now} PILOT: NUDGE — (a) Jiya account-health re-review ABHI karo (DID-independent, SUC-001 email confirm), (b) ENG-002 spin-fix gate verdict: ok>0 vs 'not owned' error split (log evidence), (c) DID land hote hi final PASS. ACC: verdict + evidence.")

# hunter — confirm LI-005 deadline
upd('HNT-003', last_update=f"{now} PILOT: LOCK — LI-005 50 MOBILE DND-scrubbed leads deadline 16:00 (1h5m left). 17,596 MOBILE ready-pool h, LI-004 missed tha — is baar CSV + DND-proof column + count evidence chahiye. ACC: CSV file + count + DND column.")

# platform — confirm PLT-003
upd('PLT-003', last_update=f"{now} PILOT: LOCK — 15:00 pehla hourly telephony verify. Note: VPS->api.vobiz.com ConnectTimeout 14:10 tha; call_loop 14:45-52 'not owned' fail. File /opt/leadgen/data/plt003_hourly.md. ACC: 15:00 entry.")

# operations — hourly digest
upd('OPS-005', last_update=f"{now} PILOT: D-0 14:55 digest — batches 2-6 loops fresh (skip=0), fail='not owned' x3/batch, totals ok=0, 560 batches cum, 343 not-owned errors, 0 USER_BUSY, 0 connect. DID land hote hi ok>0 expect. Hourly digest jari rakho; owner brief calls/connects/convert.")

# board — mirror refresh (bots.json stale 08-29)
upd('BRD-001', last_update=f"{now} PILOT: NUDGE — mirror refresh AAJ D-0 statuses: PLT-003 15:00 verify, HNT-003 16:00 LI-005, ENG-002 spin-fix LIVE, SAL-001 ESC#15 17:30 DID ACC, SUC-001 redispatch, GRD-002 Jiya re-review. bots.json abhi 08-29 stale h. ACC: 3 JSON updated + valid.")

# hourly revenue command record (history)
tasks.append({
    "id": "PILOT-REVCMD-08-30-14",
    "objective": "Hourly REVENUE COMMAND 14:55 IST — D-0: DID gate #1 (SAL-001) 17:30 ACC; TRAI ~4h; call infra READY (spin-fix live, 18,076 MOBILE leads, loop firing fresh batches)",
    "requested_by": "PILOT",
    "assigned_by": "PILOT",
    "owner": "pilot",
    "supporting": [],
    "priority": "P0",
    "status": "ACK",
    "started": now,
    "assigned_at": now,
    "last_update": f"{now} PILOT: REVENUE COMMAND (08-30 14:55) — Target ₹5,00,000 | Verified ₹1,999 (Jiya INV/2026-27/0001) | Gap ₹4,98,001 | Pace ₹71,429/d | Pipeline ₹0 (calling pre-DID) | Hot: Jiya (only payer, RED) + 18,076 MOBILE leads dialer-ready | Bottleneck: Vobiz caller-ID ownership — account owns ZERO numbers (SAL-001, GATE#1, ACC 17:30) | Action: DID purchase confirm (Vobiz/Jio/RMS) → .env swap <10min (ENG-002 runbook) → first ok>0 batch (OPS-005) → interested → UPI close (REV-105); Jiya email NOW (SUC-001); LI-005 16:00 (HNT-003); Jiya re-review (GRD-002); hourly telephony (PLT-003 15:00). Buzz MCP dead (relay restricted) — dispatch ledger-only.",
    "eta": "DONE",
    "dependencies": ["SAL-001"],
    "blocker": "none — SAL-001 in flight",
    "evidence": "VPS ext /health 63c2c47a 200; buzz :3110 ok; call_loop 560 batches 343 not-owned 0 connect"
})

with open(p, 'w', encoding='utf-8') as f:
    json.dump(tasks, f, ensure_ascii=False, indent=2)
print('ledger updated at', now)
for tid in ['SAL-001','SUC-001','ENG-002','GRD-002','HNT-003','PLT-003','OPS-005','BRD-001']:
    t = byid.get(tid)
    print(tid, t['status'], t['last_update'][:60])
print('tasks count:', len(tasks))
