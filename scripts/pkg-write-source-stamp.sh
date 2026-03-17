#!/usr/bin/env bash
set -euo pipefail

STAMP_FILE="${1:?missing stamp file}"
mkdir -p "$(dirname "${STAMP_FILE}")"
{ git rev-parse HEAD; git status --porcelain=v1 --untracked-files=all; } | shasum -a 256 | awk '{print $1}' > "${STAMP_FILE}"
