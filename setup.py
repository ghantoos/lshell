#!/usr/bin/env python
#
# $Id: setup.py,v 1.1 2008-10-16 22:56:17 ghantoos Exp $

from distutils.core import setup

if __name__ == '__main__':

	setup(name='lshell',
		version='0.2',
		description='Limited Shell',
		long_description="""Limited Shell (lshell) is lets you restrict the environment of any user. It provides an easily configurable shell: just choose a list of allowed commands for every limited account.""",
		author='Ignace Mouzannar -ghantoos-',
		author_email='ghantoos@ghantoos.org',
		maintainer='Ignace Mouzannar -ghantoos-',
		maintainer_email='ghantoos@ghantoos.org',
		keywords=['limited','shell','security','python'],
		url='http://ghantoos.org/',
		license='GPL',
		scripts = ['bin/lshell'],
		package_dir = {'':'lshellmodule'},
		packages = [''],
		data_files = [('/etc', ['etc/lshell.conf']), ('share/doc/lshell',['README', 'COPYING', 'CHANGES']), ('/var/log',['log/lshell.log'])]
	)

