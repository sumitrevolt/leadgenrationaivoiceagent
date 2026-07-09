# Graphify — code knowledge-graph (DEV tool)

> **Kya hai:** [safishamsi/graphify](https://github.com/safishamsi/graphify) (MIT, PyPI: `graphifyy`) — poore codebase ko ek **queryable knowledge-graph** me badalta (Tree-sitter AST + optional LLM semantic edges). AI coding-assistant (Claude Code) ko bade codebase me relationships/architecture samajhne deta — grep/file-by-file ki jagah structured query.
>
> **DEV-only:** Yeh **product/VPS feature NAHI** hai (customers/voice-agent se koi lena-dena nahi). Sirf development/navigation ke liye. Generated artifacts **gitignored + dockerignored** hain — prod image me kabhi nahi jaate.

## Install (one-time, isolated — prod `.venv` safe)
```
uv tool install graphifyy        # 2 executables: graphify, graphify-mcp
```

## Build / refresh the graph (FREE — AST only, no LLM, no API cost)
```
graphify update app              # -> app/graphify-out/{graph.json, GRAPH_REPORT.md}
```
- Last build: **9,881 nodes · 18,148 edges · 446 communities** (86% EXTRACTED, 14% INFERRED), token cost **0**.
- `graph.html` viz auto-skips (>5000 nodes). Chahiye to: `GRAPHIFY_VIZ_NODE_LIMIT=12000 graphify update app` ya `cluster-only --no-viz`.
- Code change ke baad: `graphify update app` (incremental, only changed files re-extract — no API cost).

## Query (the actual value)
```
graphify query "where are razorpay payment routes defined" --graph app/graphify-out/graph.json --budget 800
graphify explain "free_ai" --graph app/graphify-out/graph.json
graphify path "Payment" "AuditLog" --graph app/graphify-out/graph.json
graphify affected "Subscription" --graph app/graphify-out/graph.json   # reverse: kya impact hoga
```

## Community naming (optional, FREE + PRIVATE via local Ollama)
Default communities `Community N` placeholders hote. Local ollama se naam do (no paid LLM, code local rehta):
```
graphify label app --backend=ollama --model=qwen2.5:3b-instruct
```

## MCP server (AI assistant ke liye structured tools)
```
graphify-mcp                     # stdio MCP server over app/graphify-out/graph.json
```

## Governance rule (repo-learning only)
Graphify ko product feature mat samjho. Yeh customer/admin dashboard, automation engine, lead pipeline, voice agent, ya production delivery flow me directly run nahi hota.

- `pyproject.toml`, `requirements*.txt`, aur `frontend/package.json` me `graphify`, `graphifyy`, ya `graphify-mcp` app dependency add mat karo.
- `.mcp.json` + `graphify_refresh` scripts = AI coding assistant / repo-understanding layer.
- Output ko source-of-truth nahi mano: graph hints ko code grep, tests, aur runtime docs se verify karo.
- License-safe learning: Graphify/report se architecture patterns aur risk areas extract karo; unrelated external code copy mat karo.

Recommended coding prompt:
```
Before coding, refresh/use Graphify on the repo and use the graph report to identify god nodes, broken flows, missing integrations, and customer-delivery bottlenecks. Then verify every finding against source code before editing.
```

## Handoff memory workflow
Graphify structural memory deta hai; business decisions aur previous-session reasoning docs me likhne padte hain. Har major AI session ke start/end pe yeh workflow follow karo:

Start:
```
scripts\graphify_refresh.bat
graphify query "What is Product One customer delivery flow?" --graph app/graphify-out/graph.json --budget 1200
graphify query "Which admin/customer dashboard flows are incomplete or disconnected?" --graph app/graphify-out/graph.json --budget 1200
```

Then read:
- `app/graphify-out/GRAPH_REPORT.md`
- `docs/AI_HANDOFF.md`
- `docs/CURRENT_STATE.md`
- `docs/NEXT_ACTIONS.md`

End:
1. Run changed-area tests + `prod_check.py` + `check_secrets.py`.
2. Update `docs/AI_HANDOFF.md` with changed files, routes, DB/schema, env, tests, pending work, and next prompt.
3. Update `docs/CURRENT_STATE.md` and `docs/NEXT_ACTIONS.md` if the active product state changed.
4. Run `scripts\graphify_refresh.bat` again.

Do not re-audit the full repo from zero unless Graphify/report freshness or the handoff docs are stale. Continue from the last known state and focus the current sprint on customer deliverability: onboarding, admin cockpit, automation logs, social setup wizard, delivery proof, and Product One fulfilment.

## IDE skill (`/graphify`) — MANUAL (self-modification, agent ne auto nahi kiya)
`/graphify` slash-command chahiye to khud register karo (agent `.claude/` config khud modify nahi karta):
```
graphify install --platform claude
```

## Notes
- **Free-stack:** AST extraction LLM-free. LLM sirf optional semantic-edge/labeling pe — wahan **local Ollama** use karo (zero cost, code local).
- **Artifacts gitignored** (`graphify-out/`, `app/graphify-out/`) — regenerable, large (graph.json ~9MB). Repo me commit nahi hote, prod image me bake nahi hote (`.dockerignore`).
- Graph staleness: report me "Built from commit" likha hota — `git rev-parse HEAD` se compare karke `graphify update app` re-run karo.

---

## Refresh automation + MCP wiring (added 2026-06-16)

### 1. Staleness-aware refresh (one command, FREE)
`graphify update app` ko manually yaad rakhne ki zaroorat nahi — script khud GRAPH_REPORT.md ka "Built from commit" vs `git HEAD` compare karke sirf stale hone par rebuild karta (incremental, AST-only, token cost 0).
```
scripts\graphify_refresh.bat          # Windows (dev) — auto: rebuild only if stale
scripts\graphify_refresh.bat --force  # always rebuild
bash scripts/graphify_refresh.sh      # git-bash / WSL / VPS
```
> **Abhi STALE hai:** graph `9b244493` se bana, HEAD aage hai → ek baar `scripts\graphify_refresh.bat` chala lo.

Chaho to commit pe auto-refresh: `.pre-commit-config.yaml` me ek local hook add kar sakte ho (par har commit thoda slow hoga — manual/script recommended).

### 2. graphify-mcp → Claude Code (agents seedha graph query karein)
`.mcp.json` (repo root) ab `graphify` MCP server register karta — Claude Code / Cowork restart pe AI ko structured graph-tools milte (`query`/`explain`/`affected`/`path`) bina har baar CLI chalaye. **Yahi asli leverage hai** (grep/file-by-file ki jagah structured codebase query).

**One-time setup:**
```
uv tool install graphifyy     # graphify + graphify-mcp PATH pe (agar pehle se nahi)
# .mcp.json already wired -> Claude Code RESTART karo (project MCP servers reload)
```
- MCP server stdio hai, `app/graphify-out/graph.json` (project root se) auto-find karta. Pehle `graphify_refresh.bat` chala ke graph fresh rakho — MCP usi file ko serve karta.
- **Agar Claude Code graph na dhoonde:** `.mcp.json` me args add karo `["--graph","app/graphify-out/graph.json"]`; ya command ko `where graphify-mcp` ke full path se replace karo (Windows PATH issue).
- `.mcp.json` commit karna safe hai (koi secret nahi) — team ko bhi same MCP milta.
