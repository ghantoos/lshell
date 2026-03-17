#!/usr/bin/env bash
set -euo pipefail

DISTRO="${1:-}"
PKG_CMD="${2:-}"
CFG="${3:-/app/etc/lshell.conf}"

if [[ "${DISTRO}" != "debian" && "${DISTRO}" != "ubuntu" && "${DISTRO}" != "fedora" ]]; then
  echo "Unsupported distro: ${DISTRO}" >&2
  echo "Allowed values: debian, ubuntu, fedora" >&2
  exit 1
fi

COMPOSE_CMD="${COMPOSE:-docker compose}"
# shellcheck disable=SC2206
COMPOSE_PARTS=(${COMPOSE_CMD})
"${COMPOSE_PARTS[@]}" run --build --rm --user root --entrypoint bash "${DISTRO}" /app/docker/scripts/distro-login-shell.sh "${DISTRO}" "${PKG_CMD}" "${CFG}"
