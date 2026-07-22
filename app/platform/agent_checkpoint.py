"""
Durable State & Turn Checkpoint (M5) — Turn State Snapshot & Resumption.
========================================================================

WHY (2026-07-22, Agent Harness Engineering Standard M5):
Provides turn-by-turn state persistence for agent runs, enabling exact state
resumption on worker restart and replayable turn debugging.

Import-safe; zero side-effects on import.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CHECKPOINT_DIR = os.path.join("data", "agent_checkpoints")


def _ensure_dir() -> None:
    os.makedirs(_CHECKPOINT_DIR, exist_ok=True)


def save_checkpoint(task_id: str, turn_index: int, state_data: dict[str, Any]) -> str | None:
    """Save an atomic checkpoint file for task_id at turn_index."""
    try:
        _ensure_dir()
        filename = f"{task_id}_turn_{turn_index:03d}.json"
        filepath = os.path.join(_CHECKPOINT_DIR, filename)

        checkpoint_payload = {
            "task_id": task_id,
            "turn_index": turn_index,
            "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
            "state_data": state_data,
        }

        temp_path = filepath + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint_payload, f, indent=2)
        os.replace(temp_path, filepath)

        logger.debug("[agent_checkpoint] Saved checkpoint for %s turn %d", task_id, turn_index)
        return filepath
    except Exception as e:
        logger.warning("[agent_checkpoint] Failed to save checkpoint for %s turn %d: %s", task_id, turn_index, e)
        return None


def load_latest_checkpoint(task_id: str) -> dict[str, Any] | None:
    """Find and return the latest checkpoint data for task_id."""
    try:
        if not os.path.exists(_CHECKPOINT_DIR):
            return None

        matching_files = [
            f for f in os.listdir(_CHECKPOINT_DIR)
            if f.startswith(f"{task_id}_turn_") and f.endswith(".json")
        ]
        if not matching_files:
            return None

        matching_files.sort()
        latest_file = os.path.join(_CHECKPOINT_DIR, matching_files[-1])

        with open(latest_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("[agent_checkpoint] Failed to load latest checkpoint for %s: %s", task_id, e)
        return None
