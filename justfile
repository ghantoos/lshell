set shell := ["bash", "-cu"]

compose := env_var_or_default("COMPOSE", "docker compose")
e2e_compose := "docker compose -f docker-compose.e2e.yml"

default:
    @just --list

# Run any docker compose command, e.g. `just dc "run --rm ubuntu_tests"`
dc args:
    {{compose}} {{args}}

# Run a compose service with build + cleanup, e.g. `just run ubuntu_tests`
run service:
    {{compose}} run --build --rm {{service}}

# Start a compose service with build, e.g. `just up ubuntu-pypi`
up service:
    {{compose}} up --build {{service}}

# Build one or more services, e.g. `just build ubuntu_tests ubuntu`
build +services:
    {{compose}} build {{services}}

# Stop and remove compose resources
clean:
    {{compose}} down -v --remove-orphans

# Aggressive Docker cleanup (images, containers, networks, build cache, volumes)
docker-prune:
    docker system prune -af --volumes

# Targeted cleanup for lshell compose stacks only
docker-clean-lshell:
    {{compose}} down --rmi local --volumes --remove-orphans
    {{e2e_compose}} down --rmi local --volumes --remove-orphans

# Debian
debian:
    just run debian

test-debian:
    just run debian_tests

test-debian-pypi:
    just run debian-pypi

test-debian-pypi-pre:
    just run debian-pypi-pre

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

# Full local validation in one command
test-all:
    @bash -ceu '\
      rc=0; \
      {{compose}} up --build ubuntu_tests debian_tests fedora_tests || rc=$?; \
      {{compose}} down -v --remove-orphans; \
      exit $rc\
    '
    just test-ssh-e2e
