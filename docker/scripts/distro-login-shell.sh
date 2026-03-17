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

if [[ -z "${PKG_CMD}" ]]; then
  echo "Missing package check command." >&2
  exit 1
fi

if [[ ! -f "${CFG}" ]]; then
  echo "Config file does not exist: ${CFG}" >&2
  exit 1
fi

LSHELL_BIN="$(command -v lshell || true)"
if [[ -z "${LSHELL_BIN}" ]]; then
  echo "lshell is not installed in this container." >&2
  exit 1
fi

lshell setup-system \
  --group lshell \
  --log-dir /var/log/lshell \
  --owner root \
  --mode 2770 \
  --shell-path "${LSHELL_BIN}" \
  --set-shell-user testuser \
  --add-group-user testuser

# `su - testuser` starts lshell with its default config path (/etc/lshell.conf).
if [[ ! -f /etc/lshell.conf ]] || ! cmp -s "${CFG}" /etc/lshell.conf; then
  install -m 0644 "${CFG}" /etc/lshell.conf
fi

printf "%s\n" \
  "============================================================" \
  "Interactive ${DISTRO} root shell is ready" \
  "============================================================" \
  "Current account: root" \
  "" \
  "lshell binary: ${LSHELL_BIN}" \
  "testuser login shell is now set to lshell." \
  "active lshell config: /etc/lshell.conf (source: ${CFG})" \
  "" \
  "Suggested checks:" \
  "  1) ${PKG_CMD}" \
  "  2) lshell --version" \
  "  3) lshell policy-show --config ${CFG} --user testuser --group lshell --command \"cat /home/testuser/lshell/test/testfiles/test.conf\"" \
  "  4) su -s /bin/bash -c \"lshell --config ${CFG}\" testuser" \
  "  5) su - testuser" \
  "" \
  "Type \"exit\" to leave the container." \
  "============================================================"

exec bash
