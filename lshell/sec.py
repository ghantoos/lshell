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

import sys
import re
import os

# import lshell specifics
from lshell import utils


def warn_count(messagetype, command, conf, strict=None, ssh=None):
    """ Update the warning_counter, log and display a warning to the user
    """

    log = conf['logpath']
    if not ssh:
        if strict:
            conf['warning_counter'] -= 1
            if conf['warning_counter'] < 0:
                log.critical('*** forbidden %s -> "%s"'
                             % (messagetype, command))
                log.critical('*** Kicked out')
                sys.exit(1)
            else:
                log.critical('*** forbidden %s -> "%s"'
                             % (messagetype, command))
                sys.stderr.write('*** You have %s warning(s) left,'
                                 ' before getting kicked out.\n'
                                 % conf['warning_counter'])
                log.error('*** User warned, counter: %s'
                          % conf['warning_counter'])
                sys.stderr.write('This incident has been reported.\n')
        else:
            if not conf['quiet']:
                log.critical('*** forbidden %s: %s'
                             % (messagetype, command))

    # if you are here, means that you did something wrong. Return 1.
    return 1, conf


def check_path(line, conf, completion=None, ssh=None, strict=None):
    """ Check if a path is entered in the line. If so, it checks if user
    are allowed to see this path. If user is not allowed, it calls
    warn_count. In case of completion, it only returns 0 or 1.
    """
    allowed_path_re = str(conf['path'][0])
    denied_path_re = str(conf['path'][1][:-1])

    # split line depending on the operators
    sep = re.compile(r'\ |;|\||&')
    line = line.strip()
    line = sep.split(line)

    for item in line:
        # remove potential quotes or back-ticks
        item = re.sub(r'^["\'`]|["\'`]$', '', item)

        # remove potential $(), ${}, ``
        item = re.sub(r'^\$[\(\{]|[\)\}]$', '', item)

        # if item has been converted to something other than a string
        # or an int, reconvert it to a string
        if type(item) not in ['str', 'int']:
            item = str(item)
        # replace "~" with home path
        item = os.path.expanduser(item)

        # expand shell wildcards using "echo"
        # i know, this a bit nasty...
        if re.findall('\$|\*|\?', item):
            # remove quotes if available
            item = re.sub("\"|\'", "", item)
            import subprocess
            p = subprocess.Popen("`which echo` %s" % item,
                                 shell=True,
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            cout = p.stdout

            try:
                item = cout.readlines()[0].decode('utf8').split(' ')[0]
                item = item.strip()
                item = os.path.expandvars(item)
            except IndexError:
                conf['logpath'].critical('*** Internal error: command not '
                                         'executed')
                return 1, conf

        tomatch = os.path.realpath(item)
        if os.path.isdir(tomatch) and tomatch[-1] != '/':
            tomatch += '/'
        match_allowed = re.findall(allowed_path_re, tomatch)
        if denied_path_re:
            match_denied = re.findall(denied_path_re, tomatch)
        else:
            match_denied = None

        # if path not allowed
        # case path executed: warn, and return 1
        # case completion: return 1
        if not match_allowed or match_denied:
            if not completion:
                ret, conf = warn_count('path',
                                       tomatch,
                                       conf,
                                       strict=strict,
                                       ssh=ssh)
            return 1, conf

    if not completion:
        if not re.findall(allowed_path_re, os.getcwd() + '/'):
            ret, conf = warn_count('path',
                                   tomatch,
                                   conf,
                                   strict=strict,
                                   ssh=ssh)
            os.chdir(conf['home_path'])
            conf['promptprint'] = utils.updateprompt(os.getcwd(),
                                                     conf)
            return 1, conf
    return 0, conf
