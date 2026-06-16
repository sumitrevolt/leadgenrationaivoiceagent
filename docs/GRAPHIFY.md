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
