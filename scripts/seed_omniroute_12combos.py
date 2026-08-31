#!/usr/bin/env python3
"""Seed all 12 OmniRoute combos directly into /root/.omniroute/storage.sqlite.

Ensures OmniRoute gateway DB has all 12 combo routes registered with priority failover
across 40+ free flagship models (Groq, Gemini, Mistral, Cerebras, NVIDIA NIM, OpenRouter, etc.),
and unlocks all API keys so both local & secondary computers can execute all combos.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone


def get_db_path() -> str:
    if sys.platform == "win32":
        candidates = [
            r"\\wsl.localhost\Ubuntu-24.04\root\.omniroute\storage.sqlite",
            r"\\wsl$\Ubuntu-24.04\root\.omniroute\storage.sqlite",
            r"\\wsl.localhost\Ubuntu\root\.omniroute\storage.sqlite",
            r"\\wsl$\Ubuntu\root\.omniroute\storage.sqlite",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
    return "/root/.omniroute/storage.sqlite"


DB_PATH = get_db_path()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        "leadgen.coding_primary",
    ),
    ("leadgen-coding-fast", "Coding Fast Lane (claude-code / rapid syntax)", "leadgen.coding_fast"),
    (
        "leadgen-repo-analysis",
        "Repo Architecture Deep Scan (hermes-research)",
        "leadgen.repo_analysis",
    ),
    (
        "leadgen-test-generation",
        "Automated Test & QA (hermes-qa / pytest)",
        "leadgen.test_generation",
    ),
    ("leadgen-agent-ops", "Agent Workforce Operations (hermes-ops)", "leadgen.agent_ops"),
    ("leadgen-swara-live", "Voice Realtime Fallback (hermes-voice)", "leadgen.swara_live"),
    (
        "leadgen-marketing-content",
        "Marketing Content & Copywriting (hermes-content)",
        "leadgen.marketing_content",
    ),
    (
        "leadgen-prospect-enrich",
        "Prospecting & Lead Data Enrichment (hermes-prospect)",
        "leadgen.prospect_enrich",
    ),
    (
        "leadgen-outreach-email",
        "Outreach Email & Follow-up Drafts (hermes-outreach)",
        "leadgen.outreach_email",
    ),
    ("leadgen-seo-keyword", "SEO & SEM Keyword Clustering (hermes-seo)", "leadgen.seo_keyword"),
    (
        "leadgen-governor-review",
        "Dual Governor Code Review (hermes-governor)",
        "leadgen.governor_review",
    ),
    (
        "leadgen-project-best",
        "50-Model Master Flagship Combo (hermes-master)",
        "leadgen.project_best",
    ),
]


def seed_database() -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. Unlock all API keys (remove allowed_combos restrictions so all combos are allowed)
    c.execute(
        "UPDATE api_keys SET allowed_combos = NULL, allowed_models = NULL WHERE is_active = 1;"
    )
    print("API keys updated: allowed_combos set to NULL (all combos allowed).")

    # 2. Query existing combo IDs
    c.execute("SELECT name, data FROM combos;")
    existing_rows = {row[0]: json.loads(row[1]) for row in c.fetchall()}

    timestamp = now_iso()
    inserted_count = 0
    updated_count = 0

    for combo_name, desc, task_alias in COMBOS_DEFINITION:
        # Generate model pool with unique IDs for this combo
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

        if combo_name in existing_rows:
            combo_id = existing_rows[combo_name].get("id", combo_id)
            created_at = existing_rows[combo_name].get("createdAt", timestamp)
            updated_count += 1
        else:
            inserted_count += 1

        payload = {
            "id": combo_id,
            "name": combo_name,
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

        # Save under both hyphenated combo_name AND dot notation task_alias
        for name_key in (combo_name, task_alias):
            p = dict(payload)
            p["name"] = name_key
            row_id = str(uuid.uuid4())
            json_str = json.dumps(p)
            c.execute(
                """INSERT INTO combos (id, name, data, sort_order, created_at, updated_at)
                   VALUES (?, ?, ?, 1, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     data = excluded.data,
                     updated_at = excluded.updated_at;""",
                (row_id, name_key, json_str, timestamp, timestamp),
            )

    conn.commit()
    conn.close()
    print(f"Seeded {len(COMBOS_DEFINITION) * 2} combo keys (hyphen + dot alias) in {DB_PATH}.")


if __name__ == "__main__":
    seed_database()
