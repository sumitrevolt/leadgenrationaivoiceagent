#!/usr/bin/env bash
set -euo pipefail
cd /tmp
rm -rf r
git init r >/dev/null
cd r
git remote add origin https://github.com/deepseek-ai/deepseek-harness.git
git fetch --depth=1 origin 47f943859bef60e4160492346772ded9b24f765a
git checkout --detach FETCH_HEAD >/dev/null
BYTES=$(git archive --format=tar HEAD | wc -c)
SHA=$(git archive --format=tar HEAD | sha256sum | cut -d' ' -f1)
TREE=$(git rev-parse 'HEAD^{tree}')
echo "BYTES=$BYTES"
echo "SHA=$SHA"
echo "TREE=$TREE"
