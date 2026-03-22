#!/usr/bin/env bash

set -euo pipefail

RPM_FILE="$(ls -1t /app/build/rpm/RPMS/noarch/lshell-*.rpm | head -n1)"

dnf install -y "${RPM_FILE}"

install -m 0644 /app/rpm/lshell.rpm-test.conf /etc/lshell.rpm-test.conf

lshell --version
lshell --config /etc/lshell.conf --help >/dev/null

# Validate the dedicated RPM test profile parses and resolves policy layers.
lshell policy-show \
  --config /etc/lshell.rpm-test.conf \
  --user testuser \
  --group lshell \
  --command "cat /home/testuser/lshell/test/testfiles/test.conf" >/dev/null
