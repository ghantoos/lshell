#!/usr/bin/env python
#
# $Id: setup.py,v 1.10 2009-02-15 18:46:58 ghantoos Exp $

from distutils.core import setup
from distutils.command import install
import getopt
import sys
import os

def process(arguments):
    """ Set configuration, documentation, and manpage path """

    # Linux default path - debian and redhat
    conf_path = '/etc'
    doc_path = 'share/doc'
    man_path = 'share/man'

    # In case of install, check if --install-data= present.
    # If specified, update values of conf_path, doc_path, man_path.
    #
    # --install-data=PKG_PATH is used for *BSD installations
    if arguments[0] == 'install':
        # get all possible 'install' options from distutils/command/install.py
        install_options = []
        for item in install.install.user_options:
            install_options.append(item[0])

        optlist, args = getopt.getopt(arguments[1:], '', install_options)
        for option, value in optlist:
            if option in ['--install-data']:
                data_path = os.path.realpath(value)

                conf_path = os.path.join(data_path, 'etc')
                doc_path = os.path.join(data_path, 'share')
                man_path = os.path.join(data_path, 'man')

    return conf_path, doc_path, man_path


def main(conf_path, doc_path, man_path):

    setup(name='lshell',
        version='0.2.5',
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
        packages = [''],
        data_files = [(conf_path, ['etc/lshell.conf']), 
            (os.path.join(doc_path,'lshell') ,['README', 'COPYING', 'CHANGES']), 
            (os.path.join(man_path, 'man1') , ['man/lshell.1.gz']) ]
    )

if __name__ == '__main__':

    conf_path, doc_path, man_path = process(sys.argv[1:])
    main(conf_path, doc_path, man_path)

