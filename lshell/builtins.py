#
#  Limited command Shell (lshell)
#
#  Copyright (C) 2008-2013 Ignace Mouzannar (ghantoos) <ghantoos@ghantoos.org>
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

import glob
import sys
import os
import readline

# import lshell specifics
from lshell import variables
from lshell import utils


def lpath(conf):
    """ lists allowed and forbidden path
    """
    if conf['path'][0]:
        sys.stdout.write("Allowed:\n")
        lpath_allowed = conf['path'][0].split('|')
        lpath_allowed.sort()
        for path in lpath_allowed:
            if path:
                sys.stdout.write(" %s\n" % path[:-2])
    if conf['path'][1]:
        sys.stdout.write("Denied:\n")
        lpath_denied = conf['path'][1].split('|')
        lpath_denied.sort()
        for path in lpath_denied:
            if path:
                sys.stdout.write(" %s\n" % path[:-2])
    return 0


def lsudo(conf):
    """ lists allowed sudo commands
    """
    if 'sudo_commands' in conf \
       and len(conf['sudo_commands']) > 0:
        sys.stdout.write("Allowed sudo commands:\n")
        for command in conf['sudo_commands']:
            sys.stdout.write(" - %s\n" % command)
        return 0
    else:
        sys.stdout.write("No sudo commands allowed\n")
        return 1


def history(conf, log):
    """ print the commands history
    """
    try:
        try:
            readline.write_history_file(conf['history_file'])
        except IOError:
            log.error('WARN: couldn\'t write history '
                      'to file %s\n' % conf['history_file'])
            return 1
        f = open(conf['history_file'], 'r')
        i = 1
        for item in f.readlines():
            sys.stdout.write("%d:  %s" % (i, item))
            i += 1
    except:
        log.critical('** Unable to read the history file.')
        return 1
    return 0


def export(args):
    """ export environment variables """
    # if command contains at least 1 space
    if args.count(' '):
        env = args.split(" ", 1)[1]
        # if it contains the equal sign, consider only the first one
        if env.count('='):
            var, value = env.split(' ')[0].split('=')[0:2]
            # disallow dangerous variable
            if var in variables.FORBIDDEN_ENVIRON:
                return 1, var
            os.environ.update({var: value})
    return 0, None


def cd(directory, conf):
    """ implementation of the "cd" command
    """
    # expand user's ~
    directory = os.path.expanduser(directory)

    # remove quotes if present
    directory = directory.strip("'").strip('"')

    if len(directory) >= 1:
        # add wildcard completion support to cd
        if directory.find('*'):
            # get all files and directories matching wildcard
            wildall = glob.glob(directory)
            wilddir = []
            # filter to only directories
            for item in wildall:
                if os.path.isdir(item):
                    wilddir.append(item)
            # sort results
            wilddir.sort()
            # if any results are returned, pick first one
            if len(wilddir) >= 1:
                directory = wilddir[0]
        # go previous directory
        if directory == '-':
            directory = conf['oldpwd']

        # store current directory in oldpwd variable
        conf['oldpwd'] = os.getcwd()

        # change directory
        try:
            os.chdir(os.path.realpath(directory))
            conf['promptprint'] = utils.updateprompt(os.getcwd(), conf)
        except OSError as excp:
            sys.stdout.write("lshell: %s: %s\n" % (directory,
                                                   excp.strerror))
            return excp.errno, conf
    else:
        os.chdir(conf['home_path'])
        conf['promptprint'] = utils.updateprompt(os.getcwd(), conf)

    return 0, conf
