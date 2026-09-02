# Graphify — code knowledge-graph (DEV tool)

> **Kya hai:** [safishamsi/graphify](https://github.com/safishamsi/graphify) (MIT, PyPI: `graphifyy`) — poore codebase ko ek **queryable knowledge-graph** me badalta (Tree-sitter AST + optional LLM semantic edges). AI coding-assistant (Claude Code) ko bade codebase me relationships/architecture samajhne deta — grep/file-by-file ki jagah structured query.
>
> **DEV-only:** Yeh **product/VPS feature NAHI** hai (customers/voice-agent se koi lena-dena nahi). Sirf development/navigation ke liye. Generated artifacts **gitignored + dockerignored** hain — prod image me kabhi nahi jaate.

## Install (one-time, isolated — prod `.venv` safe)
```
uv tool install graphifyy --with mcp   # 2 exe: graphify (CLI) + graphify-mcp. `--with mcp` ZAROORI — warna MCP server `ModuleNotFoundError: No module named 'mcp'` pe crash (CLI phir bhi chalti, par .mcp.json ka MCP nahi).
```

## Build / refresh the graph (FREE — AST only, no LLM, no API cost)
```
graphify update app              # -> app/graphify-out/{graph.json, GRAPH_REPORT.md}
```
- Last build (2026-07-12, HEAD `d722fcfb`): **14,611 nodes · 26,511 edges · 744 communities** (89% EXTRACTED, 11% INFERRED), token cost **0**.
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
> Staleness auto-detect: script `GRAPH_REPORT.md` "Built from commit" vs `git HEAD` compare karta — mismatch pe hi rebuild (last refresh 2026-07-12 = fresh @ `d722fcfb`).

Chaho to commit pe auto-refresh: `.pre-commit-config.yaml` me ek local hook add kar sakte ho (par har commit thoda slow hoga — manual/script recommended).

### 2. graphify-mcp → Claude Code (agents seedha graph query karein)
`.mcp.json` (repo root) ab `graphify` MCP server register karta — Claude Code / Cowork restart pe AI ko structured graph-tools milte (`query`/`explain`/`affected`/`path`) bina har baar CLI chalaye. **Yahi asli leverage hai** (grep/file-by-file ki jagah structured codebase query).

**One-time setup:**
```
uv tool install graphifyy --with mcp   # graphify + graphify-mcp PATH pe; --with mcp ZAROORI (warna MCP "No module named mcp" pe crash)
# .mcp.json already wired -> Claude Code RESTART karo (project MCP servers reload)
```
- MCP server stdio hai. **Gotcha (2026-07-12 fixed):** server DEFAULT `graphify-out/graph.json` (repo-root) dhoondta — hamara graph `app/graphify-out/graph.json` pe hai, isliye bare command har query pe "graph.json not found" deta tha. `.mcp.json` ab `--graph app/graphify-out/graph.json` pass karta (relative = team-portable). Pehle `graphify_refresh.bat` chala ke graph fresh rakho — MCP usi file ko serve karta.
- **Verified end-to-end (2026-07-12):** JSON-RPC handshake OK (`serverInfo: graphify 1.28.1`), 10 tools exposed (`query_graph`/`get_node`/`get_neighbors`/`get_community`/`god_nodes`/`graph_stats`/`shortest_path`/`list_prs`/`get_pr_impact`/`triage_prs`), `query_graph` real nodes-with-line-numbers return karta. **Prereq tha:** `uv tool install graphifyy --with mcp` (warna server `No module named 'mcp'` pe crash).
- **Agar Claude Code phir bhi graph na dhoonde:** `.mcp.json` command ko `where graphify-mcp` ke full path se replace karo (Windows PATH issue).
- `.mcp.json` commit karna safe hai (koi secret nahi) — team ko bhi same MCP milta.

---

## Token-Saving Context Architecture (added 2026-07-12)

> Yeh section CLAUDE.md §9.5 ka **full expansion** hai. CLAUDE.md lean pointer rakhta (always-loaded); detail yahan (on-demand). Goal: coding-agents (Claude/Codex/GLM/Kimi/DeepSeek/Gemini) **poora repo dobara na padhein** har session — graph-first navigate karein, source-verify karein, phir surgical edit.

### A. Repository Context Retrieval Protocol (graph-first, source-verified)
Har non-trivial task pe yeh sequence:
1. **Compact control context** — task + CLAUDE.md `## Current State` + relevant `memory/` file(s) + task ke landmines. **Pura repo/har doc auto-read mat karo.**
2. **Graph query FIRST** (broad grep/recursive-read se PEHLE) — MCP tools (`query`/`explain`/`path`/`affected`) ya CLI:
   ```powershell
   graphify query "<subsystem in plain words>" --graph app/graphify-out/graph.json --budget 800
   graphify explain "<symbol>"  --graph app/graphify-out/graph.json
   graphify path   "<A>" "<B>"  --graph app/graphify-out/graph.json
   graphify affected "<symbol>" --graph app/graphify-out/graph.json   # reverse blast-radius
   ```
3. **Bounded working set** — normally 3–8 impl + 1–4 test + relevant config/decision files. 6 me evidence hai to 30 mat kholo.
4. **Raw source verify** — graph = navigation, PROOF nahi (see §G: ~11% edges INFERRED). Exact `src=file loc=Lxxx` Read karke hi edit.
5. **Expand only if** — call-path adhoora · test hidden-dep dikhaye · runtime graph ko contradict kare · dynamic-import/route-registration graph me miss (FastAPI first-route-wins, decorators) · change subsystem-boundary cross kare.
6. **Surgical edit** → **targeted tests FIRST** (changed subsystem ke paas wale) → phir broad.
7. **Write-back** — facts badle tabhi `## Current State`/`decisions.md`/`progress.md`; graph stale ho to `scripts\graphify_refresh.bat` (FREE, AST-only). Bade context docs bina-zaroorat rewrite mat karo.

### B. Context budgets (guidance, not hard caps — safety > cosmetic token number)
- **Tier 0 (always-loaded):** CLAUDE.md identity + safety + §9.5 pointer. ~1–2k tok.
- **Tier 1 (task context):** requirement + relevant Current-State/decisions + graph-retrieved candidate list. ~2–6k tok.
- **Tier 2 (source):** sirf zaroori file+line-ranges. Full-file read tab jab range kaafi na ho.
- **Tier 3 (expansion):** cross-cutting arch / migration / security-audit / prod-incident / ambiguous failure — tabhi.
> Compliance/customer-delivery evidence KABHI token bachane ke liye skip mat karo (§5 gates). Accuracy > token cosmetics.

### C. Task Packet template (worker-model delegation — full transcript/repo-dump ki jagah)
Kisi worker model (GLM/Kimi/DeepSeek/Gemini/Codex/staff-engineer subagent) ko kaam dete waqt YEH bhejo, na ki poori chat + project summary:
```text
TASK: <one line>
REQUIRED OUTCOME (customer/admin-visible): <what must be true after>

GRAPH RESULT (from `graphify query`):
  Subsystem: <community/dir>
  Entry points: <file:line, file:line>
  Dependencies: <callees>
  Callers: <who calls this>
  Tests: <test file(s)>
  Blast radius: <graphify affected "<symbol>">

FILES ALLOWED (edit): <file1, file2, file3>
FILES READ-ONLY (context): <file4, file5>

INVARIANTS (must hold): tenant-isolation · entitlement-correctness · idempotency ·
  no secret leakage · delivery-ledger consistency · feature-flags stay safe(default-OFF) ·
  existing API/route compat · TRAI/DND fail-CLOSED (if telephony) · billing-truth (if pricing)

ACCEPTANCE TESTS: <exact pytest path(s)>
DO NOT: broad refactor · redesign arch · edit unrelated files · deploy · touch .env/customer data · fabricate evidence
RETURN: diff summary · tests run+result · assumptions · remaining risk
```

### D. Multi-model token routing (policy)
- **Cheap/free workers** → graph queries, file-candidate selection, repetitive scans, log/test-output summarize, duplicate-detection, boilerplate, formatting, low-risk refactor.
- **Strong coding workers (GLM/Kimi/DeepSeek/Gemini/Codex/`staff-engineer`)** → bounded implementation, isolated feature, test-writing, migration draft, UI component, targeted bugfix. **Input = graph-retrieved context + exact files (Task Packet §C), NOT whole-project history.**
- **Claude senior reviewer** → architecture decisions, security review, cross-subsystem change, prod incident, customer-delivery invariants, final-diff review, deploy risk, ambiguity/conflict resolution, acceptance verification. Claude ko premium tokens "files kahan hain" dhoondhne me KABHI mat jalao — woh graph ka kaam hai.
- **Final evidence rule:** koi bhi model dusre ke summary pe "production-ready" declare NAHI kar sakta — source/tests/runtime/prod evidence chahiye.

### E. Token benchmark (measured on THIS repo, 2026-07-12 — honest, not fabricated)
Graph: **14,611 nodes · 26,511 edges · 744 communities**, built from HEAD `d722fcfb`, 631 files (`app/`-scoped), token cost **0** (AST-only). Build/refresh ~seconds (16-worker AST).

Ran 4 representative queries (raw output in session log). Mechanism-level result, honestly stated (exact per-turn tokens repo-workflow pe measure nahi kiye — estimate transparent):

| Question | Graph-assisted result | Baseline (grep/read-first) |
|---|---|---|
| Where is Product-1 delivery completion calc'd? | 1 query → `product_one_delivery.py:847 customer_delivery_status()` + `delivery_ledger.py:196 log_event()` + `usage.py activate_plan()` → open ~3 files at known lines | grep `deliver*/complet*` → hits across ledger/usage/telephony/dashboards → open ~8–15 files to disambiguate |
| Social approval → schedule → publish? | 1 query → `content_approval.py` + `approvals_bridge.py` + `social_engine/{scheduling,engine,providers}.py` | grep `approv*/publish*/schedul*` → spread across marketing/ + social_engine/ + api/ → open ~10+ |
| What depends on Redis for integration health? | 1 query → `integration_health.py` + `automation_health.py` + `call_state.py RedisCallStore._redis()` + `today_overview.build()` | grep `redis` → 40+ files → manual filter |
| Unity virtual-office route → backend API? | **WEAK** — returned office_hq/web_call/voice nodes, NOT the real Unity WebGL→backend wiring | grep `unity/` + `frontend/` → **grep WINS here** |

**Honest verdict:** For **backend (`app/`) flows** the graph is *materially better* — it returns the 3–6 canonical files with line numbers in one call, replacing a multi-grep + open-15-files disambiguation loop (the biggest token sink). For **`frontend/`, docker-compose, `unity/`** (all outside `app/`) the graph is weak-to-useless — **grep/Read still win**. Median: for backend-navigation tasks, ~half-a-dozen fewer speculative file-opens per task; no correctness loss observed (graph pointed at the right files, verified against source). Build/update cost is negligible (0 tokens, seconds). **Setup justifies staying enabled** for backend work; do not oversell frontend/infra coverage.

### F. Prompt-cache / `.claudeignore` strategy → **Strategy A (CLI/MCP retrieval)**
- `app/graphify-out/` is **gitignored + dockerignored** (13–14MB `graph.json`). It is NOT a tracked repo file, so Claude Code does not auto-ingest it into the prompt each turn — **no cache-thrash risk today**. That is why a `.claudeignore` is **not required** right now (repo has none).
- Agents reach the graph via **`graphify-mcp` (stdio MCP, `.mcp.json`)** or the `graphify query` CLI — *scoped* queries, never the whole `graph.json` in context. This is the intended leverage (query, don't load).
- **If** you ever commit graph artifacts for cross-agent reuse (Strategy B — not recommended here), add a `.claudeignore` with `app/graphify-out/` + `**/graph.json` so Claude doesn't re-read the blob every turn.

### G. Coverage & known limitations (do not over-trust)
- **`app/`-scoped only.** File count: this line long said **631**; a live `graphify extract app` scan on 2026-08-07 reported **838 code + 2 docs**, with 8 files unclassified (`.xml` FreeSWITCH configs). Both numbers are recorded because the counting basis was never stated — do not treat either as authoritative; re-run the scan if the number matters. `frontend/`, `unity/`, `docker-compose*.yml`, root scripts = NOT in graph → use grep/Read.
- **~11% edges INFERRED** (avg confidence 0.66) — treat inferred relationships as *hints*, verify against source before acting.
- **Dynamic Python not captured** — runtime route-registration, decorator magic, `getattr`/importlib, string-dispatch. FastAPI first-route-wins duplicates: still grep all split routers (`duplicate-route-guard`).
- **Function-level import blind spot (permanent — 2026-08-07):** AST extractor does **not** follow `from X import Y as Z` inside a function body + later `Z.fn()`. This is the repo's common defensive-import idiom (`app/api/*.py` endpoints). Result: real callers missing from `path`/`affected` (e.g. `blueprint_graph()` → `build_graph()`). **Rule:** `"Graphify ko koi caller nahi mila" ≠ "koi caller nahi hai"` — act karne se pehle **grep** se confirm. Empty `affected` on a leaf with no inbound *tracked* edges can be correct; do not declare the tool broken from one empty result. Test `affected` on a node you already know has inbound `calls` edges.
- **`affected` is reverse-only** — it lists who depends on the symbol via tracked relations (`calls`, etc.). Module `contains` / docstring `rationale_for` are not in that list.
- **Node-ID scheme — CLEANUP DONE 2026-08-07/08.** `graphify extract app --force --code-only` completed (path **first**; `--code-only` required else it demands an LLM key for 2 doc files). Result: **19290 nodes / 36503 edges / 919 communities**, and graphify **no longer emits the `pre-#1504` warning**. All four tools re-verified on the rebuilt graph (`query` 35 nodes · `explain` correct src+line · `path` 1 hop · `affected` 3 callers).
  - ⚠️ **Honest limit of that claim:** node IDs still *look* name-based (`platform_blueprint_graph_build_graph`). The warning disappearing is graphify's own signal, not independent proof that same-name collisions are now impossible. Treat as "no longer flagged", not "proven collision-free".
  - **`--force` does NOT bust the extraction cache.** The run reported `0 re-extracted, 838 cached/unchanged` and rebuilt from `app/graphify-out/cache/` (2 entries). For a genuinely cold rebuild, clear that cache dir first.
  - **Source paths are now relative to the scan root** (`platform/blueprint_graph.py`, not `app/platform/...`). Prepend `app/` before using a graphify path as a repo path.
  - **Long runs: launch detached and poll.** The rebuild exceeds the MCP tool timeout; run it via `Start-Process` to a log + a `.done` marker (same reason `deploy_vps.sh` uses `setsid nohup`). Tool timeout ≠ command failed — an earlier "timed out" run had in fact completed in the background. Confirm by `graph.json` mtime, not by the tool's verdict.
  - Optional follow-up graphify itself suggests: `graphify cluster-only app` to regenerate `GRAPH_REPORT.md` + name communities.
- Stale-after-commit: graph = HEAD snapshot. `scripts\graphify_refresh.bat` rebuilds only if `GRAPH_REPORT.md` "Built from commit" ≠ `git HEAD`.

### H. Session handoff — reuse `docs/AI_HANDOFF.md` (do NOT mint a new file)
Session-to-session continuity already lives in **`docs/AI_HANDOFF.md`** (start-workflow + last-session summary + next context) alongside `docs/CURRENT_STATE.md` + `docs/NEXT_ACTIONS.md`. **Do not create `memory/CURRENT_SESSION.md`** — a 4th handoff surface is exactly the memory-proliferation the token-saving goal fights. Update `AI_HANDOFF.md` at session end (changed files/routes/tests/next-prompt); durable decisions → `memory/decisions.md`; chronological evidence → `progress.md`.

### I. Runtime agent/customer memory — SEPARATE decision (NOT in scope here)
Graphify solves **repository navigation** (dev-time, code structure). It does **not** solve evolving **runtime/business facts** (per-customer state, conversation history, temporal facts). A temporal-memory system (Graphiti/Neo4j/vector-DB) for that is a **separate** decision involving tenant-isolation, DPDP/privacy, storage, ops-cost, observability. **Recommendation: do NOT add a graph-DB / Graphiti to the production app now** — the platform already uses Postgres + Redis + Qdrant (single `kb_main`, `client:<id>` namespaces) for runtime memory. Revisit only if a concrete cross-session business-fact need emerges that those cannot serve; evaluate under `enterprise-readiness-audit` + `tenant-isolation-audit`.
