#!/usr/bin/env python3
"""Owner Command Center builder: data/*.json(l) -> state.js (loaded by index.html).
Validates: no active task without owner, ASSIGNED tasks must have assigned_at (ACK watchdog),
every message has ts+from. Exit!=0 on violation."""
import json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")

def load(name, default):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return default
    if name.endswith(".jsonl"):
        out = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
    with open(p, encoding="utf-8") as f:
        return json.load(f)

msgs = load("messages.jsonl", [])
tasks = load("tasks.json", [])
bots = load("bots.json", {})

errors = []
for i, m in enumerate(msgs):
    if not m.get("ts") or not m.get("from"):
        errors.append(f"message[{i}] missing ts/from")
for t in tasks:
    tid = t.get("id", "?")
    if t.get("status") in ("ASSIGNED", "RUNNING", "BLOCKED") and not t.get("owner"):
        errors.append(f"{tid}: active task has no owner")
    if t.get("status") == "ASSIGNED" and not t.get("assigned_at"):
        errors.append(f"{tid}: ASSIGNED without assigned_at (ACK watchdog blind)")
if errors:
    print("VALIDATION FAILED:")
    for e in errors:
        print(" -", e)
    sys.exit(1)

counts = {"working": 0, "idle": 0, "blocked": 0}
for b in bots.values():
    s = str(b.get("status", "")).upper()
    if "BLOCKED" in s:
        counts["blocked"] += 1
    elif any(k in s for k in ("REV-", "WORKING", "COORDINATING")):
        counts["working"] += 1
    else:
        counts["idle"] += 1

state = {
    "group": "OWNER COMMAND CENTER",
    "subtitle": f"Pilot + 8 bots \u00b7 {counts['working']} working \u00b7 {counts['idle']} idle \u00b7 {counts['blocked']} blocked",
    "counts": counts,
    "bots": bots,
    "tasks": sorted(tasks, key=lambda t: t.get("id", "")),
    "messages": sorted(msgs, key=lambda m: m.get("ts", "")),
    "pinned": load("pinned.json", {}),
}

out = os.path.join(BASE, "state.js")
with open(out, "w", encoding="utf-8") as f:
    f.write("window.CC_STATE = ")
    json.dump(state, f, ensure_ascii=False)
    f.write(";")

print(f"BUILD OK: {len(msgs)} messages, {len(tasks)} tasks, {len(bots)} bots "
      f"({counts['working']} working / {counts['idle']} idle / {counts['blocked']} blocked)")
