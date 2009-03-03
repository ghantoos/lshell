#!/usr/bin/env python
#
# $Id: setup.py,v 1.15 2009-03-03 23:38:20 ghantoos Exp $

from distutils.core import setup

if __name__ == '__main__':

    setup(name='lshell',
        version='0.2.7',
        description='Limited Shell',
        long_description="""Limited Shell (lshell) is lets you restrict the \
environment of any user. It provides an easily configurable shell: just \
choose a list of allowed commands for every limited account.""",
        author='Ignace Mouzannar -ghantoos-',
        author_email='ghantoos@ghantoos.org',
        maintainer='Ignace Mouzannar -ghantoos-',
        maintainer_email='ghantoos@ghantoos.org',
        keywords=['limited','shell','security','python'],
        url='http://ghantoos.org/limited-shell-lshell/',
        license='GPL',
        platforms='UNIX',
        scripts = ['bin/lshell'],
        package_dir = {'':'lshellmodule'},
        packages = [''],
        data_files = [('/etc', ['etc/lshell.conf']),
            ('share/doc/lshell',['README', 'COPYING', 'CHANGES']),
            ('share/man/man1/', ['man/lshell.1.gz']) ],
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
