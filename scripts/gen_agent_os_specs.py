"""Generate agent-os/agents/*.md from app/platform/team.py STAFF (code = truth).

Also injects routing/governance blocks from app.platform.agent_os_routing.
Run:  .venv\\Scripts\\python.exe scripts\\gen_agent_os_specs.py
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.platform.agent_os_routing import policy_markdown_block  # noqa: E402

src = (REPO / "app" / "platform" / "team.py").read_text(encoding="utf-8")
tree = ast.parse(src)
staff = None
for node in ast.walk(tree):
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "STAFF"
    ):
        staff = ast.literal_eval(node.value)
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "STAFF":
                staff = ast.literal_eval(node.value)
assert staff, "STAFF not found"

BASE = ["global/config", "global/logging", "global/feature-flags"]
PROD = {
    "voice": [
        "voice/hot-path",
        "voice/free-provider-chain",
        "voice/circuit-breaker",
        "voice/compliance-gate",
        "voice/reply-mirror",
    ],
    "marketing": ["backend/error-handling", "backend/lazy-imports"],
    "platform": [
        "backend/api-routers",
        "backend/auth",
        "backend/error-handling",
        "backend/lazy-imports",
        "backend/pydantic-models",
    ],
}
EXTRA = {
    "nikhil": ["billing/billing-truth"],
    "vidya": ["billing/billing-truth"],
    "lekha": ["frontend/admin-actions"],
    "kavya": ["frontend/admin-actions"],
    "hermes": ["frontend/admin-actions"],
    "vikram": ["frontend/admin-actions"],
    "arya": ["frontend/admin-actions"],
}

outdir = REPO / "agent-os" / "agents"
outdir.mkdir(parents=True, exist_ok=True)


def gates(text: str) -> list[str]:
    return sorted(set(re.findall(r"gated ([A-Z_]+)", text)))


def kpis(text: str) -> list[str]:
    m = re.findall(r"KPIs?:\s*([a-z_0-9, ]+)", text)
    out: list[str] = []
    for grp in m:
        out += [k.strip() for k in grp.split(",") if k.strip()]
    return out


index_lines = [
    "# Agent OS — VPS AI Staff Index (generated from app/platform/team.py — code = truth)",
    "",
]
for key, a in staff.items():
    stds = BASE + PROD.get(a["product"], []) + EXTRA.get(key, [])
    g = gates(a["duties"] + " " + a["schedule"])
    k = kpis(a["duties"])
    lines = [
        f"# {a['emoji']} {a['name']} — {a['title']}",
        "",
        f'> Source of truth: `app/platform/team.py` STAFF["{key}"] + '
        f"`app/platform/agent_os_routing.py`. Yeh spec code se DERIVED hai — "
        f"code badle to `python scripts/gen_agent_os_specs.py` re-run karo. "
        f"Code vs spec conflict = code wins.",
        "",
        f"- **Key:** `{key}`",
        f"- **Product:** {a['product']}",
        f"- **Schedule:** {a['schedule']}",
    ]
    if g:
        lines.append(
            f"- **Feature gates:** {', '.join('`' + x + '`' for x in g)} (env-flag, INERT default)"
        )
    if k:
        lines.append(f"- **KPIs:** {', '.join('`' + x + '`' for x in k)}")
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
    lines += policy_markdown_block(key, a["product"])
    lines += [
        "## Non-negotiables (CLAUDE.md §5)",
        "",
        "- Compliance gates (DND fail-closed, AI-disclosure, 9am-7pm window, consent ledger) KABHI disable nahi.",
        "- Customer data cross-client leak nahi; secrets sirf `.env`.",
        "- Free AI stack only; external call KABHI route/agent crash nahi karta (graceful degradation).",
        "- `log_event()` se har kaam attribute karo — invisible automation nahi.",
        "",
    ]
    (outdir / f"{key}.md").write_text("\n".join(lines), encoding="utf-8")
    index_lines.append(
        f"- **{a['name']}** (`{key}`) — {a['title']} · {a['product']} · {a['schedule']}"
    )

(outdir / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

TEMPLATE = """# 🆕 NEW AGENT TEMPLATE — naya AI staff agent add karne ka SOP

> Council rule (2026-06-25 billionaire-audit): naya agent SIRF tab jab wo *measurable operational leverage* de jo current roster nahi deta. Pehle folding/reuse consider karo (Hermes ne Kavya/Tara ke engines REUSE kiye the).

## Checklist (sab mandatory)

1. **Roster entry:** `app/platform/team.py` STAFF me key add karo — `product` (voice/marketing/platform), `name`, `emoji`, `title`, `duties` (KPI naam ke saath), `schedule`.
2. **Feature gate:** naya env flag (e.g. `MY_AGENT=1`), INERT default, `AUTOMATION_FLAGS` registry me register.
3. **Routing policy:** `app/platform/agent_os_routing.py` me `_AGENT_OVERRIDES` entry — category, OmniRoute task (ya NONE), privacy class, contact/publish/write flags, retries/timeout/queue.
4. **Engine module:** `app/agents/<name>.py` — padosi copy karo (lazy `from app.voice_agent import free_ai` FUNCTION ke andar, module-top pe nahi; try/except + graceful degradation; `log_event()` attribution).
5. **Scheduler wiring:** `team_scheduler.py` me job (boot-grace respect karo) — heavy kaam Celery only, web process me nahi.
6. **Spec regenerate:** `python scripts/gen_agent_os_specs.py` — agent-os/agents/<key>.md auto-banega (routing block included).
7. **Test + verify:** targeted pytest + `prod_check.py` + duplicate-route grep. Evidence ke bina done nahi.
8. **Memory write-back:** `memory/decisions.md` me ADR + CLAUDE.md `## Current State`.

## Required template fields (fill before merge)

| Field | Example |
| --- | --- |
| Agent ID | `zara` |
| Display name | Zara |
| Business purpose | Approved social queue drain |
| Owner | Founder / ops |
| Inputs | Approved content job |
| Outputs | Published post / fail record |
| Required tools | Postiz / Telegram |
| Primary model class | free_ai bulk / OmniRoute `leadgen.agent_ops` if eligible |
| Fallback model class | free_ai chain |
| Privacy classification | INTERNAL_SANITIZED |
| Maximum runtime | 45s |
| Maximum retries | 2 |
| Cost ceiling | free-stack only |
| Queue | celery |
| Schedule | queue-driven |
| Approval gate | yes before publish |
| Success metric | post_id non-empty |
| Health check | SOCIAL_ENGINE + queue depth |
| Disable switch | `SOCIAL_ENGINE=0` / Office pause |
| Rollback | unset gate; restore prior job status |

## Standards jo HAR agent pe lagte hai

- `agent-os/standards/global/config.md` · `global/logging.md` · `global/feature-flags.md`
- Product-specific: voice → `voice/*`; marketing → `backend/error-handling`, `backend/lazy-imports`; platform → `backend/*`
- Billing touch → `billing/billing-truth.md` (packages.py = single source)

## OmniRoute (optional, double-gated)

Agent LLM calls default free_ai chain use karte hai. OmniRoute route tabhi jab:
1. Policy me `omniroute_task` set hai **aur** privacy `INTERNAL_SANITIZED`
2. `OMNIROUTE_ENABLED=1` **aur** `OMNIROUTE_AGENTS=1` **aur** `OMNIROUTE_API_KEY` set
3. Payload sanitized (`mask_customer_data` + `validate_no_secrets`)

Voice/realtime, billing, compliance, CRM-PII agents = `omniroute_task=None` (forbidden).
Fail-open: OmniRoute down = free_ai chain unchanged.
"""
(outdir / "NEW_AGENT_TEMPLATE.md").write_text(TEMPLATE, encoding="utf-8")

# standards/index.yml populate
std_dir = REPO / "agent-os" / "standards"
entries = []
for root, _, files in os.walk(std_dir):
    for f in sorted(files):
        if f.endswith(".md"):
            full = Path(root) / f
            rel = full.relative_to(std_dir).as_posix()
            title = full.read_text(encoding="utf-8").splitlines()[0].strip("# ").strip()
            entries.append((rel, title))
entries.sort()
yml = [
    "# Agent OS Standards Index",
    "# Generated by scripts/gen_agent_os_specs.py — /index-standards se refresh hota hai",
    "standards:",
]
for rel, title in entries:
    yml.append(f"  - path: {rel}")
    yml.append(f'    title: "{title}"')
yml.append("agents_index: ../agents/INDEX.md")
(std_dir / "index.yml").write_text("\n".join(yml) + "\n", encoding="utf-8")

print(
    f"Generated {len(staff)} agent specs + INDEX.md + NEW_AGENT_TEMPLATE.md + standards/index.yml "
    f"(repo={REPO})"
)
