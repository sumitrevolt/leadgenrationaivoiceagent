"""Idempotent .env key setter (VPS). Backs up to .env.bak, sets ONLY the listed
safe keys (no secrets in this file), reports user-action keys. Run: python scripts/env_set.py"""
import os
import shutil

ENV = "/opt/leadgen/.env" if os.path.exists("/opt/leadgen/.env") else ".env"

# Safe, non-secret keys to set (P1 revenue + P3 dormant flags). No credentials here.
SET = {
    "NOTIFY_EMAIL": "admin@leadsgenai.in",   # P1: inquiry/ops alerts ON
    "AUTO_EMAIL_OUTREACH": "true",            # P1: Rohan daily cold emails (cap 25/day)
    "USE_AGENTIC_RAG": "1",                   # P3: CRAG self-correct retrieval (defensive)
    "USE_LANGGRAPH_SUPERVISOR": "1",          # P3: semantic multi-agent (Cerebras/Groq)
}
# These need the USER's real value (can't fabricate) — report only.
REPORT_ONLY = ["UPI_VPA", "POLLINATIONS_TOKEN"]

lines = []
if os.path.exists(ENV):
    shutil.copy(ENV, ENV + ".bak")
    lines = open(ENV, encoding="utf-8").read().splitlines()

seen = set()
out = []
for ln in lines:
    s = ln.strip()
    if s and not s.startswith("#") and "=" in s and s.split("=", 1)[0].strip() in SET:
        k = s.split("=", 1)[0].strip()
        out.append(f"{k}={SET[k]}")
        seen.add(k)
    else:
        out.append(ln)
for k, v in SET.items():
    if k not in seen:
        out.append(f"{k}={v}")

with open(ENV, "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")

cur = {}
for ln in open(ENV, encoding="utf-8"):
    if "=" in ln and not ln.strip().startswith("#"):
        cur[ln.split("=", 1)[0].strip()] = ln.split("=", 1)[1].strip()

print("=== SET (P1+P3) ===")
for k in SET:
    print(f"  {k}={cur.get(k)}")
print("=== NEEDS USER VALUE (left unset — can't fabricate) ===")
for k in REPORT_ONLY:
    print(f"  {k}: {'SET' if cur.get(k) else 'NOT SET (give me the value)'}")
