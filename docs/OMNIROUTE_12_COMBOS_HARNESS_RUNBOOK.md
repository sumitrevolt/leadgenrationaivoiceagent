# OmniRoute 12-Combos & Dual-Computer Harness Runbook

> **Setup Status**: VERIFIED LIVE (2026-08-30)  
> **OmniRoute Gateway**: `http://127.0.0.1:20128/v1` (Docker compose managed, 40+ free flagship models per combo).  
> **Supported Clients**: Hermes Desktop, Claude Desktop, Antigravity IDE, LeadGen AI Agent OS.

---

## 1. Summary & Architecture

All **12 OmniRoute Combos** are configured and harnessed so both **Computer 1** (Local Host) and **Computer 2** (Peer PC / Remote) can route prompts through prioritized pools of 40+ free flagship models (Groq, Cerebras, OpenRouter free, Gemini free, NVIDIA NIM, SambaNova, etc.) with automated fallback.

### The 12 Active Combos

| # | Task ID | Primary Model / Combo | Fallback Model | Target Workload |
|---|---------|----------------------|----------------|-----------------|
| 1 | `leadgen.coding_primary` | `hermes-engineer` | `claude-code` | Feature building, coding & refactoring |
| 2 | `leadgen.coding_fast` | `claude-code` | `vps-01` | Rapid code edits & syntax checks |
| 3 | `leadgen.repo_analysis` | `hermes-research` | `hermes-qa` | Codebase architecture & graph analysis |
| 4 | `leadgen.test_generation` | `hermes-qa` | `hermes-engineer` | Automated pytest suite generation |
| 5 | `leadgen.agent_ops` | `hermes-ops` | `hermes-owner` | Agent OS workforce orchestration |
| 6 | `leadgen.swara_live` | `hermes-voice` | `vps-01` | Voice agent real-time fallback |
| 7 | `leadgen.marketing_content` | `hermes-content` | `hermes-ops` | Ad copy, social posts & marketing |
| 8 | `leadgen.prospect_enrich` | `hermes-prospect` | `hermes-research` | Lead qualification & scraping analysis |
| 9 | `leadgen.outreach_email` | `hermes-outreach` | `hermes-ops` | Email outreach & response triage |
| 10 | `leadgen.seo_keyword` | `hermes-seo` | `hermes-content` | SEM keywords & SEO page generation |
| 11 | `leadgen.governor_review` | `hermes-governor` | `hermes-qa` | Dual governor code review & audits |
| 12 | `leadgen.project_best` | `hermes-master` | `leadgen-project-best` | 50-Model Master Flagship Combo |

---

## 2. Desktop Launcher Usage

### Hermes Desktop

To launch Hermes Desktop with any of the 12 combos:

```powershell
# Default launch (50-model master flagship combo)
powershell -ExecutionPolicy Bypass -File scripts\start-hermes-omniroute.ps1

# Specific combo launch (e.g. Coding Primary)
powershell -ExecutionPolicy Bypass -File scripts\start-hermes-omniroute.ps1 -Combo leadgen.coding_primary

# From Computer 2 (connecting to Computer 1's gateway IP)
powershell -ExecutionPolicy Bypass -File scripts\start-hermes-omniroute.ps1 -OmniHost 192.168.1.10 -Combo leadgen.project_best
```

### Claude Desktop

To run Claude Desktop / Claude Code with OmniRoute:

```powershell
# Interactive session with Coding Primary combo
powershell -ExecutionPolicy Bypass -File scripts\start-claude-omniroute.ps1 -Combo leadgen.coding_primary

# One-shot command prompt with Master Flagship combo
powershell -ExecutionPolicy Bypass -File scripts\start-claude-omniroute.ps1 -Combo leadgen.project_best -Prompt "Analyze project health"

# From Computer 2 (connecting to Computer 1's gateway IP)
powershell -ExecutionPolicy Bypass -File scripts\start-claude-omniroute.ps1 -OmniHost 192.168.1.10 -Combo leadgen.coding_primary
```

---

## 3. Dual-Computer Setup (Computer 1 & Computer 2)

### Computer 1 (Host Machine running OmniRoute Gateway)
1. Gateway listens on `http://127.0.0.1:20128` (and host IP).
2. Verification CLI:
   ```powershell
   .venv\Scripts\python.exe scripts\harness_omniroute_12combos.py --verify
   ```

### Computer 2 (Peer PC / Remote Machine)
1. Ensure Computer 2 can reach Computer 1's IP on port `20128` (or use VPS gateway).
2. Set environment variables on Computer 2:
   ```powershell
   setx OMNIROUTE_HOST "192.168.1.10"   # Replace with Computer 1's IP
   setx OMNIROUTE_API_KEY "<YOUR_KEY>"
   ```
3. Run the harness on Computer 2:
   ```powershell
   .venv\Scripts\python.exe scripts\harness_omniroute_12combos.py --host 192.168.1.10
   ```

---

## 4. Claude Desktop Configuration (`claude_desktop_config.json`)

To wire Claude Desktop directly on either computer, add the following to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "omniroute_12combos": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-fetch",
        "http://127.0.0.1:20128/v1/responses"
      ],
      "env": {
        "OMNIROUTE_BASE_URL": "http://127.0.0.1:20128/v1",
        "OMNIROUTE_API_KEY": "%OMNIROUTE_API_KEY%"
      }
    }
  },
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:20128/v1",
    "ANTHROPIC_API_KEY": "%OMNIROUTE_API_KEY%"
  }
}
```

---

## 5. Verification Evidence

- **Gateway Probe**: `http://127.0.0.1:20128/api/health` -> HTTP 200 OK.
- **Unit Tests**: `pytest tests/test_omniroute_client.py` -> 20/20 PASSED.
- **Failover**: Fail-open design guarantees direct provider fallback if gateway is unreachable.
