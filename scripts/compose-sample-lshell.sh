#!/usr/bin/env bash
set -euo pipefail

DISTRO="${1:-}"
SAMPLE="${2:-01_baseline_allowlist.conf}"
SAMPLE="${SAMPLE#sample=}"

if [[ ! -f "test/samples/${SAMPLE}" ]]; then
  echo "Unknown sample: ${SAMPLE}" >&2
  echo "Use: just sample-list" >&2
  exit 1
fi

if [[ "${DISTRO}" != "debian" && "${DISTRO}" != "ubuntu" && "${DISTRO}" != "fedora" ]]; then
  echo "Unsupported distro: ${DISTRO}" >&2
  echo "Allowed values: debian, ubuntu, fedora" >&2
  exit 1
fi

echo "Starting interactive lshell on ${DISTRO} with test/samples/${SAMPLE}"

COMPOSE_CMD="${COMPOSE:-docker compose}"
# shellcheck disable=SC2206
COMPOSE_PARTS=(${COMPOSE_CMD})
"${COMPOSE_PARTS[@]}" run --build --rm --entrypoint lshell "${DISTRO}" --config "/app/test/samples/${SAMPLE}"
