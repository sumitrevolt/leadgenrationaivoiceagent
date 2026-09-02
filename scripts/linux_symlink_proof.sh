#!/bin/sh
# Linux symlink-component proof for the media-root authority.
# Runs in a minimal container: no repo conftest, no .env, network disabled.
set -e
mkdir -p /work/app/marketing /work/tests
: > /work/app/__init__.py
: > /work/app/marketing/__init__.py
cp /src/app/marketing/video_media_paths.py /work/app/marketing/
cp /src/tests/test_video_media_symlink_posix.py /work/tests/
cd /work
echo "UNAME=$(uname -s)"
if [ -f /work/.env ]; then echo "dotenv_present=YES"; else echo "dotenv_present=NO"; fi
if [ -f /work/tests/conftest.py ]; then echo "repo_conftest=YES"; else echo "repo_conftest=NO"; fi
python -m pytest tests/test_video_media_symlink_posix.py -q --no-header -p no:cacheprovider 2>&1 | tail -14
