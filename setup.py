#!/usr/bin/env python
#
# $Id: setup.py,v 1.11 2009-03-02 21:32:57 ghantoos Exp $

from distutils.core import setup

if __name__ == '__main__':

    setup(name='lshell',
        version='0.2.6',
        description='Limited Shell',
        long_description="""Limited Shell (lshell) is lets you restrict the \
environment of any user. It provides an easily configurable shell: just \
choose a list of allowed commands for every limited account.""",
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
        packages = ['lshell'],
        data_files = [(conf_path, ['etc/lshell.conf']), 
            ('share/doc/lshell',['README', 'COPYING', 'CHANGES']),
            ('share/man/man1/', ['man/lshell.1.gz']) ]
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
