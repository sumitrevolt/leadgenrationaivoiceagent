#!/bin/sh
# Linux proofs for the media-root authority AND the snapshot primitive.
# Minimal container: no repo conftest, no .env, no Compose, network disabled.
set -e
mkdir -p /work/app/marketing/video_production /work/app/utils /work/tests
: > /work/app/__init__.py
: > /work/app/marketing/__init__.py
: > /work/app/marketing/video_production/__init__.py
: > /work/app/utils/__init__.py
cp /src/app/marketing/video_media_paths.py /work/app/marketing/
cp /src/app/marketing/media_limits.py /work/app/marketing/
cp /src/app/marketing/video_production/snapshot.py /work/app/marketing/video_production/
# app/utils/logger.py pulls app.config (pydantic-settings). The POSIX proof is
# about filesystem semantics, not logging, so the harness stubs setup_logger
# rather than dragging the settings stack into a minimal offline container.
cat > /work/app/utils/logger.py <<'PYSTUB'
import logging


def setup_logger(name):
    return logging.getLogger(name)
PYSTUB
cp /src/tests/test_video_media_symlink_posix.py /work/tests/
cp /src/tests/test_video_snapshot_posix.py /work/tests/
cd /work
echo "UNAME=$(uname -s)"
if [ -f /work/.env ]; then echo "dotenv_present=YES"; else echo "dotenv_present=NO"; fi
if [ -f /work/tests/conftest.py ]; then echo "repo_conftest=YES"; else echo "repo_conftest=NO"; fi
python -m pytest tests/ -q --no-header -p no:cacheprovider 2>&1 | tail -16
