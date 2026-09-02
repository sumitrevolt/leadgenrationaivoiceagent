#!/usr/bin/env python3
"""Seed all 12 OmniRoute combos directly into the Docker container's SQLite.

Ensures OmniRoute gateway DB has all 12 combo routes registered with priority failover
across 40+ free flagship models (Groq, Gemini, Mistral, Cerebras, NVIDIA NIM, OpenRouter, etc.),
and unlocks all API keys so both local & secondary computers can execute all combos.

ADR-189: Docker-only, WSL removed. Seeds via `docker exec`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone


# Free flagship model pool candidates
COMMON_FREE_MODELS = [
    {
        "id": "c1",
        "kind": "model",
        "model": "groq/llama-3.3-70b-versatile",
        "providerId": "groq",
        "weight": 0,
        "label": "groq-llama33",
    },
    {
        "id": "c2",
        "kind": "model",
        "model": "gemini/gemini-flash-latest",
        "providerId": "gemini",
        "weight": 0,
        "label": "gemini-flash",
    },
    {
        "id": "c3",
        "kind": "model",
        "model": "mistral/mistral-small-latest",
        "providerId": "mistral",
        "weight": 0,
        "label": "mistral-small",
    },
    {
        "id": "c4",
        "kind": "model",
        "model": "cerebras/llama-3.3-70b",
        "providerId": "cerebras",
        "weight": 0,
        "label": "cerebras-llama33",
    },
    {
        "id": "c5",
        "kind": "model",
        "model": "nvidia/meta/llama-3.3-70b-instruct",
        "providerId": "nvidia",
        "weight": 0,
        "label": "nvidia-llama33",
    },
    {
        "id": "c6",
        "kind": "model",
        "model": "sambanova/Meta-Llama-3.3-70B-Instruct",
        "providerId": "sambanova",
        "weight": 0,
        "label": "sambanova-llama33",
    },
    {
        "id": "c7",
        "kind": "model",
        "model": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
        "providerId": "openrouter",
        "weight": 0,
        "label": "openrouter-llama33",
    },
    {
        "id": "c8",
        "kind": "model",
        "model": "antigravity/gemini-2.5-flash",
        "providerId": "antigravity",
        "weight": 0,
        "label": "ag-gemini",
    },
]

COMBOS_DEFINITION = [
    (
        "leadgen-coding-primary",
        "Coding & Logic Primary (hermes-engineer / leadgen-free-first)",
        [
            "leadgen.coding_primary",
            "hermes-engineer",
            "claude-omni-coding-primary",
            "hermes-owner",
        ],
    ),
    (
        "leadgen-coding-fast",
        "Coding Fast Lane (claude-code / rapid syntax)",
        ["leadgen.coding_fast", "claude-code", "claude-omni-coding-fast"],
    ),
    (
        "leadgen-repo-analysis",
        "Repo Architecture Deep Scan (hermes-research)",
        ["leadgen.repo_analysis", "hermes-research", "claude-omni-repo-analysis"],
    ),
    (
        "leadgen-test-generation",
        "Automated Test & QA (hermes-qa / pytest)",
        ["leadgen.test_generation", "hermes-qa", "claude-omni-test-generation"],
    ),
    (
        "leadgen-agent-ops",
        "Agent Workforce Operations (hermes-ops)",
        [
            "leadgen.agent_ops",
            "hermes-ops",
            "claude-omni-agent-ops",
            "hermes-sales",
            "hermes-finance",
        ],
    ),
    (
        "leadgen-swara-live",
        "Voice Realtime Fallback (hermes-voice)",
        ["leadgen.swara_live", "hermes-voice", "claude-omni-swara-live"],
    ),
    (
        "leadgen-marketing-content",
        "Marketing Content & Copywriting (hermes-content)",
        [
            "leadgen.marketing_content",
            "hermes-content",
            "hermes-marketing",
            "claude-omni-marketing-content",
        ],
    ),
    (
        "leadgen-prospect-enrich",
        "Prospecting & Lead Data Enrichment (hermes-prospect)",
        ["leadgen.prospect_enrich", "hermes-prospect", "claude-omni-prospect-enrich"],
    ),
    (
        "leadgen-outreach-email",
        "Outreach Email & Follow-up Drafts (hermes-outreach)",
        ["leadgen.outreach_email", "hermes-outreach", "claude-omni-outreach-email"],
    ),
    (
        "leadgen-seo-keyword",
        "SEO & SEM Keyword Clustering (hermes-seo)",
        ["leadgen.seo_keyword", "hermes-seo", "claude-omni-seo-keyword"],
    ),
    (
        "leadgen-governor-review",
        "Dual Governor Code Review (hermes-governor)",
        ["leadgen.governor_review", "hermes-governor", "claude-omni-governor-review"],
    ),
    (
        "leadgen-project-best",
        "50-Model Master Flagship Combo (hermes-master)",
        ["leadgen.project_best", "hermes-master", "claude-omni-project-best"],
    ),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_database_via_docker() -> None:
    """Build the SQLite seeding SQL and execute it inside the Docker container."""
    timestamp = now_iso()

    # Build all INSERT/UPDATE statements as a single SQL script
    sql_parts = []

    # 1. Unlock all API keys
    sql_parts.append(
        "UPDATE api_keys SET allowed_combos = NULL, allowed_models = NULL WHERE is_active = 1;"
    )

    total_seeded = 0

    for combo_name, desc, aliases in COMBOS_DEFINITION:
        models = [
            {
                "id": f"{combo_name}-m{i + 1}-{m['providerId']}",
                "kind": "model",
                "model": m["model"],
                "providerId": m["providerId"],
                "weight": 0,
                "label": m["label"],
            }
            for i, m in enumerate(COMMON_FREE_MODELS)
        ]

        combo_id = str(uuid.uuid4())
        created_at = timestamp

        # We'll use the same UUID for all aliases of this combo for consistency
        for name_key in [combo_name] + aliases:
            payload = {
                "id": combo_id,
                "name": name_key,
                "description": desc,
                "models": models,
                "strategy": "priority",
                "config": {
                    "maxRetries": 2,
                    "retryDelayMs": 1000,
                    "handoffThreshold": 0.85,
                    "trackMetrics": True,
                },
                "isHidden": False,
                "sortOrder": 1,
                "createdAt": created_at,
                "updatedAt": timestamp,
                "version": 2,
                "isActive": True,
            }

            row_id = str(uuid.uuid4())
            json_str = json.dumps(payload).replace("'", "''")  # escape single quotes for SQL

            sql_parts.append(
                f"""INSERT INTO combos (id, name, data, sort_order, created_at, updated_at)
                   VALUES ('{row_id}', '{name_key}', '{json_str}', 1, '{timestamp}', '{timestamp}')
                   ON CONFLICT(name) DO UPDATE SET
                     data = excluded.data,
                     updated_at = excluded.updated_at;"""
            )
            total_seeded += 1

    full_sql = "\n".join(sql_parts)

    # Execute inside Docker container
    try:
        res = subprocess.run(
            ["docker", "exec", "-i", "leadgen_omniroute", "sqlite3", "/root/.omniroute/storage.sqlite"],
            input=full_sql.encode("utf-8"),
            capture_output=True,
            timeout=15,
        )
        if res.returncode == 0:
            print(f"Seeded {total_seeded} combo keys (primary + agent aliases + dot notation) in Docker container.")
            if res.stdout:
                print(res.stdout.decode())
        else:
            print(f"[FAIL] SQLite seeding failed (exit {res.returncode}):")
            print(res.stderr.decode() if res.stderr else "")
            sys.exit(1)
    except subprocess.TimeoutExpired:
        print("[FAIL] SQLite seeding timeout")
        sys.exit(1)
    except FileNotFoundError:
        print("[FAIL] Docker not found or container 'leadgen_omniroute' not running")
        sys.exit(1)
    except Exception as e:
        print(f"[FAIL] SQLite seeding error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    seed_database_via_docker()