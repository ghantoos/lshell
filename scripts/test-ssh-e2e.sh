#!/usr/bin/env bash
set -euo pipefail

E2E_COMPOSE="${1:-docker compose -f docker-compose.e2e.yml}"
# shellcheck disable=SC2206
COMPOSE_PARTS=(${E2E_COMPOSE})

rc=0
"${COMPOSE_PARTS[@]}" up --build -d lshell-ssh-target
"${COMPOSE_PARTS[@]}" run --build --rm ansible-runner || rc=$?
"${COMPOSE_PARTS[@]}" down -v --remove-orphans
exit "${rc}"
