import json, sys

# Compare local command_center data vs VPS mirror copies (downloaded as .vps)
BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
for name in ["tasks", "bots", "pinned"]:
    lp = BASE + "/" + name + ".json"
    vp = BASE + "/" + name + ".json.vps"
    l = json.load(open(lp, encoding="utf-8"))
    v = json.load(open(vp, encoding="utf-8"))
    print(name, "SAME" if l == v else "DIFF")
# message ledger line counts
ll = sum(1 for _ in open(BASE + "/messages.jsonl", encoding="utf-8"))
vl = sum(1 for _ in open(BASE + "/messages.jsonl.vps", encoding="utf-8"))
print("messages local", ll, "vps", vl)