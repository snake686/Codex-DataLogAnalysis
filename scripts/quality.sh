#!/usr/bin/env sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export UV_CACHE_DIR="$project_root/.uv-cache"
export UV_PYTHON_INSTALL_DIR="$project_root/.uv-python"

exec uv --directory "$project_root" run --locked python scripts/quality.py
