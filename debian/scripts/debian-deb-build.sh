#!/usr/bin/env bash

set -euo pipefail

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  build-essential \
  debhelper \
  dh-python \
  dpkg-dev \
  fakeroot \
  lintian \
  pybuild-plugin-pyproject \
  python3-all \
  python3-setuptools

WORKDIR="/tmp/lshell-deb-src"
OUTDIR="/app/build/deb"

rm -rf "${WORKDIR}" "${OUTDIR}"
mkdir -p "${OUTDIR}"
cp -a /app "${WORKDIR}"

cd "${WORKDIR}"

# Legacy Debian rules expect a CHANGES file. Keep it local to build workspace.
if [ ! -f CHANGES ] && [ -f CHANGELOG.md ]; then
  cp CHANGELOG.md CHANGES
fi

PY_VERSION="$(python3 -c 'import lshell.variables as v; print(v.__version__)')"
DEB_REVISION="${DEB_REVISION:-1}"
DEB_VERSION="${PY_VERSION}-${DEB_REVISION}"
CURRENT_CHANGELOG_VERSION="$(dpkg-parsechangelog -S Version)"

if [ "${CURRENT_CHANGELOG_VERSION}" != "${DEB_VERSION}" ]; then
  sed -E -i "1s/^lshell \\([^)]*\\) /lshell (${DEB_VERSION}) /" debian/changelog
  echo "Updated debian/changelog version: ${CURRENT_CHANGELOG_VERSION} -> ${DEB_VERSION}"
fi

DEB_BUILD_OPTIONS=nocheck dpkg-buildpackage -us -uc -b

find /tmp -maxdepth 1 -type f \( -name 'lshell_*.deb' -o -name 'lshell_*.changes' -o -name 'lshell_*.buildinfo' \) -exec cp -a {} "${OUTDIR}/" \;

# Treat lintian warnings as failures so package quality stays strict.
lintian --fail-on warning "${OUTDIR}"/lshell_*.deb

ls -lah "${OUTDIR}"
