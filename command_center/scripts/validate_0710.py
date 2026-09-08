import json, sys

for f in ["tasks.json", "bots.json", "pinned.json"]:
    p = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data/" + f
    d = json.load(open(p, encoding="utf-8"))
    print(f, "VALID", type(d).__name__, len(d))
print("OK")