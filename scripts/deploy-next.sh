#!/usr/bin/env bash
set -euo pipefail

# Builds the redesigned UI with the dark-launch base path and stages it
# under docs/next/ for GitHub Pages. Only ever touches docs/next/ — never
# docs/index.html, docs/assets/, docs/engineering/, or docs/404.html — so
# the live demo at anjesh.ai/FlowStrix/ can't be clobbered by this build.
cd "$(dirname "${BASH_SOURCE[0]}")/.."

npm --prefix ui run build:next

rm -rf docs/next
mkdir -p docs/next
cp -r ui/dist/. docs/next/

echo "Staged ui/dist -> docs/next/"
