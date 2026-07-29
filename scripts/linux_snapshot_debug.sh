#!/bin/sh
set -e
mkdir -p /work/app/marketing/video_production /work/app/utils /work/tests
: > /work/app/__init__.py
: > /work/app/marketing/__init__.py
: > /work/app/marketing/video_production/__init__.py
: > /work/app/utils/__init__.py
cp /src/app/marketing/video_media_paths.py /work/app/marketing/
cp /src/app/marketing/video_production/snapshot.py /work/app/marketing/video_production/
cp /src/app/utils/logger.py /work/app/utils/
cd /work
python - <<'PY' 2>&1 | tail -8
try:
    from app.marketing.video_production import snapshot
    print("IMPORT_OK", snapshot.snapshot_filename("a", 0, "f"*64))
except Exception as e:
    import traceback
    traceback.print_exc()
PY
