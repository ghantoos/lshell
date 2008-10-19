# Limited Shell (lshell) Makefile
#
# $Id: Makefile,v 1.1 2008-10-19 16:54:14 ghantoos Exp $
#

PYTHON=`which python`
PKGNAME=lshell
DESTDIR=/
BUILDIR=deb
PROJECT=lshell
VERSION=0.2

all:
		@echo "make install - Install on local system"
		@echo "make buildrpm - Generate a rpm package"
		@echo "make builddeb - Generate a deb package"
		@echo "make clean - Get rid of scratch and byte files"

install: 
		$(PYTHON) setup.py install --root $(DESTDIR)
		chmod 664 $(DESTDIR)/var/log/lshell.log

buildrpm: 
		$(PYTHON) setup.py bdist_rpm --post-install=postinstall

builddeb:
		$(PYTHON) setup.py sdist
		mkdir -p $(BUILDIR)/$(PROJECT)-$(VERSION)/debian
		cp dist/$(PROJECT)-$(VERSION).tar.gz $(BUILDIR)
		cd $(BUILDIR) && tar xfz $(PROJECT)-$(VERSION).tar.gz
		mv $(BUILDIR)/$(PROJECT)-$(VERSION).tar.gz $(BUILDIR)/$(PROJECT)-$(VERSION)/
		cp debian/* $(BUILDIR)/$(PROJECT)-$(VERSION)/debian/
		cd $(BUILDIR)/$(PROJECT)-$(VERSION) && dpkg-buildpackage

clean:
		$(PYTHON) setup.py clean
		rm -rf build/ MANIFEST $(BUILDIR)
		find . -name '*.pyc' -delete

