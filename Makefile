# Limited Shell (lshell) Makefile
#
# $Id: Makefile,v 1.11 2009-01-25 22:56:48 ghantoos Exp $
#

PYTHON=`which python`
DESTDIR=/
BUILDIR=$(CURDIR)/debian/lshell
PROJECT=lshell

all:
		@echo "make install - Install on local system"
		@echo "make buildrpm - Generate a rpm package"
		@echo "make builddeb - Generate a deb package"
		@echo "make clean - Get rid of scratch and byte files"

install: 
		$(PYTHON) setup.py install --root $(DESTDIR) $(COMPILE)

buildrpm: 
		$(PYTHON) setup.py bdist_rpm --post-install=rpm/postinstall --post-uninstall=rpm/postuninstall

builddeb:
		mkdir -p ${BUILDIR}
		DESTDIR=$(BUILDIR) dpkg-buildpackage -rfakeroot

clean:
		$(PYTHON) setup.py clean
		$(MAKE) -f $(CURDIR)/debian/rules clean
		rm -rf build/ MANIFEST
		find . -name '*.pyc' -delete

