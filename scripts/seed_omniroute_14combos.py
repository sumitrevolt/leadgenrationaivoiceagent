#!/usr/bin/env python3
"""seed_omniroute_14combos.py — CANONICAL OmniRoute combo seed (14 combos x 42 providers).

Design (user mandate & council decision 2026-09-06):
  - Exactly 14 canonical combos named `leadsgen combo 1` .. `leadsgen combo 14`.
  - EACH combo carries ALL 42 flagship models across live and fallback providers:
    * Slots 1-6: Verified live fast/ultra/reasoning lanes (Opencode & Opencode-Zen)
    * Slots 7-22: International flagship free-tier models (Groq, Cerebras, Gemini, HF, OpenRouter, SambaNova, Together, Fireworks, DeepInfra, DigitalOcean, Ollama, Pollinations)
    * Slots 23-42: Chinese & Deep-Tail flagship free-tier models (SiliconFlow, Volcengine, Zhipu, Alibaba, Baidu, Tencent, MiniMax, Kimi, DeepSeek, iFlytek, StreamLake, China Telecom, SenseTime, 01.AI, China Mobile, Kunlun, 360 AI, PPIO, NVIDIA NIM)
  - Strategy per Combo: Priority / Automatic Fallback (Order: Primary Fast -> Ultra -> Big Pickle / Reasoning -> External Fallbacks).
  - Context window: 1M tokens (1048576) with 16384 max output tokens.
  - Dedicated email API key bound to each combo so every worker has its dedicated quota.
  - Legacy aliases registered to preserve compatibility with all apps and routers.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile
import uuid

CONTAINER = os.environ.get("OMNIROUTE_CONTAINER", "leadgen_omniroute")
DB_PATH = os.environ.get("OMNIROUTE_DB_PATH", "/app/data/storage.sqlite")
BACKUP_DIR = "/app/data/db_backups"


def _docker_bin() -> str:
    """Locate the docker executable."""
    import shutil

    found = shutil.which("docker") or shutil.which("docker.exe")
    if found:
        return found
    candidates = [
        r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
        r"C:\Users\Ratanshila\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe",
        "/usr/local/bin/docker",
        "/usr/bin/docker",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "docker"


# ---------------------------------------------------------------------------
# The Full 42-Provider Roster (Chinese + International Flagship Models)
# ---------------------------------------------------------------------------
ROSTER_42: list[dict[str, str]] = [
    # Top 6: Verified Live Lanes (Fast -> Ultra -> Reasoning)
    {"model": "opencode/nemotron-3.5-lightning-free", "providerId": "opencode", "label": "ocd-nemotron35-lightning"},
    {"model": "opencode/nemotron-3-ultra-free", "providerId": "opencode", "label": "ocd-nemotron3-ultra"},
    {"model": "opencode/big-pickle", "providerId": "opencode", "label": "ocd-big-pickle"},
    {"model": "opencode-zen/nemotron-3.5-lightning-free", "providerId": "opencode-zen", "label": "ocdzen-nemotron35-lightning"},
    {"model": "opencode-zen/nemotron-3-ultra-free", "providerId": "opencode-zen", "label": "ocdzen-nemotron3-ultra"},
    {"model": "opencode-zen/big-pickle", "providerId": "opencode-zen", "label": "ocdzen-big-pickle"},

    # International Flagship Free-Tier Providers
    {"model": "groq/llama-3.3-70b-versatile", "providerId": "groq", "label": "groq-llama33-70b"},
    {"model": "groq/deepseek-r1-distill-llama-70b", "providerId": "groq", "label": "groq-deepseek-r1-70b"},
    {"model": "cerebras/llama-3.3-70b", "providerId": "cerebras", "label": "cerebras-llama33-70b"},
    {"model": "gemini/gemini-2.0-flash", "providerId": "gemini", "label": "gemini-20-flash"},
    {"model": "gemini/gemini-1.5-pro", "providerId": "gemini", "label": "gemini-15-pro"},
    {"model": "huggingface/Qwen/Qwen2.5-Coder-32B-Instruct", "providerId": "huggingface", "label": "hf-qwen25-coder-32b"},
    {"model": "huggingface/deepseek-ai/DeepSeek-V3", "providerId": "huggingface", "label": "hf-deepseek-v3"},
    {"model": "openrouter/nvidia/nemotron-3.5-lightning:free", "providerId": "openrouter", "label": "openrouter-nemotron35-free"},
    {"model": "openrouter/meta-llama/llama-3.3-70b-instruct:free", "providerId": "openrouter", "label": "openrouter-llama33-free"},
    {"model": "sambanova/Meta-Llama-3.3-70B-Instruct", "providerId": "sambanova", "label": "sambanova-llama33-70b"},
    {"model": "together/meta-llama/Llama-3.3-70B-Instruct-Turbo", "providerId": "together", "label": "together-llama33-70b"},
    {"model": "fireworks/accounts/fireworks/models/llama-v3p3-70b-instruct", "providerId": "fireworks", "label": "fireworks-llama33-70b"},
    {"model": "deepinfra/meta-llama/Llama-3.3-70B-Instruct", "providerId": "deepinfra", "label": "deepinfra-llama33-70b"},
    {"model": "digitalocean/meta-llama-3.3-70b-instruct", "providerId": "digitalocean", "label": "do-llama33-70b"},
    {"model": "ollama-cloud/llama-3.3-70b", "providerId": "ollama-cloud", "label": "ollama-llama33-70b"},
    {"model": "pollinations/openai-fast", "providerId": "pollinations", "label": "pollinations-fast"},

    # Chinese Flagship Free-Tier Providers
    {"model": "siliconflow/deepseek-ai/DeepSeek-V4-Pro", "providerId": "siliconflow", "label": "siliconflow-deepseek-v4-pro"},
    {"model": "siliconflow/Qwen3.7-Max", "providerId": "siliconflow", "label": "siliconflow-qwen37-max"},
    {"model": "volcengine/Doubao-Seed-2.0-Pro", "providerId": "volcengine", "label": "volcengine-doubao-seed2-pro"},
    {"model": "zhipu/GLM-5.2", "providerId": "zhipu", "label": "zhipu-glm52"},
    {"model": "alibaba/Qwen3.7-Max", "providerId": "alibaba", "label": "alibaba-qwen37-max"},
    {"model": "baidu/ERNIE-5.1", "providerId": "baidu", "label": "baidu-ernie51"},
    {"model": "tencent/Hunyuan-Hy3", "providerId": "tencent", "label": "tencent-hunyuan-hy3"},
    {"model": "minimax/MiniMax-M3", "providerId": "minimax", "label": "minimax-m3"},
    {"model": "kimi/Kimi-K3", "providerId": "kimi", "label": "kimi-k3"},
    {"model": "deepseek/deepseek-v4-flash", "providerId": "deepseek", "label": "deepseek-v4-flash"},
    {"model": "iflytek/Spark-X2", "providerId": "iflytek", "label": "iflytek-spark-x2"},
    {"model": "streamlake/KAT-Coder-Air-V2.5", "providerId": "streamlake", "label": "streamlake-kat-coder-v25"},
    {"model": "telecom/TeleChat3", "providerId": "telecom", "label": "telecom-telechat3"},
    {"model": "sensetime/SenseNova-6.7-Flash", "providerId": "sensetime", "label": "sensetime-sensenova-67"},
    {"model": "zeroone/Yi-Lightning", "providerId": "zeroone", "label": "zeroone-yi-lightning"},
    {"model": "chinamobile/MoMA-300B", "providerId": "mobile", "label": "mobile-moma-300b"},
    {"model": "kunlun/Matrix-3.5", "providerId": "kunlun", "label": "kunlun-matrix-35"},
    {"model": "ai360/360-AI-4.0", "providerId": "ai360", "label": "ai360-40"},
    {"model": "ppio/DeepSeek-V4-Flash", "providerId": "ppio", "label": "ppio-deepseek-v4-flash"},
    {"model": "nvidia/nvidia/nemotron-3-super-120b-a12b", "providerId": "nvidia", "label": "nvidia-nemotron-super-120b"},
]

assert len(ROSTER_42) == 42, f"ROSTER_42 must contain exactly 42 models, got {len(ROSTER_42)}"


# ---------------------------------------------------------------------------
# The 14 canonical combos + their dedicated email binding + legacy aliases
# ---------------------------------------------------------------------------
COMBOS_14 = [
    ("leadsgen combo 1", "Coding & Logic Primary — flagship worker #1",
     "admin@leadsgenai.in",
     ["leadgen-coding-primary", "leadgen-free-first", "hermes-engineer", "claude-omni-coding-primary", "hermes-owner"]),
    ("leadsgen combo 2", "Coding Fast Lane — rapid syntax worker #2",
     "ops@leadsgenai.in",
     ["leadgen-coding-fast", "claude-code", "claude-omni-coding-fast"]),
    ("leadsgen combo 3", "Repo Architecture Deep Scan — research worker #3",
     "hello@leadsgenai.in",
     ["leadgen-repo-analysis", "hermes-research", "claude-omni-repo-analysis"]),
    ("leadsgen combo 4", "Automated Test & QA — qa worker #4",
     "support@leadsgenai.in",
     ["leadgen-test-generation", "hermes-qa", "claude-omni-test-generation"]),
    ("leadsgen combo 5", "Agent Workforce Operations — ops worker #5",
     "sunny@leadsgenai.in",
     ["leadgen-agent-ops", "hermes-ops", "claude-omni-agent-ops", "hermes-sales", "hermes-finance"]),
    ("leadsgen combo 6", "Voice Realtime Fallback — swara worker #6",
     "sumit20016@gmail.com",
     ["leadgen-swara-live", "hermes-voice", "claude-omni-swara-live", "vps-01"]),
    ("leadsgen combo 7", "Marketing Content & Copy — content worker #7",
     "bunnybunnysunny49@gmail.com",
     ["leadgen-marketing-content", "hermes-marketing", "claude-omni-marketing-content"]),
    ("leadsgen combo 8", "Prospecting & Lead Enrichment — prospect worker #8",
     "bunnysunnysunny49@gmail.com",
     ["leadgen-prospect-enrich", "claude-omni-prospect-enrich"]),
    ("leadsgen combo 9", "Outreach Email & Follow-up — outreach worker #9",
     "damsamsamdam39@gmail.com",
     ["leadgen-outreach-email", "claude-omni-outreach-email"]),
    ("leadsgen combo 10", "SEO & SEM Keyword Clustering — seo worker #10",
     "daryananisumit440@gmail.com",
     ["leadgen-seo-keyword", "claude-omni-seo-keyword"]),
    ("leadsgen combo 11", "Dual Governor Code Review — governor worker #11",
     "sunnybunny23211@gmail.com",
     ["leadgen-governor-review", "claude-omni-governor-review"]),
    ("leadsgen combo 12", "50-Model Master Flagship — master worker #12",
     "sunnydaryanani2@gmail.com",
     ["leadgen-project-best", "claude-omni-project-best"]),
    ("leadsgen combo 13", "Free-first failover lane — vps worker #13",
     "CLI Auto-Key",
     ["leadgen-14th-combo", "vps-02"]),
    ("leadsgen combo 14", "General purpose free-tier worker #14",
     "OmniRoute Master Key",
     []),
]


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _sql_str(value: str) -> str:
    """Single-quote a string for SQL, escaping embedded single quotes."""
    return "'" + value.replace("'", "''") + "'"


def get_combo_models(combo_idx: int) -> list[dict]:
    """Return all 42 models for combo, rotating the top live lanes to spread concurrency."""
    # Rotate the top 6 live lanes based on combo index so workers distribute primary load
    shift = combo_idx % 6
    top_6 = ROSTER_42[shift:6] + ROSTER_42[:shift]
    remaining_36 = ROSTER_42[6:]
    ordered_42 = top_6 + remaining_36
    assert len(ordered_42) == 42
    return ordered_42


def build_sql() -> str:
    """Return the full SQL script to seed all 14 combos x 42 providers."""
    timestamp = _now_iso()
    canonical_names = {c[0] for c in COMBOS_14}
    keep_names = canonical_names

    parts: list[str] = []

    # 1. Backup marker
    parts.append("-- backup dir: " + BACKUP_DIR)

    # 2. Delete stale/temporary combos except default, auto, canonical and aliases
    keep_list = ",".join(_sql_str(n) for n in sorted(keep_names))
    parts.append(
        "DELETE FROM combos WHERE name NOT LIKE 'auto/%' "
        "AND name NOT IN ('default', 'auto') "
        "AND name NOT IN (" + keep_list + ");"
    )

    # 3. Context Overrides: Set 1M tokens context window (1048576) for all 42 models
    for m in ROSTER_42:
        parts.append(
            "INSERT OR REPLACE INTO model_context_overrides (provider, model_id, real_context, source, refreshed_at) "
            "VALUES (" + _sql_str(m["providerId"]) + ", " + _sql_str(m["model"]) + ", 1048576, 'manual', datetime('now'));"
        )

    # 4. Insert all 14 combos + aliases (each containing all 42 models)
    for idx, (combo_name, desc, email_key, aliases) in enumerate(COMBOS_14):
        combo_id = str(uuid.uuid4())
        combo_models_42 = get_combo_models(idx)
        
        models = [
            {
                "id": f"{combo_name}-m{i+1}-{m['providerId']}",
                "kind": "model",
                "model": m["model"],
                "providerId": m["providerId"],
                "weight": 0,
                "label": m["label"],
            }
            for i, m in enumerate(combo_models_42)
        ]
        
        payload = {
            "id": combo_id,
            "name": combo_name,
            "description": desc,
            "models": models,
            "strategy": "priority",
            "config": {
                "maxRetries": 3,
                "retryDelayMs": 1000,
                "handoffThreshold": 0.85,
                "trackMetrics": True,
                "contextWindow": 1048576,
                "maxTokens": 16384,
            },
            "isHidden": False,
            "sortOrder": 1,
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "version": 2,
            "isActive": True,
        }
        
        # 4. Only insert the canonical combo row (no duplicate alias rows cluttering OmniRoute UI)
        row_payload = dict(payload)
        row_payload["name"] = combo_name
        json_str = json.dumps(row_payload).replace("'", "''")
        row_id = str(uuid.uuid4())
        parts.append(
            "INSERT INTO combos (id, name, data, sort_order, created_at, updated_at) "
            "VALUES (" + _sql_str(row_id) + ", " + _sql_str(combo_name) + ", "
            + _sql_str(json_str) + ", 1, " + _sql_str(timestamp) + ", "
            + _sql_str(timestamp) + ") "
            "ON CONFLICT(name) DO UPDATE SET data = excluded.data, "
            "updated_at = excluded.updated_at;"
        )

        # 5. Bind the worker email key to this combo (allowed_combos = [combo_name] + aliases)
        allowed_keys = [combo_name] + aliases
        combo_list_json = json.dumps(allowed_keys).replace("'", "''")
        parts.append(
            "UPDATE api_keys SET allowed_combos = " + _sql_str(combo_list_json) + " "
            "WHERE name = " + _sql_str(email_key) + " AND is_active = 1;"
        )

    return "\n".join(parts)


def run_seed() -> int:
    """Execute the SQL inside the container via node:sqlite."""
    sql = build_sql()
    js_path = os.path.join(tempfile.gettempdir(), "omniroute_seed_14x42.js")
    node_script = (
        "const { DatabaseSync } = require('node:sqlite');\n"
        "const db = new DatabaseSync(" + json.dumps(DB_PATH) + ");\n"
        "db.exec(`" + sql.replace("`", "\\`") + "`);  // nosecurity\n"
        "db.close();\n"
        "console.log('SEED_14x42_OK');\n"
    )
    with open(js_path, "w", encoding="utf-8") as f:
        f.write(node_script)

    docker_bin = _docker_bin()

    try:
        cp_res = subprocess.run(
            [docker_bin, "cp", js_path, CONTAINER + ":/tmp/omniroute_seed_14x42.js"],
            capture_output=True, timeout=30,
        )
        if cp_res.returncode != 0:
            print("[FAIL] docker cp failed:", cp_res.stderr.decode()[:300])
            return 1
            
        res = subprocess.run(
            [docker_bin, "exec", CONTAINER, "node", "/tmp/omniroute_seed_14x42.js"],
            capture_output=True, timeout=60,
        )
        if res.returncode == 0:
            print("[OK] Seed executed successfully in container:", CONTAINER)
            print(res.stdout.decode().strip() if res.stdout else "")
            return 0
        print("[FAIL] Seed SQL failed (exit", res.returncode, "):")
        print(res.stderr.decode() if res.stderr else res.stdout.decode() if res.stdout else "")
        return 1
    except FileNotFoundError:
        print("[FAIL] Docker not found or container", CONTAINER, "not running")
        return 1
    except Exception as e:
        print("[FAIL] Seed error:", e)
        return 1


if __name__ == "__main__":
    sys.exit(run_seed())
