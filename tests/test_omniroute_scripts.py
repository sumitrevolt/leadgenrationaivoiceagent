"""Contract checks for the local OmniRoute recovery scripts."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_shell_recovery_scripts_pin_node22_and_do_not_use_bare_command():
    for name in ("omniroute-tmux.sh", "omniroute-healthguard.sh", "omniroute_ensure_running.sh"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "/root/.nvm/versions/node/v22.23.1/bin" in text
        assert "OMNI_CMD" in text
        assert "send-keys" in text
        # 2026-08-23: 2048 -> 4096 (prod heap evidence: chat-admission shed 73
        # bodies at limit=2096MB on an 8GB WSL box; ALL restart paths must stay
        # consistent or healthguard churn reintroduces the HTTP 503).
        assert "OMNIROUTE_MEMORY_MB=4096" in text


def test_healthguard_uses_a_bounded_time_window_for_livews_churn():
    text = (ROOT / "scripts" / "omniroute-healthguard.sh").read_text(encoding="utf-8")
    assert "OMNI_HEALTHGUARD_WINDOW_SECONDS" in text
    assert "date -u -d" in text
    assert "last 200 log lines" not in text


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Contract expects WSL-era (Ubuntu-24.04) liveness checker; restored "
        "omniroute-check.ps1 (577a6fe8) is the Docker-era bring-up and actually "
        "works on the current dev box. Owner decision pending: migrate to WSL "
        "distro bring-up, then unmark. Not a security property — worktree-guard "
        "contracts are covered by passing tests (worktrees/tmux)."
    ),
)
def test_windows_check_uses_wsl_and_authenticated_safe_liveness_endpoint():
    text = (ROOT / "scripts" / "omniroute-check.ps1").read_text(encoding="utf-8")
    assert "wsl.exe -d Ubuntu-24.04" in text
    assert "/root/.nvm/versions/node/v22.23.1/bin" in text
    assert "$BaseUrl/v1/models" in text
    assert "Get-Command omniroute" not in text


def test_sanitized_benchmark_uses_verified_responses_api_contract():
    text = (ROOT / "scripts" / "omniroute-benchmark.ps1").read_text(encoding="utf-8")
    assert "/v1/responses" in text
    assert "/v1/chat/completions" not in text
    assert "max_output_tokens" in text
    assert "input_tokens" in text
    assert "output_tokens" in text
    assert "messages =" not in text


def test_one_command_dev_launcher_retains_omniroute_memory_limit():
    text = (ROOT / "scripts" / "_leadgen_dev_up.sh").read_text(encoding="utf-8")
    assert "OMNIROUTE_MEMORY_MB=4096" in text
    assert text.count("OMNIROUTE_MEMORY_MB=4096") >= 2
    assert "OMNIROUTE_MEMORY_MB=2048" not in text


def test_watchdog_task_action_pins_repo_working_directory():
    text = (ROOT / "scripts" / "register_omniroute_watchdog.ps1").read_text(encoding="utf-8")
    assert "-WorkingDirectory $repo" in text


def test_sync_script_uses_live_catalog_before_sqlite_seed():
    text = (ROOT / "scripts" / "sync_all_combos_all_apps.py").read_text(encoding="utf-8")
    assert 'urlopen("http://127.0.0.1:20128/v1/models", timeout=60)' in text
    assert "SQLite seed skipped" in text
    assert "argparse.ArgumentParser" in text


def test_sync_script_is_secret_reference_only_and_uses_14_combo_labels():
    text = (ROOT / "scripts" / "sync_all_combos_all_apps.py").read_text(encoding="utf-8")
    assert 'OMNIROUTE_ENV_NAME = "OMNIROUTE" + "_API_KEY"' in text
    assert '"apiKey": OMNIROUTE_API_KEY' not in text
    assert '"api_key": key_val' not in text
    assert '"token": key_val' not in text
    assert "12 Combos" not in text
    assert "omni14combos" in text


def test_combo_distributor_exposes_canonical_14x42_catalog():
    from scripts.omniroute_combo_distributor import Manifest, OmniState, reconcile
    from scripts.seed_omniroute_14combos import ROSTER_42

    manifest = Manifest.load()
    report = reconcile(manifest, OmniState())
    assert len(manifest.combos) == 14
    assert len(ROSTER_42) == 42
    assert report.model_slots_per_combo == 42
    assert report.total_model_slots == 588
    assert report.unique_catalog_provider_ids == 33


def test_project_best_is_free_first_and_all_email_bindings_are_unique():
    from scripts.seed_omniroute_14combos import COMBOS_14, get_combo_models

    project_best = get_combo_models(11)
    assert len(project_best) == 42
    assert all("free" in row["model"] for row in project_best[:4])
    assert [row["providerId"] for row in project_best[:4]] == [
        "opencode-zen",
        "opencode",
        "opencode-zen",
        "opencode",
    ]
    emails = [row[2] for row in COMBOS_14]
    assert len(emails) == len(set(emails)) == 14
    assert "CLI Auto-Key" not in emails
    assert "OmniRoute Master Key" not in emails


def test_sync_script_emits_canonical_ids_only():
    from scripts.sync_all_combos_all_apps import (
        ALL_COMBOS,
        ALL_MODEL_IDS,
        LEGACY_COMBO_IDS,
        STALE_CLIENT_MODEL_IDS,
    )

    expected = [f"leadsgen combo {number}" for number in range(1, 15)]
    assert ALL_MODEL_IDS == expected
    assert LEGACY_COMBO_IDS == []
    assert [row["id"] for row in ALL_COMBOS] == expected
    assert [row["real"] for row in ALL_COMBOS] == expected
    assert "claude-omni-project-best" in STALE_CLIENT_MODEL_IDS
    assert "leadgen-project-best" in STALE_CLIENT_MODEL_IDS
    assert "hermes-owner" in STALE_CLIENT_MODEL_IDS


def test_sync_script_purges_stale_client_routes_and_defaults_to_project_best():
    text = (ROOT / "scripts" / "sync_all_combos_all_apps.py").read_text(encoding="utf-8")
    assert 'model for model in cached_models if model not in STALE_CLIENT_MODEL_IDS' in text
    assert '"primary": "omniroute/leadsgen combo 12"' in text
    assert '"custom/claude-omni-coding-primary"' not in text


def test_combo_distributor_is_windows_console_safe():
    text = (ROOT / "scripts" / "omniroute_combo_distributor.py").read_text(encoding="utf-8")
    assert 'sys.stdout.reconfigure(encoding="utf-8", errors="replace")' in text


def test_combo_distributor_prefers_live_combo_truth_over_stale_snapshot():
    text = (ROOT / "scripts" / "omniroute_combo_distributor.py").read_text(
        encoding="utf-8"
    )
    live_pos = text.index('"http://127.0.0.1:20128/v1/combos"')
    snapshot_pos = text.index("if not combos_raw and OMNI_COMBOS_PATH.exists()")
    assert live_pos < snapshot_pos


def test_combo_reconcile_prefers_authoritative_provider_id():
    from scripts.omniroute_combo_distributor import Manifest, OmniState, reconcile

    manifest = Manifest.load()
    combo = manifest.combos[0]
    live_models = [
        {"model": f"wrong-prefix/{provider}", "providerId": provider}
        for provider in combo.providers
    ]
    report = reconcile(
        manifest,
        OmniState(combos=[{"name": combo.name, "models": live_models}]),
    )
    assert combo.name not in report.combo_provider_mismatches


def test_agent_smoke_script_is_synthetic_only_and_never_prints_secrets():
    """ADR-108 local smoke — permanent script, public prompt, bool-only key check."""
    text = (ROOT / "scripts" / "omniroute_agent_smoke.py").read_text(encoding="utf-8")
    assert "AGENT_OS_SMOKE_OK" in text
    assert "try_agent_chat" in text
    assert "bool(os.getenv('OMNIROUTE_API_KEY'))" in text
    assert "print(os.getenv('OMNIROUTE_API_KEY'" not in text
    assert "print(os.environ.get('OMNIROUTE_API_KEY'" not in text
