import json
import os
from collections import Counter, defaultdict

# LLM ok-rates (last 500 calls)
rows = (
    open("data/llm_calls.jsonl").readlines()[-500:]
    if os.path.exists("data/llm_calls.jsonl")
    else []
)
s = defaultdict(lambda: [0, 0])
for r in rows:
    try:
        d = json.loads(r)
    except Exception:
        continue
    p = d.get("provider") or "unknown"
    s[p][0] += 1
    if d.get("ok"):
        s[p][1] += 1
print("=== LLM OK-RATES (last 500) ===")
for p, v in sorted(s.items()):
    print(f"  {p}: {round(v[1] / max(v[0], 1) * 100)}%  ({v[0]} calls)")

# Prospects
print("\n=== PROSPECTS ===")
pros = [json.loads(l) for l in open("data/prospects.jsonl")]
st = Counter(p.get("status", "unknown") for p in pros)
print(f"  Total: {len(pros)}")
print(f"  Status: {dict(st)}")
print(f"  With email: {sum(1 for p in pros if p.get('email'))}")
print(f"  With phone: {sum(1 for p in pros if p.get('phone'))}")
print(f"  Hot leads (score>=70): {sum(1 for p in pros if (p.get('lead_score') or 0) >= 70)}")

# Cadence
print("\n=== CADENCE ===")
cads = (
    [json.loads(l) for l in open("data/cadence_leads.jsonl")]
    if os.path.exists("data/cadence_leads.jsonl")
    else []
)
cs = Counter(c.get("status", "?") for c in cads)
print(f"  Enrolled: {len(cads)}, Status: {dict(cs)}")

# Deals
print("\n=== DEALS ===")
deals = (
    [json.loads(l) for l in open("data/deals.jsonl")] if os.path.exists("data/deals.jsonl") else []
)
ds = Counter(d.get("stage", "?") for d in deals)
print(f"  Total: {len(deals)}, Stages: {dict(ds)}")

# Reply drafts
print("\n=== REPLY DRAFTS ===")
rds = (
    [json.loads(l) for l in open("data/reply_drafts.jsonl")]
    if os.path.exists("data/reply_drafts.jsonl")
    else []
)
rs = Counter(r.get("intent", "?") for r in rds)
print(f"  Total: {len(rds)}, Intents: {dict(rs)}")

# Harvest
print("\n=== HARVEST RUNS ===")
hrs = (
    [json.loads(l) for l in open("data/harvest_runs.jsonl")]
    if os.path.exists("data/harvest_runs.jsonl")
    else []
)
for h in hrs[-3:]:
    print(
        f"  {h.get('ts', '')[:16]}  scraped={h.get('scraped', 0)}  sources={h.get('sources_used', [])} "
    )

# Env flags
print("\n=== KEY FLAGS (env) ===")
flags = [
    "NICHE_ROTATION",
    "AUTO_EMAIL_OUTREACH",
    "REPLY_AGENT",
    "LEAD_HARVESTER",
    "SALES_ENGINE",
    "CADENCE_ENGINE",
    "SELF_IMPROVE_LOOP",
    "GROWTH_OPTIMIZER",
    "CHANNEL_EXPERIMENTS",
    "SALES_TEAM",
    "BRAVE_API_KEY",
    "OPENROUTER_API_KEY",
    "RAZORPAY_WEBHOOK_SECRET",
    "MISSED_CALL_CALLBACK",
    "WHATSAPP_AUTO_SEND",
    "DLT",
    "JOURNEY_ENGINE",
    "AUTO_QUALIFY_CALLS",
]
for f in flags:
    v = os.environ.get(f)
    print(f"  {f}: {'SET' if v else 'UNSET'}")
