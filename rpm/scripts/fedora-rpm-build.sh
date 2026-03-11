#!/usr/bin/env bash

set -euo pipefail

dnf install -y rpm-build python3-devel python3-setuptools
git config --global --add safe.directory /app

VERSION="$(python3 -c "from lshell.variables import __version__; print(__version__)")"
TOPDIR="/tmp/rpmbuild"
OUTDIR="/app/build/rpm"

rm -rf "${TOPDIR}" "${OUTDIR}"
mkdir -p "${TOPDIR}"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
mkdir -p "${OUTDIR}"

git -C /app archive \
  --format=tar.gz \
  --prefix="lshell-${VERSION}/" \
  -o "${TOPDIR}/SOURCES/lshell-${VERSION}.tar.gz" \
  HEAD

cp /app/rpm/lshell.spec "${TOPDIR}/SPECS/"
cp /app/rpm/preinstall /app/rpm/postinstall /app/rpm/postuninstall "${TOPDIR}/SOURCES/"

rpmbuild -ba --define "_topdir ${TOPDIR}" "${TOPDIR}/SPECS/lshell.spec"

cp -a "${TOPDIR}/RPMS" "${OUTDIR}/"
cp -a "${TOPDIR}/SRPMS" "${OUTDIR}/"

ls -lah "${OUTDIR}/RPMS" "${OUTDIR}/SRPMS"
