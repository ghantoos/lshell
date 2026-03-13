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
    @bash -ceu '\
      sample="{{sample}}"; \
      sample="${sample#sample=}"; \
      distro="{{distro}}"; \
      if [[ ! -f "test/samples/${sample}" ]]; then \
        echo "Unknown sample: ${sample}"; \
        echo "Use: just sample-list"; \
        exit 1; \
      fi; \
      if [[ "${distro}" != "debian" && "${distro}" != "ubuntu" && "${distro}" != "fedora" ]]; then \
        echo "Unsupported distro: ${distro}"; \
        echo "Allowed values: debian, ubuntu, fedora"; \
        exit 1; \
      fi; \
      echo "Starting interactive lshell on ${distro} with test/samples/${sample}"; \
      {{compose}} run --build --rm --entrypoint lshell "${distro}" --config "/app/test/samples/${sample}" \
    '

# User-friendly distro shortcuts:
sample-debian sample='01_baseline_allowlist.conf':
    just sample-lshell debian {{sample}}

sample-ubuntu sample='01_baseline_allowlist.conf':
    just sample-lshell ubuntu {{sample}}

sample-fedora sample='01_baseline_allowlist.conf':
    just sample-lshell fedora {{sample}}

# Debian
debian:
    just run debian

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

# Open an interactive root shell with testuser preconfigured
pkg-deb-run-debian:
    just pkg-deb-run-debian-mode login

# Ubuntu
ubuntu:
    just run ubuntu

test-ubuntu:
    just run ubuntu_tests

test-ubuntu-pypi:
    just run ubuntu-pypi

test-ubuntu-pypi-pre:
    just run ubuntu-pypi-pre

# Fedora
fedora:
    just run fedora

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
    @bash -ceu '\
      rc=0; \
      {{e2e_compose}} up --build -d lshell-ssh-target; \
      {{e2e_compose}} run --build --rm ansible-runner || rc=$?; \
      {{e2e_compose}} down -v --remove-orphans; \
      exit $rc\
    '

# Lint Python sources
test-lint-flake8:
    pylint $(git ls-files '*.py')
    flake8 lshell test

# Run Atheris fuzzing in Debian Docker container (host deps not required)
test-fuzz-security-parser runs='20000':
    {{compose}} run --build --rm --entrypoint bash debian -lc "CLANG_BIN=clang python3 -m pip install --user --break-system-packages -r /app/requirements-fuzz.txt && PYTHONPATH=/app python3 /app/fuzz/fuzz_parser_policy.py -runs={{runs}}"

# Full local validation in one command
test-all:
    just test-lint-flake8
    @bash -ceu '\
      rc=0; \
      {{compose}} up --build ubuntu_tests debian_tests fedora_tests || rc=$?; \
      {{compose}} down -v --remove-orphans; \
      exit $rc\
    '
    just test-fuzz-security-parser
    just test-ssh-e2e
