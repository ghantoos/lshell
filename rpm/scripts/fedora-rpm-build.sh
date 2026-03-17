#!/usr/bin/env bash

set -euo pipefail

dnf install -y rpm-build python3-devel python3-setuptools python3-wheel

VERSION="$(awk '/^Version:/{print $2; exit}' /app/rpm/lshell.spec)"
if [[ -z "${VERSION}" ]]; then
  echo "Unable to read Version from /app/rpm/lshell.spec" >&2
  exit 1
fi
TOPDIR="/tmp/rpmbuild"
OUTDIR="/app/build/rpm"

rm -rf "${TOPDIR}" "${OUTDIR}"
mkdir -p "${TOPDIR}"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
mkdir -p "${OUTDIR}"

# Build source tarball from the current workspace state (not just git HEAD),
# so local packaging fixes are included in RPM builds.
tar -C /app \
  --exclude-vcs \
  --exclude='./build' \
  --exclude='./.venv' \
  --exclude='./.pytest_cache' \
  --exclude='./.hypothesis' \
  --exclude='./.pylint.d' \
  --exclude='./.pylint_cache' \
  --exclude='./.git' \
  --exclude='./*.egg-info' \
  --exclude='*/__pycache__' \
  --transform "s,^\.,lshell-${VERSION}," \
  -czf "${TOPDIR}/SOURCES/lshell-${VERSION}.tar.gz" \
  .

cp /app/rpm/lshell.spec "${TOPDIR}/SPECS/"
cp /app/rpm/preinstall /app/rpm/postinstall /app/rpm/postuninstall "${TOPDIR}/SOURCES/"

rpmbuild -ba --define "_topdir ${TOPDIR}" "${TOPDIR}/SPECS/lshell.spec"

cp -a "${TOPDIR}/RPMS" "${OUTDIR}/"
cp -a "${TOPDIR}/SRPMS" "${OUTDIR}/"

ls -lah "${OUTDIR}/RPMS" "${OUTDIR}/SRPMS"
