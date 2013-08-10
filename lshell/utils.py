#
#    Limited command Shell (lshell)
#  
#    Copyright (C) 2008-2013 Ignace Mouzannar (ghantoos) <ghantoos@ghantoos.org>
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

import re

try:
    from os import urandom
except:
    def urandom(n):
        try:
            _urandomfd = open("/dev/urandom", 'r')
        except Exception,e:
            print e
            raise NotImplementedError("/dev/urandom (or equivalent) not found")
        bytes = ""
        while len(bytes) < n:
            bytes += _urandomfd.read(n - len(bytes))
        _urandomfd.close()
        return bytes


def get_aliases(line, aliases):
    """ Replace all configured aliases in the line
    """

    for item in aliases.keys():
        reg1 = '(^|; |;)%s([ ;&\|]+|$)(.*)' % item
        reg2 = '(^|; |;)%s([ ;&\|]+|$)' % item

        # in case aliase bigin with the same command
        # (this is until i find a proper regex solution..)
        aliaskey = urandom(10)

        while re.findall(reg1, line):
            (before, after, rest) = re.findall(reg1, line)[0]
            linesave = line
            cmd = "%s %s" % (item, rest)

            line = re.sub(reg2, "%s%s%s" % (before, aliaskey,       \
                                                     after), line, 1)
            # if line does not change after sub, exit loop
            if linesave == line:
                break
        # replace the key by the actual alias
        line = line.replace(aliaskey, aliases[item])

    for char in [';']:
        # remove all remaining double char
        line = line.replace('%s%s' %(char, char), '%s' %char)
    return line
