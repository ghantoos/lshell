#!/usr/bin/env python
#
# $Id: setup.py,v 1.32 2010-10-17 15:47:21 ghantoos Exp $
#
#    Copyright (C) 2008-2009  Ignace Mouzannar (ghantoos) <ghantoos@ghantoos.org>
#
#    This file is part of lshell
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from distutils.core import setup

if __name__ == '__main__':

    setup(name='lshell',
          version='0.9.16',
          description='Limited Shell',
          long_description="""Limited Shell (lshell) is lets you restrict the \
environment of any user. It provides an easily configurable shell: just \
choose a list of allowed commands for every limited account.""",
          author='Ignace Mouzannar (ghantoos)',
          author_email='ghantoos@ghantoos.org',
          maintainer='Ignace Mouzannar (ghantoos)',
          maintainer_email='ghantoos@ghantoos.org',
          keywords=['limited','shell','security','python'],
          url='http://ghantoos.org/limited-shell-lshell/',
          license='GPL',
          platforms='UNIX',
          scripts = ['bin/lshell'],
          package_dir = {'':'lshell'},
          packages = [''],
          data_files = [('/etc', ['etc/lshell.conf']),
                        ('/etc/logrotate.d', ['etc/logrotate.d/lshell']),
                        ('share/doc/lshell',['README', 'COPYING', 'CHANGES']),
                        ('share/man/man1/', ['man/lshell.1']) ],
          classifiers=[
            'Development Status :: 4 - Beta',
            'Environment :: Console'
            'Intended Audience :: Advanced End Users',
            'Intended Audience :: System Administrators',
            'License :: OSI Approved :: GNU General Public License v3',
            'Operating System :: POSIX',
            'Programming Language :: Python',
            'Topic :: Security',
            'Topic :: System Shells',
            'Topic :: Terminals'
            ],
          )
