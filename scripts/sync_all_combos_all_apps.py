import json
import os
import sqlite3
import subprocess
import yaml

# Exactly 12 clean, unique OmniRoute dynamic combos with claude-omni- IDs for Claude Desktop frontend filter
ALL_COMBOS = [
    {"id": "claude-omni-coding-primary", "real": "leadgen-coding-primary", "name": "OmniRoute Coding Primary"},
    {"id": "claude-omni-coding-fast", "real": "leadgen-coding-fast", "name": "OmniRoute Coding Fast"},
    {"id": "claude-omni-repo-analysis", "real": "leadgen-repo-analysis", "name": "OmniRoute Repo Analysis"},
    {"id": "claude-omni-test-generation", "real": "leadgen-test-generation", "name": "OmniRoute Test Generation"},
    {"id": "claude-omni-agent-ops", "real": "leadgen-agent-ops", "name": "OmniRoute Agent Ops"},
    {"id": "claude-omni-swara-live", "real": "leadgen-swara-live", "name": "OmniRoute Swara Live"},
    {"id": "claude-omni-marketing-content", "real": "leadgen-marketing-content", "name": "OmniRoute Marketing Content"},
    {"id": "claude-omni-prospect-enrich", "real": "leadgen-prospect-enrich", "name": "OmniRoute Prospect Enrich"},
    {"id": "claude-omni-outreach-email", "real": "leadgen-outreach-email", "name": "OmniRoute Outreach Email"},
    {"id": "claude-omni-seo-keyword", "real": "leadgen-seo-keyword", "name": "OmniRoute SEO Keyword"},
    {"id": "claude-omni-governor-review", "real": "leadgen-governor-review", "name": "OmniRoute Governor Review"},
    {"id": "claude-omni-project-best", "real": "leadgen-project-best", "name": "OmniRoute Project Best"},
]

COMBO_IDS = [c["id"] for c in ALL_COMBOS]

def sync_dsh():
    dsh_yaml_path = os.path.expanduser(r"~\.dsh\settings.yaml")
    if os.path.exists(dsh_yaml_path):
        with open(dsh_yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        if "llm-pi-ai" not in data:
            data["llm-pi-ai"] = {}
        if "providers" not in data["llm-pi-ai"]:
            data["llm-pi-ai"]["providers"] = {}
        
        models_list = [{"id": c["real"], "name": c["name"]} for c in ALL_COMBOS]
        data["llm-pi-ai"]["providers"]["omniroute"] = {
            "displayName": "OmniRoute (12 Combos)",
            "api": "openai-completions",
            "baseURL": "http://127.0.0.1:20128/v1",
            "apiKeyEnv": "OMNIROUTE_API_KEY",
            "models": models_list
        }
        
        with open(dsh_yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        print(f"[OK] DSH settings synced ({len(models_list)} unique combos) -> {dsh_yaml_path}")

def sync_claude():
    claude_settings_path = os.path.expanduser(r"~\AppData\Roaming\Claude\settings.json")
    if os.path.exists(os.path.dirname(claude_settings_path)):
        if os.path.exists(claude_settings_path):
            with open(claude_settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
        
        if "inferenceGateway" not in data:
            data["inferenceGateway"] = {}
        
        data["inferenceGateway"]["url"] = "http://127.0.0.1:22000"
        data["inferenceGateway"]["apiKey"] = "sk-18effe9c5f68c04f-fb461e-b60524ad"
        data["inferenceGateway"]["models"] = COMBO_IDS
        
        with open(claude_settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[OK] Claude Desktop settings synced ({len(COMBO_IDS)} claude-omni- combos) -> {claude_settings_path}")

def sync_workbuddy():
    wb_settings_path = os.path.expanduser(r"~\.workbuddy-ai\settings.json")
    if os.path.exists(os.path.dirname(wb_settings_path)):
        if os.path.exists(wb_settings_path):
            with open(wb_settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
        
        data["omniroute"] = {
            "baseURL": "http://127.0.0.1:22000",
            "apiKey": "sk-18effe9c5f68c04f-fb461e-b60524ad",
            "models": COMBO_IDS
        }
        
        with open(wb_settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[OK] WorkBuddy AI settings synced ({len(COMBO_IDS)} unique combos) -> {wb_settings_path}")

def sync_hermes():
    hermes_dir = os.path.expanduser(r"~\AppData\Roaming\Hermes")
    if os.path.exists(hermes_dir):
        conn_path = os.path.join(hermes_dir, "connections.json")
        conn_data = {
            "version": 2,
            "primary": "omniroute",
            "launchMode": "last-used",
            "lastUsed": "omniroute",
            "connections": [
                {
                    "id": "omniroute",
                    "kind": "custom",
                    "label": "OmniRoute Gateway (12 Combos)",
                    "baseURL": "http://127.0.0.1:22000",
                    "apiKey": "sk-18effe9c5f68c04f-fb461e-b60524ad",
                    "models": COMBO_IDS
                },
                {
                    "id": "local",
                    "kind": "local",
                    "label": "This device"
                }
            ]
        }
        with open(conn_path, "w", encoding="utf-8") as f:
            json.dump(conn_data, f, indent=2)
        print(f"[OK] Hermes Desktop connections synced -> {conn_path}")

def sync_omniroute_sqlite():
    seed_script = os.path.join(os.path.dirname(__file__), "seed_omniroute_12combos.py")
    if os.path.exists(seed_script):
        res = subprocess.run([".venv\\Scripts\\python.exe", seed_script], capture_output=True, text=True)
        print("[OK] OmniRoute SQLite seeding triggered:")
        print(res.stdout)

if __name__ == "__main__":
    print("=== Syncing 12 Dynamic OmniRoute Combos (claude-omni- prefixed) Across All Apps ===")
    sync_omniroute_sqlite()
    sync_dsh()
    sync_claude()
    sync_workbuddy()
    sync_hermes()
    print("=== All Client App Configs Successfully Synced! ===")
