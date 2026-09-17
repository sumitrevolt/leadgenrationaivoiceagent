#!/bin/bash
# Telegram Enterprise Grid - Auto Create 3 Missing Groups
# Uses Telethon to create groups and add bot as admin

set -e

echo "=== Telegram Enterprise Grid Setup ==="
echo "Date: $(date)"
echo ""

# Check if Python and telethon are available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

# Check telethon
python3 -c "import telethon" 2>/dev/null || {
    echo "Installing telethon..."
    pip install telethon
}

# Set credentials (FROM OWNER)
export TELEGRAM_API_ID=30160587
export TELEGRAM_API_HASH=5a6af325bc59e9da130999f2ccda1674

# Run the script
echo "Running telethon_create_groups.py..."
python3 scripts/telethon_create_groups.py \
    --api-id $TELEGRAM_API_ID \
    --api-hash "$TELEGRAM_API_HASH" \
    --phone "+91" \
    --create

echo ""
echo "=== Setup Complete ==="
echo "Check data/new_group_chat_ids.json for results"
