lshell - limited shell
======================

All this information (and more) is in the man file.

Installation:
----------------

You have 3 options:

* Use the setup.py present in the source tar.gz. It uses python distutils to install everything in the right place:
    1. Install from source

            # extract source
            tar xvfz lshell-{version}.tar.gz
            # on Linux:
            python setup.py install --no-compile --install-scripts=/usr/bin/
            # on *BSD:
            python setup.py install --no-compile --install-data=/usr/{pkg,local}/
    2.  Install the rpm

            yum install lshell
            # or 
            rpm -Uvh lshell-x.x-x.noarch.rpm
    3. Install the .deb

            apt-get install lshell
            # or
            dpkg -i lshell-x.x-x.deb


Configuration:
------------------------

lshell.conf presents a template configuration file. See etc/lshell.conf or man file for more information.

A [default] profile is available for all users using lshell. Nevertheless,  you can create a [username] section or a [grp:groupname] section to customize users' preferences.

Order of priority when loading preferences is the following:

1. User configuration
2. Group configuration
3. Default configuration


The primary goal of lshell, was to be able to create shell accounts with ssh access and restrict their environment to a couple a needed commands.
 
For example User 'foo' and user 'bar' both belong to the 'users' UNIX group:

- User 'foo': 
       - must be able to access /usr and /var but not /usr/local
       - user all command in his PATH but 'su'
       - has a warning counter set to 5
       - has his home path set to '/home/users'

- User 'bar':
       - must be able to access /etc and /usr but not /usr/local
       - is allowed default commands plus 'ping' minus 'ls'
       - strictness is set to 1 (meaning he is not allowed to type an unknown command)

In this case, my configuration file will look something like this:

    # CONFIGURATION START
    [global]
    logpath         : /var/log/lshell/
    loglevel        : 2

    [default]
    allowed         : ['ls','pwd']
    forbidden       : [';', '&', '|'] 
    warning_counter : 2
    timer           : 0
    path            : ['/etc', '/usr']
    env_path        : ':/sbin:/usr/foo'
    scp             : 1 # or 0
    sftp            : 1 # or 0
    overssh         : ['rsync','ls']
    aliases         : {'ls':'ls --color=auto','ll':'ls -l'}

    [grp:users]
    warning_counter : 5
    overssh         : - ['ls']

    [foo]
    allowed         : 'all' - ['su']
    path            : ['/var', '/usr'] - ['/usr/local']
    home_path       : '/home/users'

    [bar]
    allowed         : + ['ping'] - ['ls'] 
    path            : - ['/usr/local']
    strict          : 1
    scpforce        : '/home/bar/uploads/'
    # CONFIGURATION END


Usage:
--------------

To launch lshell, just execute lshell specifying the location of your configuration file:

    lshell --config /path/to/configuration/file

By default lshell will try to launch using /${CONFPATH}/lshell.conf unless specified otherwise (using --config), where ${CONFPATH} is :

- "/etc/" for Linux
- "/usr/{pkg,local}/etc/" for *BSD

In order to log a user, you will have to add him to the lshellg group:

    usermod -aG lshellg username


Use case 1: /etc/passwd
----------------------------------------
In order to configure a user account to use lshell by default, you must:

- On Linux:

        chsh -s /usr/bin/lshell user_name

- On *BSD:

        chsh -s /usr/{pkg,local}/bin/lshell user_name

After this, whichever method is used by the user to log into his account, he will end up using the limited shell you configured for him!

Use case 2: OpenSSH & authorized_keys
-----------------------------------------------------------------
    
In order to launch lshell limited to the 'ssh' command, I used ssh's authorized_keys:

    # vi /home/foo/.ssh/authorized_keys
    # and add :
    command="/usr/bin/lshell --config /path/to/lshell.conf",no-port-for warding,no-X11-forwarding,no-agent-forwarding,no-pty just before the public key part.

This will have the effect of executing lshell upon user's SSH connection. 

Contact
----------------
If you want to contribute to this project, please do not hesitate. Open an issue and, if possible, send a patch! I would be glad to take a look at it!

You can use the interface on github: ghantoos/lshell/issues

Cheers,

 Ignace Mouzannar <ghantoos@ghantoos.org>
