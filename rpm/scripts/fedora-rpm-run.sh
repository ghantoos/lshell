#!/usr/bin/env bash

set -euo pipefail

MODE="${1:-${MODE:-tests}}"
MODE="${MODE#mode=}"
RPM_FILE="$(ls -1t /app/build/rpm/RPMS/noarch/lshell-*.rpm | head -n1)"

dnf install -y "${RPM_FILE}"
dnf install -y bash-completion

if ! grep -q "bash_completion" /root/.bashrc 2>/dev/null; then
  cat >>/root/.bashrc <<'EOF'
if [ -f /usr/share/bash-completion/bash_completion ]; then
  . /usr/share/bash-completion/bash_completion
fi
EOF
fi

if [ -f /usr/etc/lshell.conf ] && [ ! -f /etc/lshell.conf ]; then
  cp -a /usr/etc/lshell.conf /etc/lshell.conf
fi

install -m 0644 /app/rpm/lshell.rpm-test.conf /etc/lshell.rpm-test.conf

if [ "${MODE}" = "tests" ]; then
  # Force test invocations to use the installed RPM binary.
  ln -sf /usr/bin/lshell /home/testuser/lshell/bin/lshell

  runuser -u testuser -- bash -lc \
    "cd /home/testuser/lshell && python3 -m pytest -q /home/testuser/lshell/test"
  exit 0
fi

if [ "${MODE}" = "login" ]; then
  # For manual login testing, make the layered RPM test profile the active default.
  cp -f /etc/lshell.rpm-test.conf /etc/lshell.conf

  printf "%s\n" \
    "============================================================" \
    "Fedora RPM test shell is ready" \
    "============================================================" \
    "Installed RPM: ${RPM_FILE}" \
    "" \
    "Accounts:" \
    "  - root (current shell)" \
    "  - testuser / password: password" \
    "" \
    "Main RPM test config (layered): /etc/lshell.rpm-test.conf" \
    "Layers included in this file:" \
    "  - [default]" \
    "  - [grp:lshell]" \
    "  - [testuser]" \
    "" \
    "Suggested checks:" \
    "  1) rpm -qi lshell" \
    "  2) lshell --version" \
    "  3) lshell policy-show --config /etc/lshell.rpm-test.conf --user testuser --group lshell --command \"cat /home/testuser/lshell/test/testfiles/test.conf\"" \
    "  4) su -s /bin/bash -c \"lshell --config /etc/lshell.rpm-test.conf\" testuser" \
    "  5) su - testuser" \
    "  6) runuser -u testuser -- bash -lc \"cd /home/testuser/lshell && python3 -m pytest -q /home/testuser/lshell/test\"" \
    "" \
    "Type \"exit\" to leave the container." \
    "============================================================"
  exec bash
fi

echo "Unknown mode: ${MODE}. Use MODE=tests or MODE=login." >&2
exit 2
