#!/usr/bin/env bash

set -euo pipefail

MODE="${1:-${MODE:-tests}}"
MODE="${MODE#mode=}"
DEB_FILE="$(ls -1t /app/build/deb/lshell_*_all.deb | head -n1)"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y "${DEB_FILE}"

install -m 0644 /app/debian/lshell.deb-test.conf /etc/lshell.deb-test.conf

if [ "${MODE}" = "tests" ]; then
  # Force test invocations to use the installed Debian package binary.
  ln -sf /usr/bin/lshell /home/testuser/lshell/bin/lshell

  runuser -u testuser -- bash -lc \
    "cd /home/testuser/lshell && python3 -m pytest -q /home/testuser/lshell/test"
  exit 0
fi

if [ "${MODE}" = "login" ]; then
  # For manual login testing, make the layered Debian test profile the active default.
  cp -f /etc/lshell.deb-test.conf /etc/lshell.conf

  printf "%s\n" \
    "============================================================" \
    "Debian package test shell is ready" \
    "============================================================" \
    "Installed DEB: ${DEB_FILE}" \
    "" \
    "Accounts:" \
    "  - root (current shell)" \
    "  - testuser / password: password" \
    "" \
    "Main DEB test config (layered): /etc/lshell.deb-test.conf" \
    "Layers included in this file:" \
    "  - [default]" \
    "  - [grp:lshell]" \
    "  - [testuser]" \
    "" \
    "Suggested checks:" \
    "  1) dpkg -s lshell" \
    "  2) lshell --version" \
    "  3) lshell policy-show --config /etc/lshell.deb-test.conf --user testuser --group lshell --command \"cat /home/testuser/lshell/test/testfiles/test.conf\"" \
    "  4) su -s /bin/bash -c \"lshell --config /etc/lshell.deb-test.conf\" testuser" \
    "  5) su - testuser" \
    "  6) runuser -u testuser -- bash -lc \"cd /home/testuser/lshell && python3 -m pytest -q /home/testuser/lshell/test\"" \
    "" \
    "Type \"exit\" to leave the container." \
    "============================================================"
  exec bash
fi

echo "Unknown mode: ${MODE}. Use MODE=tests or MODE=login." >&2
exit 2
