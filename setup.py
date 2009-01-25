#!/usr/bin/env python
#
# $Id: setup.py,v 1.9 2009-01-25 22:56:48 ghantoos Exp $

from distutils.core import setup

if __name__ == '__main__':

	setup(name='lshell',
		version='0.2.4',
		description='Limited Shell',
		long_description="""Limited Shell (lshell) is lets you restrict the environment of any user. It provides an easily configurable shell: just choose a list of allowed commands for every limited account.""",
		author='Ignace Mouzannar -ghantoos-',
		author_email='ghantoos@ghantoos.org',
		maintainer='Ignace Mouzannar -ghantoos-',
		maintainer_email='ghantoos@ghantoos.org',
		keywords=['limited','shell','security','python'],
		url='http://ghantoos.org/',
		license='GPL',
		platforms='UNIX',
		scripts = ['bin/lshell'],
		package_dir = {'':'lshellmodule'},
		packages = [''],
		data_files = [('/etc', ['etc/lshell.conf']), 
						('share/doc/lshell',['README', 'COPYING', 'CHANGES']), 
						('share/man/man1/', ['man/lshell.1.gz']) ]
	)

