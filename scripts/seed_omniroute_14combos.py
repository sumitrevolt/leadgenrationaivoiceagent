#!/usr/bin/env python3
"""seed_omniroute_14combos.py — CANONICAL OmniRoute combo seed (14 combos).

2026-09-05: replaces the mess — the gateway DB had 67 combos (duplicate
aliases, leftover test combos, model-named entries, stale vps-01/02) and the
old `seed_omniroute_12combos.py` targeted the WRONG DB path
(`/root/.omniroute/storage.sqlite` — the real one is `/app/data/storage.sqlite`),
so its seeds never landed.

Design (council decision 2026-09-05):
  - Exactly 14 canonical combos named `leadsgen combo 1` .. `leadsgen combo 14`.
  - Each combo carries 3 free-tier flagship models = 42 provider slots total.
  - Each combo is bound to ONE email API key (the worker keys) so every
    worker has its own rate-limit/quota identity ("har combo apne worker ko
    power karega").
  - Old names (leadgen-*, hermes-*, claude-code, vps-01, claude-omni-*) are
    registered as ALIASES of the same combo UUID, so `app/platform/
    omniroute_client.py` `_TASK_ROUTES` keeps resolving without app changes.
  - Cleanup: deletes every combo that is NOT default / auto:* / leadsgen combo
    N / its aliases. Backs up the DB first (db_backups/).
  - Idempotent: re-running updates in place (ON CONFLICT name DO UPDATE).

Usage:  python scripts/seed_omniroute_14combos.py
(requires Docker container `leadgen_omniroute` running; uses node:sqlite
inside the container — the container image has node but no sqlite3 binary.)
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
    """Locate the docker executable (Python subprocess PATH may differ from shell)."""
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
# The 42 free model slots (3 per combo).
#
# 2026-09-05 LIVE-CATALOG AUDIT (2nd pass, same day): the gateway's /v1/models
# dump lists thousands of models, but routing consults a DIFFERENT per-connection
# live catalog. The only trustworthy signal is an actual HTTP 200 on /v1/responses.
#
# PROBED 2026-09-05 (real requests, not config): NVIDIA (NIM), Ollama Cloud,
# DigitalOcean, Fireworks and OpenRouter connections ALL still fail — every model
# returns upstream 401/400 because their stored keys were rotated upstream (the
# gateway DB's `test_status`/`apiKeyHealth` says active/warning but real inference
# proves the keys dead). There is NO 200 model on those five connections today,
# so the pool is NOT extended with them — seeding dead lanes is the exact failure
# this file exists to prevent. Fix = refresh keys in the gateway dashboard.
#
# What IS live: the opencode ANONYMOUS free tier (account=noauth) is served under
# TWO routable labels — `opencode/*` and `opencode-zen/*` — and BOTH return real
# 200 + output_text on the same free models (verified twice each: nemotron-3.5-
# lightning-free, nemotron-3-ultra-free, big-pickle). Same-day re-probe also found
# the ORIGINAL pool's `muse-spark-1.2-contributor-free` (502) and `laguna-s-2.1-
# free` (401) lanes had since died, and `mimo-v2.5-free` returns 200-with-EMPTY
# output (unusable). So the pool below is the re-verified live set: 3 models x 2
# labels = 6 genuinely-live lanes, every slot answers.
#
# Round-robin distribution gives each combo 3 DISTINCT live lanes (slot 1 = the
# strongest lane) so priority failover actually fires. If the owner later
# refreshes other providers' keys in the gateway dashboard, extend this pool.
# ---------------------------------------------------------------------------
_LIVE = [
    ("opencode/nemotron-3.5-lightning-free", "opencode", "ocd-nemotron35-lightning"),
    ("opencode/nemotron-3-ultra-free", "opencode", "ocd-nemotron3-ultra"),
    ("opencode/big-pickle", "opencode", "ocd-big-pickle"),
    ("opencode-zen/nemotron-3.5-lightning-free", "opencode-zen", "ocdzen-nemotron35-lightning"),
    ("opencode-zen/nemotron-3-ultra-free", "opencode-zen", "ocdzen-nemotron3-ultra"),
    ("opencode-zen/big-pickle", "opencode-zen", "ocdzen-big-pickle"),
]

MODEL_POOL: list[dict] = []
# 42 slots = 14 combos x 3. Combo i starts at lane (i % 6) and takes the next
# 3 lanes (wrap) — so every combo has 3 DISTINCT live lanes AND consecutive
# combos rotate primaries (combo 1 primary = lane0, combo 2 = lane1, ...) which
# spreads concurrent worker traffic across all 6 lanes instead of thundering on
# one. Priority failover therefore always has a live primary + 2 live fallbacks.
for combo_i in range(14):
    start = combo_i % 6
    for j in range(3):
        model, prov, label = _LIVE[(start + j) % 6]
        MODEL_POOL.append({"model": model, "providerId": prov, "label": label})
assert len(MODEL_POOL) == 42, "MODEL_POOL must have 42 entries, got %d" % len(MODEL_POOL)
# Ensure each combo's 3 slots (offset, offset+1, offset+2) are distinct lanes.
for off in range(0, 42, 3):
    labels = [m["label"] for m in MODEL_POOL[off:off + 3]]
    assert len(set(labels)) == 3, "combo at offset %d repeats a lane: %s" % (off, labels)

# ---------------------------------------------------------------------------
# The 14 canonical combos + their email-key binding + legacy aliases
# ---------------------------------------------------------------------------
# (name, description, worker_email_key, [legacy alias names])
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

# Name -> slot offset into MODEL_POOL (3 models per combo, different providers)
_COMBO_MODEL_OFFSET = {
    "leadsgen combo 1": 0, "leadsgen combo 2": 3, "leadsgen combo 3": 6,
    "leadsgen combo 4": 9, "leadsgen combo 5": 12, "leadsgen combo 6": 15,
    "leadsgen combo 7": 18, "leadsgen combo 8": 21, "leadsgen combo 9": 24,
    "leadsgen combo 10": 27, "leadsgen combo 11": 30, "leadsgen combo 12": 33,
    "leadsgen combo 13": 36, "leadsgen combo 14": 39,
}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _sql_str(value: str) -> str:
    """Single-quote a string for SQL, escaping embedded single quotes."""
    return "'" + value.replace("'", "''") + "'"


def build_sql() -> str:
    """Return the full SQL script to run inside the container."""
    timestamp = _now_iso()
    canonical_names = {c[0] for c in COMBOS_14}
    alias_names = {a for c in COMBOS_14 for a in c[3]}
    keep_names = canonical_names | alias_names

    parts: list[str] = []

    # 1. Backup marker
    parts.append("-- backup dir: " + BACKUP_DIR)

    # 2. Delete the mess — everything except default / auto:* / canonical / aliases.
    # NOTE: SQLite treats double-quoted strings as identifiers, so the keep-list
    # MUST use single-quoted SQL literals (apostrophes escaped via _sql_str).
    keep_list = ",".join(_sql_str(n) for n in sorted(keep_names))
    parts.append(
        "DELETE FROM combos WHERE name NOT LIKE 'auto/%' "
        "AND name NOT IN ('default', 'auto') "
        "AND name NOT IN (" + keep_list + ");"
    )

    # 3. Unlock all API keys
    parts.append(
        "UPDATE api_keys SET allowed_combos = NULL, allowed_models = NULL WHERE is_active = 1;"
    )

    # 4. Insert the 14 combos + aliases (same UUID per combo)
    for combo_name, desc, email_key, aliases in COMBOS_14:
        combo_id = str(uuid.uuid4())
        offset = _COMBO_MODEL_OFFSET[combo_name]
        slot_models = MODEL_POOL[offset:offset + 3]
        models = [
            {
                "id": combo_name + "-m" + str(i + 1) + "-" + m["providerId"],
                "kind": "model",
                "model": m["model"],
                "providerId": m["providerId"],
                "weight": 0,
                "label": m["label"],
            }
            for i, m in enumerate(slot_models)
        ]
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
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "version": 2,
            "isActive": True,
        }
        for name_key in [combo_name] + aliases:
            row_payload = dict(payload)
            row_payload["name"] = name_key
            json_str = json.dumps(row_payload).replace("'", "''")
            row_id = str(uuid.uuid4())
            parts.append(
                "INSERT INTO combos (id, name, data, sort_order, created_at, updated_at) "
                "VALUES (" + _sql_str(row_id) + ", " + _sql_str(name_key) + ", "
                + _sql_str(json_str) + ", 1, " + _sql_str(timestamp) + ", "
                + _sql_str(timestamp) + ") "
                "ON CONFLICT(name) DO UPDATE SET data = excluded.data, "
                "updated_at = excluded.updated_at;"
            )

        # 5. Bind the worker email key to this combo (allowed_combos = [combo_name])
        combo_list_json = json.dumps([combo_name]).replace("'", "''")
        parts.append(
            "UPDATE api_keys SET allowed_combos = " + _sql_str(combo_list_json) + " "
            "WHERE name = " + _sql_str(email_key) + " AND is_active = 1;"
        )

    return "\n".join(parts)


def run_seed() -> int:
    """Execute the SQL inside the container via node:sqlite (container has node)."""
    sql = build_sql()
    # The SQL + JS wrapper is ~68KB — exceeds the Windows command-line length
    # limit (32767 chars), so write the script to a temp file and `docker cp` it
    # into the container instead of passing via `node -e`.
    js_path = os.path.join(tempfile.gettempdir(), "omniroute_seed_14.js")
    node_script = (
        "const { DatabaseSync } = require('node:sqlite');\n"
        "const db = new DatabaseSync(" + json.dumps(DB_PATH) + ");\n"
        "db.exec(`" + sql.replace("`", "\\`") + "`);  // nosecurity\n"
        "db.close();\n"
        "console.log('SEED_OK');\n"
    )
    with open(js_path, "w", encoding="utf-8") as f:
        f.write(node_script)

    docker_bin = _docker_bin()
    # Backup first (inside container, cheap file copy)
    try:
        subprocess.run(
            [docker_bin, "exec", CONTAINER, "sh", "-c",
             "mkdir -p " + BACKUP_DIR + " && cp " + DB_PATH + " " + BACKUP_DIR
             + "/pre_14combos_$(date +%Y%m%d_%H%M%S).sqlite"],
            capture_output=True, timeout=30, check=True,
        )
        print("[OK] DB backup written to", BACKUP_DIR)
    except Exception as e:
        print("[WARN] DB backup failed (continuing):", e)

    try:
        cp_res = subprocess.run(
            [docker_bin, "cp", js_path, CONTAINER + ":/tmp/omniroute_seed_14.js"],
            capture_output=True, timeout=30,
        )
        if cp_res.returncode != 0:
            print("[FAIL] docker cp failed:", cp_res.stderr.decode()[:300])
            return 1
        res = subprocess.run(
            [docker_bin, "exec", CONTAINER, "node", "/tmp/omniroute_seed_14.js"],
            capture_output=True, timeout=60,
        )
        if res.returncode == 0:
            print("[OK] Seed executed in container:", CONTAINER)
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
