from __future__ import annotations

from pathlib import Path


def test_dockerignore_excludes_runtime_data_after_data_include() -> None:
    """Runtime/model data must not be baked into Dockerfile.lock app images."""
    lines = Path(".dockerignore").read_text(encoding="utf-8").splitlines()
    include_idx = lines.index("!data/**")
    after_data_include = {
        line.strip().rstrip("/")
        for line in lines[include_idx + 1 :]
        if line.strip() and not line.lstrip().startswith("#")
    }

    required_excludes = {
        "data/ai_images",
        "data/backups",
        "data/call_recordings",
        "data/obsidian_staging",
        "data/ollama",
        "data/u2net",
        "data/vectorstore",
    }
    assert required_excludes <= after_data_include


def test_dockerignore_excludes_vps_runtime_backups_from_build_context() -> None:
    """VPS root backups are multi-GB and must never enter an app image build."""
    lines = {
        line.strip().rstrip("/")
        for line in Path(".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "backups" in lines
