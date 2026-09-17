# Telegram Enterprise Grid - Auto Create 3 Missing Groups
# Uses Telethon to create groups and add bot as admin

Write-Host "=== Telegram Enterprise Grid Setup ===" -ForegroundColor Cyan
Write-Host "Date: $(Get-Date)" -ForegroundColor Gray
Write-Host ""

# Check if Python is available
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: python not found" -ForegroundColor Red
    exit 1
}

# Check telethon
try {
    python -c "import telethon" 2>$null
} catch {
    Write-Host "Installing telethon..." -ForegroundColor Yellow
    pip install telethon
}

# Set credentials (FROM OWNER)
$env:TELEGRAM_API_ID = "30160587"
$env:TELEGRAM_API_HASH = "5a6af325bc59e9da130999f2ccda1674"

# Run the script
Write-Host "Running telethon_create_groups.py..." -ForegroundColor Green
python scripts/telethon_create_groups.py `
    --api-id $env:TELEGRAM_API_ID `
    --api-hash $env:TELEGRAM_API_HASH `
    --phone "+91" `
    --create

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host "Check data/new_group_chat_ids.json for results" -ForegroundColor Gray
