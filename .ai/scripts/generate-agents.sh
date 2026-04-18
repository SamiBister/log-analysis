#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv run orangit_agents/build.py --source agent "$@"
