#!/usr/bin/env bash
set -euo pipefail

COMPOSE_CMD="${1:-docker compose}"
# shellcheck disable=SC2206
COMPOSE_PARTS=(${COMPOSE_CMD})

rc=0
"${COMPOSE_PARTS[@]}" up --build ubuntu_tests debian_tests fedora_tests || rc=$?
"${COMPOSE_PARTS[@]}" down -v --remove-orphans
exit "${rc}"
