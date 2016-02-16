#!/usr/bin/env python
#
#  Copyright (C) 2008-2009  Ignace Mouzannar (ghantoos) <ghantoos@ghantoos.org>
#
#  This file is part of lshell
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

from distutils.core import setup

# import lshell specifics
from lshell.variables import __version__

if __name__ == '__main__':

    setup(name='lshell',
          version='%s' % __version__,
          description='Limited Shell',
          long_description="""Limited Shell (lshell) is lets you restrict the \
environment of any user. It provides an easily configurable shell: just \
choose a list of allowed commands for every limited account.""",
          author='Ignace Mouzannar',
          author_email='ghantoos@ghantoos.org',
          maintainer='Ignace Mouzannar',
          maintainer_email='ghantoos@ghantoos.org',
          keywords=['limited', 'shell', 'security', 'python'],
          url='https://github.com/ghantoos/lshell',
          license='GPL',
          platforms='UNIX',
          scripts=['bin/lshell'],
          package_dir={'lshell': 'lshell'},
          packages=['lshell'],
          data_files=[('/etc', ['etc/lshell.conf']),
                      ('/etc/logrotate.d', ['etc/logrotate.d/lshell']),
                      ('share/doc/lshell', ['README.md',
                                            'COPYING',
                                            'CHANGES']),
                      ('share/man/man1/', ['man/lshell.1'])],
          classifiers=[
            'Development Status :: 5 - Production/Stable',
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
