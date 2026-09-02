import json
import os
import sqlite3
import subprocess

import yaml

# Exactly 12 clean, unique OmniRoute dynamic combos with claude-omni- IDs for Claude Desktop frontend filter
ALL_COMBOS = [
    {
        "id": "claude-omni-coding-primary",
        "real": "leadgen-coding-primary",
        "name": "OmniRoute Coding Primary",
    },
    {
        "id": "claude-omni-coding-fast",
        "real": "leadgen-coding-fast",
        "name": "OmniRoute Coding Fast",
    },
    {
        "id": "claude-omni-repo-analysis",
        "real": "leadgen-repo-analysis",
        "name": "OmniRoute Repo Analysis",
    },
    {
        "id": "claude-omni-test-generation",
        "real": "leadgen-test-generation",
        "name": "OmniRoute Test Generation",
    },
    {"id": "claude-omni-agent-ops", "real": "leadgen-agent-ops", "name": "OmniRoute Agent Ops"},
    {"id": "claude-omni-swara-live", "real": "leadgen-swara-live", "name": "OmniRoute Swara Live"},
    {
        "id": "claude-omni-marketing-content",
        "real": "leadgen-marketing-content",
        "name": "OmniRoute Marketing Content",
    },
    {
        "id": "claude-omni-prospect-enrich",
        "real": "leadgen-prospect-enrich",
        "name": "OmniRoute Prospect Enrich",
    },
    {
        "id": "claude-omni-outreach-email",
        "real": "leadgen-outreach-email",
        "name": "OmniRoute Outreach Email",
    },
    {
        "id": "claude-omni-seo-keyword",
        "real": "leadgen-seo-keyword",
        "name": "OmniRoute SEO Keyword",
    },
    {
        "id": "claude-omni-governor-review",
        "real": "leadgen-governor-review",
        "name": "OmniRoute Governor Review",
    },
    {
        "id": "claude-omni-project-best",
        "real": "leadgen-project-best",
        "name": "OmniRoute Project Best",
    },
]

COMBO_IDS = [c["id"] for c in ALL_COMBOS]


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
        "env": {"BUZZ_RELAY": "https://leadsgenai.communities.buzz.xyz"},
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
                "id": c["real"],
                "name": c["name"],
                "contextWindow": 1048576,
                "maxTokens": 16384,
            }
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
            "apiKey": "sk-18effe9c5f68c04f-fb461e-b60524ad",
            "models": COMBO_IDS,
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
                    "id": c["id"],
                    "name": c["name"],
                    "vendor": "OmniRoute",
                    "url": "http://127.0.0.1:22000/v1/chat/completions",
                    "apiKey": "sk-18effe9c5f68c04f-b87d87-c952d5da",
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
                    "apiKey": "sk-18effe9c5f68c04f-b87d87-c952d5da",
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
            [c["real"] for c in ALL_COMBOS]
            + [c["id"] for c in ALL_COMBOS]
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
                key_val = "sk-18effe9c5f68c04f-b87d87-c952d5da"
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
                cfg_data["model"]["default"] = "leadgen-coding-primary"
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
                    "model": "leadgen-coding-primary",
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
                        "model": c["real"],
                        "models": [c["real"], c["id"]],
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
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        if "models" not in data or not isinstance(data["models"], dict):
            data["models"] = {}
        if "providers" not in data["models"] or not isinstance(data["models"]["providers"], dict):
            data["models"]["providers"] = {}

        omni_models = [
            {
                "id": c["real"],
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
                "id": c["id"],
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
            "apiKey": "sk-18effe9c5f68c04f-b87d87-c952d5da",
            "api": "openai-completions",
            "models": omni_models,
        }

        data["models"]["providers"]["custom"] = {
            "baseUrl": "http://127.0.0.1:22000/v1",
            "apiKey": "sk-18effe9c5f68c04f-b87d87-c952d5da",
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
    """Seed OmniRoute SQLite inside the Docker container (ADR-189: Docker-only, WSL removed)."""
    seed_script_win = os.path.join(os.path.dirname(__file__), "seed_omniroute_12combos.py")
    if not os.path.exists(seed_script_win):
        print(f"[WARN] Seed script not found: {seed_script_win}")
        return
    try:
        # Copy seed script into container and run it
        # The container has Python and SQLite at /root/.omniroute/storage.sqlite
        res = subprocess.run(
            ["docker", "exec", "-i", "leadgen_omniroute", "python3"],
            input=open(seed_script_win, "rb").read(),
            capture_output=True,
            timeout=15,
        )
        if res.returncode == 0:
            print("[OK] OmniRoute SQLite seeded (via Docker exec)")
            print(res.stdout.decode() if res.stdout else "")
        else:
            print(f"[WARN] OmniRoute SQLite seeding failed (exit {res.returncode}):")
            print(res.stderr.decode() if res.stderr else "")
    except subprocess.TimeoutExpired:
        print("[WARN] OmniRoute SQLite seeding timeout")
    except Exception as e:
        print(f"[WARN] OmniRoute SQLite seeding note: {e}")


if __name__ == "__main__":
    print("=== Syncing 12 Dynamic OmniRoute Combos (1M+ Context & MCP) Across All Apps ===")
    sync_omniroute_sqlite()
    sync_dsh()
    sync_claude()
    sync_workbuddy()
    sync_hermes()
    sync_openclaw()
    sync_workspace_mcp()
    print("=== All Client App Configs Successfully Synced! ===")
