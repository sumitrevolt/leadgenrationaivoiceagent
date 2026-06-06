#!/usr/bin/env bash
# LeadGen AI — one-command local launch (Mac/Linux)
# Usage:  bash start_local.sh
set -e
echo "==> LeadGen AI local launch"

# 1. venv
if [ ! -d "venv" ]; then python -m venv venv; fi
source venv/bin/activate

# 2. deps (core = fast). Full features: pip install -r requirements.txt
echo "Installing core deps..."
pip install -q -r requirements-core.txt

# 3. .env
if [ ! -f ".env" ]; then
  cp .env.example .env
  printf "\nDATABASE_URL=sqlite:///./leadgen.db\nAPP_ENV=development\nDEBUG=true\n" >> .env
  echo ".env created (SQLite). Add GEMINI_API_KEY / SARVAM_API_KEY for real AI."
fi

# 4. seed demo data
echo "Seeding demo data..."
export DATABASE_URL="sqlite:///./leadgen.db"
python scripts/seed_demo_data.py

# 5. run
echo "Starting server -> http://localhost:8000  (/site/ /app/customer /app/admin /app/test-call)"
uvicorn app.main:app --reload --port 8000
