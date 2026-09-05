"""Owner OS hot-queue analyzer — runs on prod via SSH-copied file."""
import json, sys
from collections import Counter

d = json.load(open("/tmp/hq_all.json"))
items = d.get("items", [])
print(f"scope={d.get('scope')} count={len(items)} summary={json.dumps(d.get('summary',{}))}")
print()
ch = Counter(i.get("channel", "?") for i in items)
intent = Counter(i.get("intent", "?") for i in items)
niche = Counter(i.get("niche", "?") for i in items)
city = Counter(i.get("city", "?") for i in items)
print("CHANNELS:", dict(ch.most_common(8)))
print("INTENTS :", dict(intent.most_common(8)))
print("NICHES  :", dict(niche.most_common(8)))
print("CITIES  :", dict(city.most_common(8)))
print()
with_phone = [i for i in items if i.get("phone") and ("+" in str(i.get("phone","")) or str(i.get("phone","")).startswith("91"))]
print(f"with_phone: {len(with_phone)}")
print()
print("=== TOP 25 WITH PHONE (call-first) ===")
for i in [x for x in items if x.get("phone") and "****" not in str(x.get("phone",""))][:25]:
    print(f"  {i.get('business_name','?')[:35]:35s} | {i.get('from','?')[:30]:30s} | {str(i.get('phone','')):14s} | {i.get('niche','?')[:18]:18s} | {i.get('city','?')[:14]:14s} | {i.get('channel','?')}")
print()
print("=== WA LINKS READY (top 10) ===")
for i in [x for x in items if x.get("wa_link")][:10]:
    print(f"  {i.get('business_name','?')[:30]:30s} | WA={i.get('wa_link','')[:90]}")
print()
# Estimated revenue at 1999 starter / 5999 advanced conversion
potential_low = len(with_phone) * 1999
potential_mid = len(items) * 1999
print(f"POTENTIAL REVENUE (if all {len(with_phone)} call-phoned → starter ₹1999): ₹{potential_low:,}")
print(f"POTENTIAL REVENUE (if all 42 convert starter): ₹{potential_mid:,}")
print(f"NEEDED FOR 5L: ₹{(500000 - 5997):,} — {((500000-5997)//1999)+1} starter sales")
