# Limited Shell (lshell) Makefile
#
# $Id: Makefile,v 1.16 2010-03-06 23:11:38 ghantoos Exp $
#

PYTHON=`which python3`
DESTDIR=/
BUILDIR=$(CURDIR)/debian/lshell
PROJECT=lshell

all:
		@echo "make source - Create source package"
		@echo "make sourcedeb - Create source package (.orig.tar.gz)"
		@echo "make install - Install on local system"
		@echo "make buildrpm - Generate a rpm package"
		@echo "make builddeb - Generate a deb package"
		@echo "make clean - Get rid of scratch and byte files"

source:
		$(PYTHON) -m build --sdist

sourcedeb:
		$(PYTHON) -m build --sdist --outdir=../
		rename -f 's/limited_shell-(.*)\.tar\.gz/$(PROJECT)_$$1\.orig\.tar\.gz/' ../limited_shell-*.tar.gz

install: 
		$(PYTHON) -m pip install --no-deps --no-build-isolation --root=$(DESTDIR) --no-compile .

buildrpm: 
		rpmbuild -ba rpm/lshell.spec

builddeb:
		# build the source package in the parent directory 
		# then rename it to project_version.orig.tar.gz
		$(PYTHON) -m build --sdist --outdir=../
		rename -f 's/limited_shell-(.*)\.tar\.gz/$(PROJECT)_$$1\.orig\.tar\.gz/' ../limited_shell-*.tar.gz
		# build the package
		dpkg-buildpackage -i -I -rfakeroot

clean:
		rm -rf build/ MANIFEST dist/ *.egg-info
		find . -name '*.pyc' -delete
