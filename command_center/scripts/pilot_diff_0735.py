import json, sys

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"

# tasks diff: print id|status|owner|prio|deadline|evidence_tail head for both sides
lt = json.load(open(BASE + "/tasks.json", encoding="utf-8"))
vt = json.load(open(BASE + "/tasks.json.vps", encoding="utf-8"))
lmap = {t["id"]: t for t in lt}
vmap = {t["id"]: t for t in vt}
print("=== TASK IDS local:", list(lmap.keys()))
print("=== TASK IDS vps:", list(vmap.keys()))
for tid in sorted(set(lmap) | set(vmap)):
    l = lmap.get(tid)
    v = vmap.get(tid)
    ls = (l or {}).get("status")
    vs = (v or {}).get("status")
    if ls != vs:
        print("STATUS DIFF", tid, "local", ls, "vps", vs)
print("=== BOTS local keys:", list(lt[0].keys()) if lt else "-")

# bots diff
lb = json.load(open(BASE + "/bots.json", encoding="utf-8"))
vb = json.load(open(BASE + "/bots.json.vps", encoding="utf-8"))
for k in lb:
    s1 = lb[k].get("status", "")[:80]
    s2 = vb.get(k, {}).get("status", "")[:80]
    if s1 != s2:
        print("BOT DIFF", k)
        print("  local:", s1)
        print("  vps  :", s2)

# pinned diff
lp = json.load(open(BASE + "/pinned.json", encoding="utf-8"))
vp = json.load(open(BASE + "/pinned.json.vps", encoding="utf-8"))
for k in lp:
    if lp.get(k) != vp.get(k):
        print("PIN DIFF", k, "| local:", str(lp.get(k))[:80], "| vps:", str(vp.get(k))[:80])