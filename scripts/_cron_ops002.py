import json

p = "command_center/data/tasks.json"
d = json.load(open(p))
if not any(t["id"] == "OPS-002" for t in d):
    d.append({
        "id": "OPS-002",
        "objective": "Fix leadgen_temporal crash-loop (missing dynamicconfig development-sql.yaml) + restart OOM-killed leadgen_app",
        "requested_by": "PILOT",
        "assigned_by": "PILOT",
        "owner": "platform",
        "supporting": ["operations"],
        "priority": "P0",
        "status": "VERIFIED",
        "started": "2026-08-26T11:15:00+05:30",
        "last_update": "2026-08-26T11:22:00+05:30 PILOT: VERIFIED - temporal config written, container healthy (Up, logs clean); leadgen_app restarted, /health 200 OK",
        "eta": "done",
        "dependencies": [],
        "blocker": "none",
        "evidence": "docker ps: leadgen_app Up healthy, leadgen_temporal Up healthy; app log shows GET /health 200 OK at 04:07Z before exit 255 (OOM=false); temporal dynamicconfig/development-sql.yaml created on VPS",
        "final_result": ""
    })
json.dump(d, open(p, "w"), indent=2)
print("tasks:", len(d), "| OPS-002 recorded")
