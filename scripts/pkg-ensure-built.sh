#!/usr/bin/env bash
set -euo pipefail

STAMP_FILE="${1:?missing stamp file}"
ARTIFACT_GLOB="${2:?missing artifact glob}"
BUILD_RECIPE="${3:?missing build recipe}"
LABEL="${4:-Package}"

artifact="$(ls -1 ${ARTIFACT_GLOB} 2>/dev/null | head -n1 || true)"
current="$( { git rev-parse HEAD; git status --porcelain=v1 --untracked-files=all; } | shasum -a 256 | awk '{print $1}')"

if [[ -n "${artifact}" && -f "${STAMP_FILE}" && "$(cat "${STAMP_FILE}")" == "${current}" ]]; then
  echo "${LABEL} artifacts are up to date."
  exit 0
fi

echo "${LABEL} sources changed (or no artifact found); rebuilding package."
just "${BUILD_RECIPE}"
