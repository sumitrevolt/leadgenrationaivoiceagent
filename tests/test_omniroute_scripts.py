"""Contract checks for the local OmniRoute recovery scripts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shell_recovery_scripts_pin_node22_and_do_not_use_bare_command():
    for name in ("omniroute-tmux.sh", "omniroute-healthguard.sh", "omniroute_ensure_running.sh"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "/root/.nvm/versions/node/v22.23.1/bin" in text
        assert "OMNI_CMD" in text
        assert "send-keys" in text
        assert "OMNIROUTE_MEMORY_MB=2048" in text


def test_healthguard_uses_a_bounded_time_window_for_livews_churn():
    text = (ROOT / "scripts" / "omniroute-healthguard.sh").read_text(encoding="utf-8")
    assert "OMNI_HEALTHGUARD_WINDOW_SECONDS" in text
    assert "date -u -d" in text
    assert "last 200 log lines" not in text


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
    assert "OMNIROUTE_MEMORY_MB=2048" in text
    assert text.count("OMNIROUTE_MEMORY_MB=2048") >= 2


def test_agent_smoke_script_is_synthetic_only_and_never_prints_secrets():
    """ADR-108 local smoke — permanent script, public prompt, bool-only key check."""
    text = (ROOT / "scripts" / "omniroute_agent_smoke.py").read_text(encoding="utf-8")
    assert "AGENT_OS_SMOKE_OK" in text
    assert "try_agent_chat" in text
    assert "bool(os.getenv('OMNIROUTE_API_KEY'))" in text
    assert "print(os.getenv('OMNIROUTE_API_KEY'" not in text
    assert "print(os.environ.get('OMNIROUTE_API_KEY'" not in text
