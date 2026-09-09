#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 dist/praxis_v2.pyz demo --out "demo-$(date +%Y%m%d-%H%M%S)"
