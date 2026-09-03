# Squad Lead — QA & Testing (Squad 6)
# Responsibility: Targeted pytest suites, smoke tests, contract tests, landmine detection
# Autopilot: Auto-run on every commit, daily full suite, landmine alert

from app.utils.logger import setup_logger
import subprocess, json

logger = setup_logger(__name__)
squad_name = "QA & Testing"
status = "GREEN"
capacity = 66

def run_contract_tests():
    """Run the contract test suite (test_billing_truth_2026.py + knowledge OS)."""
    result = subprocess.run(
        ["bash", "-c", ".venv\\Scripts\\pytest.exe tests/test_billing_truth_2026.py -q"],
        cwd="C:\\Users\\Ratanshila\\.openclaw\\workspace",
        capture_output=True, text=True
    )
    output = result.stdout + result.stderr
    pass_count = output.count("PASS") if "PASS" in output else 0
    fail_count = output.count("FAIL") if "FAIL" in output else 0
    
    result_data = {
        "status": "run_complete",
        "pass_count": pass_count,
        "fail_count": fail_count,
        "output": output[-500:] if len(output) > 500 else output,
    }
    logger.info(f"Squad 6 contract tests: {pass_count} passed, {fail_count} failed")
    return result_data

def run_pytest_shards():
    """Run the 4 pytest shards (1-4) as part of CI gate."""
    results = []
    for shard in range(1, 5):
        r = subprocess.run(
            ["bash", "-c", f".venv\\Scripts\\pytest.exe tests/ -q --shard={shard}"],
            cwd="C:\\Users\\Ratanshila\\.openclaw\\workspace",
            capture_output=True, text=True
        )
        results.append({
            "shard": shard,
            "returncode": r.returncode,
            "output": r.stdout[-300:] if len(r.stdout) > 300 else r.stdout,
        })
    return {"status": "shards_run", "results": results}

def check_landmines():
    """Scan codebase for known landmines from AGENT_WORK_RULES.md."""
    import os, re
    landmines_found = []
    
    # Check for common anti-patterns
    for root, dirs, files in os.walk("C:\\Users\\Ratanshila\\.openclaw\\workspace\\app"):
        # Skip .venv
        if ".venv" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                filepath = os.path.join(root, f)
                try:
                    with open(filepath) as fh:
                        content = fh.read()
                    # Check for :latest usage (provenance risk)
                    if ":latest" in content:
                        landmines_found.append(f"{filepath}: :latest usage detected")
                    # Check for bare git add -A
                    if re.search(r"git\s+add\s+-A\s*", content):
                        landmines_found.append(f"{filepath}: git add -A detected")
                except:
                    pass
    
    return {"status": "landmine_scan", "found": len(landmines_found), "details": landmines_found[:10]}

# Export for autopilot registration
__all__ = ["squad_name", "status", "capacity", "run_contract_tests", "run_pytest_shards", "check_landmines"]