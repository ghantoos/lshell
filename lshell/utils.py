#
#    Limited command Shell (lshell)
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

import re
import subprocess
import os
import sys
from getpass import getuser

# import lshell specifics
from lshell import variables


def usage():
    """ Prints the usage """
    sys.stderr.write(variables.usage)
    sys.exit(0)


def version():
    """ Prints the version """
    sys.stderr.write('lshell-%s - Limited Shell\n' % variables.__version__)
    sys.exit(0)


def random_string(length):
    """ generate a random string """
    import random
    import string
    randstring = ''
    for char in range(length):
        char = random.choice(string.ascii_letters + string.digits)
        randstring += char

    return randstring


def get_aliases(line, aliases):
    """ Replace all configured aliases in the line
    """

    for item in aliases.keys():
        escaped_item = re.escape(item)
        reg1 = '(^|;|&&|\|\||\|)\s*%s([ ;&\|]+|$)(.*)' % escaped_item
        reg2 = '(^|;|&&|\|\||\|)\s*%s([ ;&\|]+|$)' % escaped_item

        # in case alias begins with the same command
        # (this is until i find a proper regex solution..)
        aliaskey = random_string(10)

        while re.findall(reg1, line):
            (before, after, rest) = re.findall(reg1, line)[0]
            linesave = line

            line = re.sub(reg2, "%s %s%s" % (before,
                                             aliaskey,
                                             after), line, 1)

            # if line does not change after sub, exit loop
            if linesave == line:
                break

        # replace the key by the actual alias
        line = line.replace(aliaskey, aliases[item])

    for char in [';']:
        # remove all remaining double char
        line = line.replace('%s%s' % (char, char), '%s' % char)
    return line


def exec_cmd(cmd):
    """ execute a command, locally catching the signals """
    try:
        retcode = subprocess.call("%s" % cmd, shell=True)
    except KeyboardInterrupt:
        # exit code for user terminated scripts is 130
        retcode = 130

    return retcode


def getpromptbase(conf):
    """ get prompt used by the shell
    """
    if 'prompt' in conf:
        promptbase = conf['prompt']
        promptbase = promptbase.replace('%u', getuser())
        promptbase = promptbase.replace('%h', os.uname()[1].split('.')[0])
    else:
        promptbase = getuser()

    return promptbase


def updateprompt(path, conf):
    """ Set actual prompt to print, updated when changing directories
    """

    # get initial promptbase (from configuration)
    promptbase = getpromptbase(conf)

    # update the prompt when directory is changed
    if path == conf['home_path']:
        prompt = '%s:~$ ' % promptbase
    elif conf['prompt_short'] == 1:
        prompt = '%s: %s$ ' % (promptbase,
                               path.split('/')[-1])
    elif conf['prompt_short'] == 2:
        prompt = '%s: %s$ ' % (promptbase, os.getcwd())
    elif re.findall(conf['home_path'], path):
        prompt = '%s:~%s$ ' % (promptbase,
                               path.split(conf['home_path'])[1])
    else:
        prompt = '%s:%s$ ' % (promptbase, path)

    return prompt
