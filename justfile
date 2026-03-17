set shell := ["bash", "-cu"]

compose := env_var_or_default("COMPOSE", "docker compose")
e2e_compose := "docker compose -f docker-compose.e2e.yml"

[private]
default:
    @just --list

# Run a compose service with build + cleanup, e.g. `just run ubuntu_tests`
[private]
run service:
    {{compose}} run --build --rm {{service}}

# Start a compose service with build, e.g. `just up ubuntu-pypi`
[private]
up service:
    {{compose}} up --build {{service}}

# Build one or more services, e.g. `just build ubuntu_tests ubuntu`
[private]
build +services:
    {{compose}} build {{services}}

# Aggressive Docker cleanup (images, containers, networks, build cache, volumes)
docker-prune:
    docker system prune -af --volumes

# Targeted cleanup for lshell compose stacks only
docker-clean-lshell:
    {{compose}} down --rmi local --volumes --remove-orphans
    {{e2e_compose}} down --rmi local --volumes --remove-orphans

# List available interactive sample configurations
sample-list:
    @ls -1 test/samples/*.conf | xargs -n1 basename
    @echo
    @echo "Run one with:"
    @echo "  just sample-ubuntu 01_baseline_allowlist.conf"
    @echo "  just sample-ubuntu sample=01_baseline_allowlist.conf"

# Run lshell interactively with one sample config on a chosen distro.
# Example: just sample-lshell debian 04_sudo_and_aliases.conf
[private]
sample-lshell distro sample='01_baseline_allowlist.conf':
    COMPOSE="{{compose}}" ./scripts/compose-sample-lshell.sh "{{distro}}" "{{sample}}"

# User-friendly distro shortcuts:
sample-debian sample='01_baseline_allowlist.conf':
    just sample-lshell debian {{sample}}

sample-ubuntu sample='01_baseline_allowlist.conf':
    just sample-lshell ubuntu {{sample}}

sample-fedora sample='01_baseline_allowlist.conf':
    just sample-lshell fedora {{sample}}

# Open a distro container as root with package-style suggested checks.
[private]
distro-login-shell distro pkg_cmd cfg='/app/etc/lshell.conf':
    COMPOSE="{{compose}}" ./scripts/compose-distro-login-shell.sh "{{distro}}" "{{pkg_cmd}}" "{{cfg}}"

# Debian
run-debian:
    just run debian

run-debian-root:
    just distro-login-shell debian "dpkg -s lshell"

test-debian:
    just run debian_tests

test-debian-pypi:
    just run debian-pypi

test-debian-pypi-pre:
    just run debian-pypi-pre

# Build a Debian package from the current workspace using Debian tooling
[private]
pkg-deb-build-debian:
    {{compose}} run --build --rm --user root --entrypoint bash debian /app/debian/scripts/debian-deb-build.sh

# Install latest built Debian package and verify CLI smoke checks
[private]
pkg-deb-install-debian:
    {{compose}} run --build --rm --user root --entrypoint bash debian /app/debian/scripts/debian-deb-install-smoke.sh

# Run against installed Debian package in two modes:
# - mode=tests (default): run full /app/test suite as testuser
# - mode=login: open root shell with testuser configured as /usr/bin/lshell
[private]
pkg-deb-run-debian-mode mode='tests':
    {{compose}} run --build --rm --user root -e MODE={{mode}} --entrypoint bash debian /app/debian/scripts/debian-deb-run.sh

# Run full tests against installed Debian package
[private]
pkg-deb-test-debian:
    just pkg-deb-run-debian-mode tests

# Full Debian flow: build, install verification, and installed-package tests
pkg-deb-build:
    just pkg-deb-build-debian
    just pkg-deb-install-debian
    just pkg-deb-test-debian

pkg-deb-run-debian:
    just pkg-deb-run-debian-mode login

# Ubuntu
run-ubuntu:
    just run ubuntu

run-ubuntu-root:
    just distro-login-shell ubuntu "dpkg -s lshell"

test-ubuntu:
    just run ubuntu_tests

test-ubuntu-pypi:
    just run ubuntu-pypi

test-ubuntu-pypi-pre:
    just run ubuntu-pypi-pre

# Fedora
run-fedora:
    just run fedora

run-fedora-root:
    just distro-login-shell fedora "rpm -qi lshell"

test-fedora:
    just run fedora_tests

# Build an RPM from the current workspace using Fedora tooling
[private]
pkg-rpm-build-fedora:
    {{compose}} run --build --rm --user root --entrypoint bash fedora /app/rpm/scripts/fedora-rpm-build.sh

# Install latest built RPM in Fedora container and verify CLI smoke checks
[private]
pkg-rpm-install-fedora:
    {{compose}} run --build --rm --user root --entrypoint bash fedora /app/rpm/scripts/fedora-rpm-install-smoke.sh

# Run against installed RPM in two modes:
# - mode=tests (default): run full /app/test suite as testuser
# - mode=login: open root shell with testuser configured as /usr/bin/lshell
[private]
pkg-rpm-run-fedora-mode mode='tests':
    {{compose}} run --build --rm --user root -e MODE={{mode}} --entrypoint bash fedora /app/rpm/scripts/fedora-rpm-run.sh

# Run full tests against installed RPM
[private]
pkg-rpm-test-fedora:
    just pkg-rpm-run-fedora-mode tests

# Open an interactive root shell with testuser preconfigured
pkg-rpm-run-fedora:
    just pkg-rpm-run-fedora-mode login

# Full RPM flow: build, install verification, and installed-package tests
pkg-rpm-build:
    just pkg-rpm-build-fedora
    just pkg-rpm-install-fedora
    just pkg-rpm-test-fedora

test-fedora-pypi:
    just run fedora-pypi

test-fedora-pypi-pre:
    just run fedora-pypi-pre

# Real SSH end-to-end tests with Docker + Ansible only
test-ssh-e2e:
    ./scripts/test-ssh-e2e.sh "{{e2e_compose}}"

# Lint Python sources
test-lint-flake8:
    pylint lshell test
    flake8 lshell test

# Run Atheris fuzzing in Debian Docker container (host deps not required)
test-fuzz-security-parser runs='20000':
    {{compose}} run --build --rm --entrypoint bash debian -lc "CLANG_BIN=clang python3 -m pip install --user --break-system-packages -r /app/requirements-fuzz.txt && PYTHONPATH=/app python3 /app/fuzz/fuzz_parser_policy.py -runs={{runs}}"

# Full local validation in one command
test-all:
    just test-lint-flake8
    ./scripts/test-all.sh "{{compose}}"
    just test-fuzz-security-parser
    just test-ssh-e2e
