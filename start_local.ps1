# LeadGen AI — one-command local launch (Windows PowerShell)
# Usage:  powershell -ExecutionPolicy Bypass -File start_local.ps1

Write-Host "==> LeadGen AI local launch" -ForegroundColor Cyan

# 1. venv
if (-not (Test-Path "venv")) {
    Write-Host "Creating venv..." -ForegroundColor Yellow
    python -m venv venv
}
.\venv\Scripts\Activate.ps1

# 2. deps (core = fast). Full features: pip install -r requirements.txt
Write-Host "Installing core deps..." -ForegroundColor Yellow
pip install -q -r requirements-core.txt

# 3. .env
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Add-Content ".env" "`nDATABASE_URL=sqlite:///./leadgen.db`nAPP_ENV=development`nDEBUG=true"
    Write-Host ".env created (SQLite). Add GEMINI_API_KEY / SARVAM_API_KEY for real AI." -ForegroundColor Yellow
}

# 4. seed demo data
Write-Host "Seeding demo data..." -ForegroundColor Yellow
$env:DATABASE_URL = "sqlite:///./leadgen.db"
python scripts/seed_demo_data.py

# 5. run
Write-Host "Starting server -> http://localhost:8000" -ForegroundColor Green
Write-Host "  /site/  /app/customer  /app/admin  /app/test-call" -ForegroundColor Green
uvicorn app.main:app --reload --port 8000
