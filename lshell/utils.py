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
