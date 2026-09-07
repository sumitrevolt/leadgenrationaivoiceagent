import argparse
import json
import os
import sqlite3
import subprocess
import urllib.request

import yaml

# OmniRoute loopback auth is not enforced (ADR-167); key read from env only —
# never hardcode it (GitGuardian incident 36739747/36798909).
OMNIROUTE_API_KEY = os.environ.get("OMNIROUTE_API_KEY", "")

# Exactly 14 canonical OmniRoute combos — `leadsgen combo N` (2026-09-05
# council: the gateway now holds exactly these 14; legacy leadgen-*/claude-omni-*
# names are registered as same-UUID aliases in the gateway DB and stay here as
# display/alias ids so app _TASK_ROUTES and the Claude Desktop filter resolve).
# (id, real, name) per combo — id is the canonical claude-omni-* alias used by
# the Claude Desktop frontend filter; real is the app-facing leadgen-* alias;
# name is the human label. canonical = the exact `leadsgen combo N` gateway id.
ALL_COMBOS = [
    {"id": "claude-omni-coding-primary", "real": "leadgen-coding-primary", "canonical": "leadsgen combo 1", "name": "LeadsGen Combo 1 — Coding Primary", "email": "admin@leadsgenai.in", "role": "Coding & Logic Primary (Worker #1)"},
    {"id": "claude-omni-coding-fast", "real": "leadgen-coding-fast", "canonical": "leadsgen combo 2", "name": "LeadsGen Combo 2 — Coding Fast", "email": "ops@leadsgenai.in", "role": "Coding Fast Lane (Worker #2)"},
    {"id": "claude-omni-repo-analysis", "real": "leadgen-repo-analysis", "canonical": "leadsgen combo 3", "name": "LeadsGen Combo 3 — Repo Analysis", "email": "hello@leadsgenai.in", "role": "Repo Architecture Deep Scan (Worker #3)"},
    {"id": "claude-omni-test-generation", "real": "leadgen-test-generation", "canonical": "leadsgen combo 4", "name": "LeadsGen Combo 4 — Test Generation", "email": "support@leadsgenai.in", "role": "Automated Test & QA (Worker #4)"},
    {"id": "claude-omni-agent-ops", "real": "leadgen-agent-ops", "canonical": "leadsgen combo 5", "name": "LeadsGen Combo 5 — Agent Ops", "email": "sunny@leadsgenai.in", "role": "Agent Workforce Operations (Worker #5)"},
    {"id": "claude-omni-swara-live", "real": "leadgen-swara-live", "canonical": "leadsgen combo 6", "name": "LeadsGen Combo 6 — Swara Live", "email": "sumit20016@gmail.com", "role": "Voice Realtime Fallback (Worker #6 / VPS)"},
    {"id": "claude-omni-marketing-content", "real": "leadgen-marketing-content", "canonical": "leadsgen combo 7", "name": "LeadsGen Combo 7 — Marketing Content", "email": "bunnybunnysunny49@gmail.com", "role": "Marketing Content & Copy (Worker #7)"},
    {"id": "claude-omni-prospect-enrich", "real": "leadgen-prospect-enrich", "canonical": "leadsgen combo 8", "name": "LeadsGen Combo 8 — Prospect Enrich", "email": "bunnysunnysunny49@gmail.com", "role": "Prospecting & Lead Enrichment (Worker #8)"},
    {"id": "claude-omni-outreach-email", "real": "leadgen-outreach-email", "canonical": "leadsgen combo 9", "name": "LeadsGen Combo 9 — Outreach Email", "email": "damsamsamdam39@gmail.com", "role": "Outreach Email & Follow-up (Worker #9)"},
    {"id": "claude-omni-seo-keyword", "real": "leadgen-seo-keyword", "canonical": "leadsgen combo 10", "name": "LeadsGen Combo 10 — SEO Keyword", "email": "daryananisumit440@gmail.com", "role": "SEO & SEM Keyword Clustering (Worker #10)"},
    {"id": "claude-omni-governor-review", "real": "leadgen-governor-review", "canonical": "leadsgen combo 11", "name": "LeadsGen Combo 11 — Governor Review", "email": "sunnybunny23211@gmail.com", "role": "Dual Governor Code Review (Worker #11)"},
    {"id": "claude-omni-project-best", "real": "leadgen-project-best", "canonical": "leadsgen combo 12", "name": "LeadsGen Combo 12 — Project Best", "email": "sunnydaryanani2@gmail.com", "role": "50-Model Master Flagship (Worker #12)"},
    {"id": "claude-omni-free-first", "real": "leadgen-14th-combo", "canonical": "leadsgen combo 13", "name": "LeadsGen Combo 13 — Free First (VPS)", "email": "CLI Auto-Key", "role": "Free-First Failover Lane (Worker #13 / VPS)"},
    {"id": "claude-omni-general", "real": "leadsgen-combo-14", "canonical": "leadsgen combo 14", "name": "LeadsGen Combo 14 — General", "email": "OmniRoute Master Key", "role": "General Purpose Free-Tier (Worker #14)"},
]

COMBO_IDS = [c["id"] for c in ALL_COMBOS]
CANONICAL_COMBO_IDS = [c["canonical"] for c in ALL_COMBOS]
LEGACY_COMBO_IDS = [c["real"] for c in ALL_COMBOS] + COMBO_IDS
ALL_MODEL_IDS = CANONICAL_COMBO_IDS + LEGACY_COMBO_IDS


PYTHON_PATH = r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\.venv\Scripts\python.exe"
REPO_DIR = r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent"
GRAPHIFY_EXE = r"C:\Users\Ratanshila\AppData\Roaming\uv\tools\graphifyy\Scripts\graphify-mcp.exe"
if not os.path.exists(GRAPHIFY_EXE):
    GRAPHIFY_EXE = "graphify-mcp"

UNIVERSAL_MCP_SERVERS = {
    "leadgen_admin_harness": {
        "command": PYTHON_PATH,
        "args": [os.path.join(REPO_DIR, r"scripts\leadgen_admin_harness_mcp.py")],
    },
    "buzz": {
        "command": PYTHON_PATH,
        "args": [os.path.join(REPO_DIR, r"scripts\buzz_mcp.py")],
        "env": {"BUZZ_RELAY": "ws://127.0.0.1:3100"},
    },
    "puppeteer": {
        "command": "npx.cmd",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
    },
    "playwright": {
        "command": "npx.cmd",
        "args": ["-y", "@executeautomation/playwright-mcp-server"],
    },
    "filesystem": {
        "command": "npx.cmd",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", REPO_DIR],
    },
    "graphify": {
        "command": GRAPHIFY_EXE,
        "args": ["--graph", os.path.join(REPO_DIR, r"app\graphify-out\graph.json")],
    },
}


def sync_dsh():
    dsh_yaml_path = os.path.expanduser(r"~\.dsh\settings.yaml")
    if os.path.exists(dsh_yaml_path):
        with open(dsh_yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        if "llm-pi-ai" not in data:
            data["llm-pi-ai"] = {}
        if "providers" not in data["llm-pi-ai"]:
            data["llm-pi-ai"]["providers"] = {}

        models_list = [
            {
                "id": c["canonical"],
                "name": c["name"],
                "contextWindow": 1048576,
                "maxTokens": 16384,
            }
            for c in ALL_COMBOS
        ]
        models_list += [
            {"id": c["real"], "name": f"{c['name']} (legacy)", "contextWindow": 1048576, "maxTokens": 16384}
            for c in ALL_COMBOS
        ]
        data["llm-pi-ai"]["providers"]["omniroute"] = {
            "displayName": "OmniRoute (12 Combos - 1M Context)",
            "api": "openai-completions",
            "baseURL": "http://127.0.0.1:20128/v1",
            "apiKeyEnv": "OMNIROUTE_API_KEY",
            "models": models_list,
        }
        data["mcpServers"] = UNIVERSAL_MCP_SERVERS

        with open(dsh_yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        print(f"[OK] DSH settings synced ({len(models_list)} unique combos - 1M context + Full Project MCPs) -> {dsh_yaml_path}")


def sync_claude():
    claude_dir = os.path.expanduser(r"~\AppData\Roaming\Claude")
    if os.path.exists(claude_dir):
        # 1. Update claude_desktop_config.json (The canonical and ONLY MCP config for Claude Desktop)
        claude_config_path = os.path.join(claude_dir, "claude_desktop_config.json")
        config_data = {"mcpServers": UNIVERSAL_MCP_SERVERS}
        with open(claude_config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        # 2. Ensure settings.json is valid clean JSON without invalid root keys
        claude_settings_path = os.path.join(claude_dir, "settings.json")
        data = {}
        if os.path.exists(claude_settings_path):
            try:
                with open(claude_settings_path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        # Remove any invalid keys that cause Electron crashes
        data.pop("inferenceGateway", None)
        data.pop("mcpServers", None)
        with open(claude_settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(
            f"[OK] Claude Desktop MCP config synced (Full Project MCPs + Computer Use) -> {claude_dir}"
        )


def sync_workbuddy():
    wb_dir = os.path.expanduser(r"~\.workbuddy-ai")
    if os.path.exists(wb_dir):
        # 1. Update settings.json
        wb_settings_path = os.path.join(wb_dir, "settings.json")
        data = {}
        if os.path.exists(wb_settings_path):
            try:
                with open(wb_settings_path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data["omniroute"] = {
            "baseURL": "http://127.0.0.1:22000",
            "apiKey": OMNIROUTE_API_KEY,
            "models": ALL_MODEL_IDS,
        }
        data["mcpServers"] = UNIVERSAL_MCP_SERVERS

        with open(wb_settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # 2. Update models.json (WorkBuddy AI custom provider models array with 1M context)
        wb_models_path = os.path.join(wb_dir, "models.json")
        wb_models = []
        # Preserve non-OmniRoute models if any
        if os.path.exists(wb_models_path):
            try:
                with open(wb_models_path, encoding="utf-8") as f:
                    existing = json.load(f)
                    if isinstance(existing, list):
                        wb_models = [
                            m
                            for m in existing
                            if not (isinstance(m, dict) and m.get("vendor") == "OmniRoute")
                        ]
            except Exception:
                wb_models = []

        for c in ALL_COMBOS:
            wb_models.append(
                {
                    "id": c["canonical"],
                    "name": c["name"],
                    "vendor": "OmniRoute",
                    "url": "http://127.0.0.1:22000/v1/chat/completions",
                    "apiKey": OMNIROUTE_API_KEY,
                    "supportsToolCall": True,
                    "supportsImages": False,
                    "supportsReasoning": True,
                    "useCustomProtocol": False,
                    "contextLength": 1048576,
                    "maxTokens": 16384,
                }
            )
            wb_models.append(
                {
                    "id": c["id"],
                    "name": c["name"],
                    "vendor": "OmniRoute",
                    "url": "http://127.0.0.1:22000/v1/chat/completions",
                    "apiKey": OMNIROUTE_API_KEY,
                    "supportsToolCall": True,
                    "supportsImages": False,
                    "supportsReasoning": True,
                    "useCustomProtocol": False,
                    "contextLength": 1048576,
                    "maxTokens": 16384,
                }
            )
            wb_models.append(
                {
                    "id": c["real"],
                    "name": f"{c['name']} ({c['real']})",
                    "vendor": "OmniRoute",
                    "url": "http://127.0.0.1:20128/v1/chat/completions",
                    "apiKey": OMNIROUTE_API_KEY,
                    "supportsToolCall": True,
                    "supportsImages": False,
                    "supportsReasoning": True,
                    "useCustomProtocol": False,
                    "contextLength": 1048576,
                    "maxTokens": 16384,
                }
            )

        with open(wb_models_path, "w", encoding="utf-8") as f:
            json.dump(wb_models, f, indent=2)

        # 3. Write mcp_servers.json for WorkBuddy
        wb_mcp_path = os.path.join(wb_dir, "mcp_servers.json")
        with open(wb_mcp_path, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": UNIVERSAL_MCP_SERVERS}, f, indent=2)

        print(
            f"[OK] WorkBuddy AI synced (settings.json + models.json + mcp_servers.json: {len(wb_models)} combos - 1M context + Full Project MCPs) -> {wb_dir}"
        )


def sync_hermes():
    # 1. Roaming connections.json & mcp_servers.json
    hermes_roaming = os.path.expanduser(r"~\AppData\Roaming\Hermes")
    if os.path.exists(hermes_roaming):
        # Remove stale fallback/lock files that cause boot-loop
        fallback_file = os.path.join(hermes_roaming, "windows-sandbox-fallback.json")
        if os.path.exists(fallback_file):
            try:
                os.remove(fallback_file)
            except Exception:
                pass

        conn_path = os.path.join(hermes_roaming, "connections.json")
        conn_data = {
            "version": 2,
            "primary": "local",
            "launchMode": "last-used",
            "lastUsed": "local",
            "connections": [
                {"id": "local", "kind": "local", "label": "This device"},
            ],
        }
        with open(conn_path, "w", encoding="utf-8") as f:
            json.dump(conn_data, f, indent=2)

        roaming_mcp = os.path.join(hermes_roaming, "mcp_servers.json")
        with open(roaming_mcp, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": UNIVERSAL_MCP_SERVERS}, f, indent=2)
        print(f"[OK] Hermes Desktop Roaming connections + MCP synced -> {conn_path}")

    # 2. Local AppData hermes cache, auth & mcp
    hermes_local = os.path.expanduser(r"~\AppData\Local\hermes")
    if os.path.exists(hermes_local):
        all_combo_models = (
            ALL_MODEL_IDS
            + [
                "hermes-engineer",
                "claude-code",
                "hermes-research",
                "hermes-qa",
                "hermes-ops",
                "hermes-voice",
                "hermes-content",
                "hermes-prospect",
                "hermes-outreach",
                "hermes-seo",
                "hermes-governor",
                "hermes-master",
            ]
        )

        # provider_models_cache.json
        cache_path = os.path.join(hermes_local, "provider_models_cache.json")
        cache_data = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cache_data = json.load(f)
            except Exception:
                cache_data = {}

        now_ts = 1888106106.0
        cache_data["omniroute"] = {"fp": "omni12combos", "at": now_ts, "models": all_combo_models}
        cache_data["custom"] = {"fp": "custom12combos", "at": now_ts, "models": all_combo_models}
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2)

        # auth.json
        auth_path = os.path.join(hermes_local, "auth.json")
        if os.path.exists(auth_path):
            try:
                with open(auth_path, encoding="utf-8") as f:
                    auth_data = json.load(f)
                if "providers" not in auth_data:
                    auth_data["providers"] = {}
                key_val = OMNIROUTE_API_KEY
                auth_data["providers"]["omniroute"] = {
                    "provider": "omniroute",
                    "api_key": key_val,
                    "auth_type": "api_key",
                    "token": key_val,
                }
                auth_data["providers"]["custom"] = {
                    "provider": "custom",
                    "api_key": key_val,
                    "auth_type": "api_key",
                    "token": key_val,
                }
                with open(auth_path, "w", encoding="utf-8") as f:
                    json.dump(auth_data, f, indent=2)
            except Exception as e:
                print(f"[WARN] Hermes auth.json sync note: {e}")

        # config.yaml
        config_path = os.path.join(hermes_local, "config.yaml")
        if os.path.exists(config_path):
            try:
                with open(config_path, encoding="utf-8", errors="ignore") as f:
                    cfg_data = yaml.safe_load(f) or {}
                if "model" not in cfg_data:
                    cfg_data["model"] = {}
                cfg_data["model"]["default"] = "leadsgen combo 1"
                cfg_data["model"]["provider"] = "omniroute"
                cfg_data["model"]["base_url"] = "http://127.0.0.1:20128/v1"
                cfg_data["model"]["max_tokens"] = 16384
                cfg_data["model"]["context_length"] = 1048576

                if "providers" not in cfg_data:
                    cfg_data["providers"] = {}
                cfg_data["providers"]["omniroute"] = {
                    "name": "OmniRoute (12 Combos - 1M Context)",
                    "base_url": "http://127.0.0.1:20128/v1",
                    "key_env": "OMNIROUTE_API_KEY",
                    "model": "leadsgen combo 1",
                    "models": all_combo_models,
                    "discover_models": True,
                    "context_length": 1048576,
                }
                cfg_data["providers"]["custom"] = {
                    "name": "Claude Proxy (12 Combos - 1M Context)",
                    "base_url": "http://127.0.0.1:22000/v1",
                    "key_env": "OMNIROUTE_API_KEY",
                    "model": "claude-omni-coding-primary",
                    "models": all_combo_models,
                    "discover_models": True,
                    "context_length": 1048576,
                }

                # Register each individual combo under providers: so model switch succeeds for any alias
                for c in ALL_COMBOS:
                    slug_hyphen = c["name"].lower().replace(" ", "-")
                    provider_entry = {
                        "name": c["name"],
                        "base_url": "http://127.0.0.1:20128/v1",
                        "key_env": "OMNIROUTE_API_KEY",
                        "model": c["canonical"],
                        "models": [c["canonical"], c["real"], c["id"]],
                        "discover_models": False,
                        "context_length": 1048576,
                    }
                    cfg_data["providers"][slug_hyphen] = provider_entry
                    cfg_data["providers"][f"custom:{slug_hyphen}"] = provider_entry
                    cfg_data["providers"][c["id"]] = provider_entry
                    cfg_data["providers"][c["real"]] = provider_entry

                # Also register in custom_providers
                cfg_data["custom_providers"] = [
                    {
                        "name": c["name"],
                        "provider_key": c["name"].lower().replace(" ", "-"),
                        "base_url": "http://127.0.0.1:20128/v1",
                        "model": c["real"],
                        "key_env": "OMNIROUTE_API_KEY",
                        "context_length": 1048576,
                    }
                    for c in ALL_COMBOS
                ]

                cfg_data["mcp_servers"] = UNIVERSAL_MCP_SERVERS

                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.dump(cfg_data, f, default_flow_style=False, sort_keys=False)
            except Exception as e:
                print(f"[WARN] Hermes config.yaml sync note: {e}")

        # Local mcp_servers.json
        local_mcp = os.path.join(hermes_local, "mcp_servers.json")
        with open(local_mcp, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": UNIVERSAL_MCP_SERVERS}, f, indent=2)

        print(
            f"[OK] Hermes Agent Local AppData synced ({len(all_combo_models)} combos in provider_models_cache + auth + config.yaml with 1M context + Full Project MCPs) -> {hermes_local}"
        )


def sync_openclaw():
    openclaw_dir = os.path.expanduser(r"~\.openclaw")
    if not os.path.exists(openclaw_dir):
        return

    config_path = os.path.join(openclaw_dir, "openclaw.json")
    try:
        data = {}
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)

        if "models" not in data or not isinstance(data["models"], dict):
            data["models"] = {}
        if "providers" not in data["models"] or not isinstance(data["models"]["providers"], dict):
            data["models"]["providers"] = {}

        omni_models = [
            {
                "id": c["canonical"],
                "name": f"{c['name']} (OmniRoute 1M)",
                "reasoning": False,
                "input": ["text"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                "contextWindow": 1048576,
                "maxTokens": 16384,
            }
            for c in ALL_COMBOS
        ]

        custom_models = [
            {
                "id": c["canonical"],
                "name": f"{c['name']} (Claude Proxy 1M)",
                "reasoning": False,
                "input": ["text"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                "contextWindow": 1048576,
                "maxTokens": 16384,
            }
            for c in ALL_COMBOS
        ]

        data["models"]["providers"]["omniroute"] = {
            "baseUrl": "http://127.0.0.1:20128/v1",
            "apiKey": OMNIROUTE_API_KEY,
            "api": "openai-completions",
            "models": omni_models,
        }

        data["models"]["providers"]["custom"] = {
            "baseUrl": "http://127.0.0.1:22000/v1",
            "apiKey": OMNIROUTE_API_KEY,
            "api": "openai-completions",
            "models": custom_models,
        }

        if "agents" not in data or not isinstance(data["agents"], dict):
            data["agents"] = {}
        if "defaults" not in data["agents"] or not isinstance(data["agents"]["defaults"], dict):
            data["agents"]["defaults"] = {}

        data["agents"]["defaults"]["model"] = {
            "primary": "custom/claude-omni-coding-primary"
        }

        if "models" not in data["agents"]["defaults"] or not isinstance(data["agents"]["defaults"]["models"], dict):
            data["agents"]["defaults"]["models"] = {}

        data["agents"]["defaults"]["models"]["custom/*"] = {}
        data["agents"]["defaults"]["models"]["omniroute/*"] = {}
        data["agents"]["defaults"]["models"]["custom/claude-omni-coding-primary"] = {}
        data["agents"]["defaults"]["models"]["omniroute/leadgen-coding-primary"] = {}

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"[OK] OpenClaw config synced with OmniRoute & Claude Proxy 12 Combos -> {config_path}")
    except Exception as e:
        print(f"[WARN] OpenClaw sync note: {e}")


def sync_workspace_mcp():
    mcp_json_path = os.path.join(REPO_DIR, ".mcp.json")
    try:
        data = {"mcpServers": UNIVERSAL_MCP_SERVERS}
        with open(mcp_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[OK] Workspace .mcp.json synced -> {mcp_json_path}")
    except Exception as e:
        print(f"[WARN] Workspace .mcp.json sync note: {e}")


def sync_omniroute_sqlite():
    """Seed OmniRoute SQLite via the CANONICAL 14-combo seed (2026-09-05)."""
    # The live gateway keeps SQLite open while serving requests.  A recovery
    # sync must not race that connection: the runtime API is authoritative for
    # readiness, and seeding is only needed when the canonical catalog is
    # actually absent.  This also makes the watchdog idempotent during normal
    # healthy operation instead of producing a misleading "database locked"
    # warning every time it reconciles desktop configuration.
    try:
        with urllib.request.urlopen("http://127.0.0.1:20128/v1/models", timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        model_ids = {str(item.get("id", "")) for item in payload.get("data", []) if isinstance(item, dict)}
        if set(CANONICAL_COMBO_IDS).issubset(model_ids):
            print("[OK] OmniRoute live gateway already exposes all 14 canonical combos; SQLite seed skipped")
            return
    except Exception:
        # Gateway unavailable or malformed: fall through to the recovery seed.
        pass

    seed_script_win = os.path.join(os.path.dirname(__file__), "seed_omniroute_14combos.py")
    if not os.path.exists(seed_script_win):
        print(f"[WARN] Seed script not found: {seed_script_win}")
        return
    try:
        # The 14-combo seed is self-contained Python — run it directly (it does
        # its own docker cp + node:sqlite execution + DB backup).
        env = dict(os.environ)
        # The legacy locally-running image stores its DB under /app/data;
        # the pinned image uses /root/.omniroute. Detect the active container
        # mount so recovery never seeds an unused database.
        container = env.get("OMNIROUTE_CONTAINER", "leadgen_omniroute")
        try:
            mount = subprocess.run(
                ["docker", "inspect", "--format", "{{json .Mounts}}", container],
                capture_output=True, text=True, timeout=10,
            )
            if "/app/data" in (mount.stdout or ""):
                env["OMNIROUTE_DB_PATH"] = "/app/data/storage.sqlite"
            else:
                env.setdefault("OMNIROUTE_DB_PATH", "/root/.omniroute/storage.sqlite")
        except Exception:
            env.setdefault("OMNIROUTE_DB_PATH", "/root/.omniroute/storage.sqlite")
        res = subprocess.run(
            [PYTHON_PATH, seed_script_win],
            capture_output=True,
            timeout=120,
            env=env,
        )
        if res.returncode == 0:
            print("[OK] OmniRoute SQLite seeded (14 combos via canonical seed)")
            print(res.stdout.decode().strip() if res.stdout else "")
        else:
            print(f"[WARN] OmniRoute SQLite seeding failed (exit {res.returncode}):")
            print(res.stderr.decode() if res.stderr else res.stdout.decode() if res.stdout else "")
    except subprocess.TimeoutExpired:
        print("[WARN] OmniRoute SQLite seeding timeout")
    except Exception as e:
        print(f"[WARN] OmniRoute SQLite seeding note: {e}")


def sync_verdant():
    """Enterprise Verdant Desktop sync — ensure directories exist and full 14 combos + MCPs are provisioned."""
    target_roaming = os.path.expanduser(r"~\AppData\Roaming\Verdant")
    target_dot = os.path.expanduser(r"~\.verdant")

    for t in (target_roaming, target_dot):
        os.makedirs(t, exist_ok=True)

    models = [
        {
            "id": c["canonical"],
            "name": c["name"],
            "vendor": "OmniRoute",
            "baseURL": "http://127.0.0.1:20128/v1",
            "apiKey": OMNIROUTE_API_KEY,
            "models": [c["canonical"], c["real"], c["id"]],
            "contextLength": 1048576,
            "maxTokens": 16384,
            "workerEmail": c.get("email", ""),
            "workerRole": c.get("role", ""),
        }
        for c in ALL_COMBOS
    ]

    config = {
        "version": 2,
        "defaultModel": "leadsgen combo 1",
        "providers": {
            "omniroute": {
                "name": "OmniRoute (14 LeadsGen Combos - 1M Context)",
                "base_url": "http://127.0.0.1:20128/v1",
                "apiKeyEnv": "OMNIROUTE_API_KEY",
                "models": models,
                "context_length": 1048576,
            },
            "claude_proxy": {
                "name": "Claude Proxy (Port 22000)",
                "base_url": "http://127.0.0.1:22000/v1",
                "apiKeyEnv": "OMNIROUTE_API_KEY",
                "models": models,
                "context_length": 1048576,
            }
        },
        "mcpServers": UNIVERSAL_MCP_SERVERS,
    }

    for target in (target_roaming, target_dot):
        try:
            cfg_file = os.path.join(target, "config.json")
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            models_file = os.path.join(target, "models.json")
            with open(models_file, "w", encoding="utf-8") as f:
                json.dump(models, f, indent=2)

            mcp_file = os.path.join(target, "mcp_servers.json")
            with open(mcp_file, "w", encoding="utf-8") as f:
                json.dump({"mcpServers": UNIVERSAL_MCP_SERVERS}, f, indent=2)

            settings_file = os.path.join(target, "settings.json")
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump({
                    "activeProvider": "omniroute",
                    "activeModel": "leadsgen combo 1",
                    "autoFallback": True,
                    "mcpEnabled": True,
                    "workerEmail": "admin@leadsgenai.in"
                }, f, indent=2)

            print(f"[OK] Verdant Desktop provisioned ({len(models)} combos + MCPs) -> {target}")
        except Exception as e:
            print(f"[WARN] Verdant sync note for {target}: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize the canonical 14 OmniRoute combos across local desktop clients."
    )
    parser.parse_args()
    print("=== Syncing 14 Canonical OmniRoute Combos (1M+ Context & MCP) Across All Apps ===")
    sync_omniroute_sqlite()
    sync_dsh()
    sync_claude()
    sync_workbuddy()
    sync_hermes()
    sync_openclaw()
    sync_verdant()
    sync_workspace_mcp()
    print("=== All Client App Configs Successfully Synced! ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
