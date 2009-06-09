# Limited Shell (lshell) Makefile
#
# $Id: Makefile,v 1.15 2009-06-09 19:53:46 ghantoos Exp $
#

PYTHON=`which python`
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
		$(PYTHON) setup.py sdist

sourcedeb:
		$(PYTHON) setup.py sdist --dist-dir=../ --prune
		rename -f 's/$(PROJECT)-(.*)\.tar\.gz/$(PROJECT)_$$1\.orig\.tar\.gz/' ../*

install: 
		$(PYTHON) setup.py install --root=$(DESTDIR) --no-compile

buildrpm: 
		$(PYTHON) setup.py bdist_rpm --pre-install=rpm/preinstall --post-install=rpm/postinstall --post-uninstall=rpm/postuninstall

builddeb:
		# build the source package in the parent directory 
		# then rename it to project_version.orig.tar.gz
		$(PYTHON) setup.py sdist --dist-dir=../ --prune
		rename -f 's/$(PROJECT)-(.*)\.tar\.gz/$(PROJECT)_$$1\.orig\.tar\.gz/' ../*
		# build the package
		dpkg-buildpackage -i -I -rfakeroot

clean:
		$(PYTHON) setup.py clean
		$(MAKE) -f $(CURDIR)/debian/rules clean
		rm -rf build/ MANIFEST
		find . -name '*.pyc' -delete

