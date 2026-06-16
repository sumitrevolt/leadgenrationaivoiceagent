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
