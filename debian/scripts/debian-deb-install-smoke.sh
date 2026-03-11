#!/usr/bin/env bash

set -euo pipefail

DEB_FILE="$(ls -1t /app/build/deb/lshell_*_all.deb | head -n1)"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y "${DEB_FILE}"

install -m 0644 /app/debian/lshell.deb-test.conf /etc/lshell.deb-test.conf

lshell --version
lshell --config /etc/lshell.conf --help >/dev/null

# Validate the dedicated Debian test profile parses and resolves policy layers.
lshell policy-show \
  --config /etc/lshell.deb-test.conf \
  --user testuser \
  --group lshell \
  --command "cat /home/testuser/lshell/test/testfiles/test.conf" >/dev/null
