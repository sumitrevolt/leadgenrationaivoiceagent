import ast, re, os, io

REPO = "/sessions/intelligent-festive-fermi/mnt/leadgenrationaiagent"
src = open(f"{REPO}/app/platform/team.py", encoding="utf-8").read()
tree = ast.parse(src)
staff = None
for node in ast.walk(tree):
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "STAFF":
        staff = ast.literal_eval(node.value)
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "STAFF":
                staff = ast.literal_eval(node.value)
assert staff, "STAFF not found"

BASE = ["global/config", "global/logging", "global/feature-flags"]
PROD = {
    "voice": ["voice/hot-path", "voice/free-provider-chain", "voice/circuit-breaker", "voice/compliance-gate", "voice/reply-mirror"],
    "marketing": ["backend/error-handling", "backend/lazy-imports"],
    "platform": ["backend/api-routers", "backend/auth", "backend/error-handling", "backend/lazy-imports", "backend/pydantic-models"],
}
EXTRA = {
    "nikhil": ["billing/billing-truth"], "vidya": ["billing/billing-truth"],
    "lekha": ["frontend/admin-actions"], "kavya": ["frontend/admin-actions"],
    "hermes": ["frontend/admin-actions"], "vikram": ["frontend/admin-actions"],
    "arya": ["frontend/admin-actions"],
}

outdir = f"{REPO}/agent-os/agents"
os.makedirs(outdir, exist_ok=True)

def gates(text):
    return sorted(set(re.findall(r"gated ([A-Z_]+)", text)))

def kpis(text):
    m = re.findall(r"KPIs?:\s*([a-z_0-9, ]+)", text)
    out = []
    for grp in m:
        out += [k.strip() for k in grp.split(",") if k.strip()]
    return out

index_lines = ["# Agent OS — VPS AI Staff Index (generated from app/platform/team.py — code = truth)", ""]
for key, a in staff.items():
    stds = BASE + PROD.get(a["product"], []) + EXTRA.get(key, [])
    g = gates(a["duties"] + " " + a["schedule"])
    k = kpis(a["duties"])
    lines = [
        f"# {a['emoji']} {a['name']} — {a['title']}",
        "",
        f"> Source of truth: `app/platform/team.py` STAFF[\"{key}\"]. Yeh spec code se DERIVED hai — code badle to `python scripts/gen_agent_os_specs.py` re-run karo. Code vs spec conflict = code wins.",
        "",
        f"- **Key:** `{key}`",
        f"- **Product:** {a['product']}",
        f"- **Schedule:** {a['schedule']}",
    ]
    if g:
        lines.append(f"- **Feature gates:** {', '.join('`'+x+'`' for x in g)} (env-flag, INERT default)")
    if k:
        lines.append(f"- **KPIs:** {', '.join('`'+x+'`' for x in k)}")
    lines += [
        "",
        "## Duties",
        "",
        a["duties"],
        "",
        "## Relevant standards (load via /inject-standards)",
        "",
    ]
    lines += [f"- `agent-os/standards/{s}.md`" for s in stds]
    lines += [
        "",
        "## Non-negotiables (CLAUDE.md §5)",
        "",
        "- Compliance gates (DND fail-closed, AI-disclosure, 9am-7pm window, consent ledger) KABHI disable nahi.",
        "- Customer data cross-client leak nahi; secrets sirf `.env`.",
        "- Free AI stack only; external call KABHI route/agent crash nahi karta (graceful degradation).",
        "- `log_event()` se har kaam attribute karo — invisible automation nahi.",
        "",
    ]
    open(f"{outdir}/{key}.md", "w", encoding="utf-8").write("\n".join(lines))
    index_lines.append(f"- **{a['name']}** (`{key}`) — {a['title']} · {a['product']} · {a['schedule']}")

open(f"{outdir}/INDEX.md", "w", encoding="utf-8").write("\n".join(index_lines) + "\n")

TEMPLATE = """# 🆕 NEW AGENT TEMPLATE — naya AI staff agent add karne ka SOP

> Council rule (2026-06-25 billionaire-audit): naya agent SIRF tab jab wo *measurable operational leverage* de jo current roster nahi deta. Pehle folding/reuse consider karo (Hermes ne Kavya/Tara ke engines REUSE kiye the).

## Checklist (sab mandatory)

1. **Roster entry:** `app/platform/team.py` STAFF me key add karo — `product` (voice/marketing/platform), `name`, `emoji`, `title`, `duties` (KPI naam ke saath), `schedule`.
2. **Feature gate:** naya env flag (e.g. `MY_AGENT=1`), INERT default, `AUTOMATION_FLAGS` registry me register.
3. **Engine module:** `app/agents/<name>.py` — padosi copy karo (lazy `from app.voice_agent import free_ai` FUNCTION ke andar, module-top pe nahi; try/except + graceful degradation; `log_event()` attribution).
4. **Scheduler wiring:** `team_scheduler.py` me job (boot-grace respect karo) — heavy kaam Celery only, web process me nahi.
5. **Spec regenerate:** `python scripts/gen_agent_os_specs.py` — agent-os/agents/<key>.md auto-banega.
6. **Test + verify:** targeted pytest + `prod_check.py` + duplicate-route grep. Evidence ke bina done nahi.
7. **Memory write-back:** `memory/decisions.md` me ADR + CLAUDE.md `## Current State`.

## Standards jo HAR agent pe lagte hai

- `agent-os/standards/global/config.md` · `global/logging.md` · `global/feature-flags.md`
- Product-specific: voice → `voice/*`; marketing → `backend/error-handling`, `backend/lazy-imports`; platform → `backend/*`
- Billing touch → `billing/billing-truth.md` (packages.py = single source)

## OmniRoute (optional, double-gated)

Agent LLM calls default free_ai chain use karte hai. OmniRoute route tabhi jab `OMNIROUTE_ENABLED=1` **aur** `OMNIROUTE_AGENTS=1` — sanitized payload only, free_ai fallback hamesha intact.
"""
open(f"{outdir}/NEW_AGENT_TEMPLATE.md", "w", encoding="utf-8").write(TEMPLATE)

# standards/index.yml populate
std_dir = f"{REPO}/agent-os/standards"
entries = []
for root, _, files in os.walk(std_dir):
    for f in sorted(files):
        if f.endswith(".md"):
            rel = os.path.relpath(os.path.join(root, f), std_dir).replace("\\", "/")
            title = open(os.path.join(root, f), encoding="utf-8").readline().strip("# \n")
            entries.append((rel, title))
entries.sort()
yml = ["# Agent OS Standards Index", "# Generated by scripts/gen_agent_os_specs.py — /index-standards se refresh hota hai", "standards:"]
for rel, title in entries:
    yml.append(f"  - path: {rel}")
    yml.append(f"    title: \"{title}\"")
yml.append("agents_index: ../agents/INDEX.md")
open(f"{std_dir}/index.yml", "w", encoding="utf-8").write("\n".join(yml) + "\n")

print(f"Generated {len(staff)} agent specs + INDEX.md + NEW_AGENT_TEMPLATE.md + standards/index.yml")
