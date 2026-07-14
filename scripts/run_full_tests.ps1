# run_full_tests.ps1 — FULL regression suite with a bounded per-test timeout.
# The full suite is documented as able to HANG (team_pulse area), so every test
# gets a hard timeout and the run is written to a log we read afterwards
# (streaming long output kills the Desktop Commander session).
$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
$py = '.venv\Scripts\python.exe'
# No -x: we want the FULL failure picture, not just the first break.
# --timeout-method=thread survives tests that block in C/socket calls.
& $py -m pytest tests/ -q --timeout=90 --timeout-method=thread --no-header `
  2>&1 | Out-File -FilePath 'pytest_full.log' -Encoding utf8
Write-Output ('PYTEST_RC=' + $LASTEXITCODE) | Out-File -FilePath 'pytest_full.log' -Append -Encoding utf8
