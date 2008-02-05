#!/usr/bin/env python
#
#    Limited command Shell (lshell)
#  
#    $Id: lshell.py,v 1.7 2008-02-05 19:51:41 ghantoos Exp $
#
#    "Copyright 2008 Ignace Mouzannar ( http://ghantoos.org )"
#    Email: ghantoos@ghantoos.org
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


import cmd
import sys
import os
import ConfigParser
from threading import Timer
from getpass import getpass, getuser
import termios


# Global Variable config_list listing the required configuration fields per user
config_list = ['passwd', 'allowed', 'forbidden', 'warning_counter', 'timer','path','scp']

# help text
help = """------------------------------------------------------------------------
Limited Shell (lshell):
 - Specify a configuration file using: ./lshell.py /path/to/config/file
 - Else, lshell.conf will be used by default

For more specifications, please refer to the README.
------------------------------------------------------------------------
"""

help_help = """Limited Shell (lshell) limited help.
Cheers.
"""

# Intro Text
intro = """------------------
Welcome to lshell!
------------------
Type '?' or 'help' to get the list of allowed commands"""

class shell_cmd(cmd.Cmd,object): 

	def __init__(self):
		""" This methohd uses the 'username' global variable, to put it in the prompt.
		The whole idea here, is just to embellish the lshell..: )
		"""
		if (timer > 0): 
			t = Timer(2, self.mytimer)
			t.start()
		cmd.Cmd.__init__(self)
		self.prompt = username+':-$ '
		self.intro = intro

	def __getattr__(self, attr):
		"""This is the heart of lshell!
		This method actually takes care of all the called method that are 
		not resolved (i.e not existing methods). It actually will simulate
		the existance of any method	entered in the 'allowed' global variable list.

		e.g. You just have to add 'uname' in list of allowed commands in 
		the 'allowed' global variable, and lshell will react as if you had 
		added a do_uname in the shell_cmd class!
		"""
		if self.check_secure(self.g_line) == 0: return object.__getattribute__(self, attr)
		if self.check_path(self.g_line) == 0: return object.__getattribute__(self, attr)
		if self.g_cmd in ['quit', 'exit', 'EOF']:
			self.stdout.write('\nExiting..\n')
			sys.exit(1)
		elif self.g_cmd in allowed:
			os.system(self.g_line)
		elif self.g_cmd not in ['','?','help'] : self.stdout.write('*** Unknown syntax: %s\n'%self.g_cmd) 
		self.g_cmd, self.g_arg, self.g_line = ['', '', ''] 
		return object.__getattribute__(self, attr)

	def check_secure(self,line):
		"""This method is used to check the content on the typed command.
		Its purpose is to forbid the user to user to override the lshell
		command restrictions. 
		The forbidden characters are placed in the 'forbidden' global variable.
		Feel free to update the list. Emptying it would be quite useless..: )

		A warining counter has been added, to kick out of lshell a user if he
		is warned more than X time (X beeing the 'forbidden_counter' global variable).
		"""
		for item in forbidden:
			if item in line:
				global warning_counter
				warning_counter -= 1
				if warning_counter <= 0: 
					self.stdout.write('I warned you.. See ya!\n')
					sys.exit(1)
				else:
					self.stdout.write('WARNING: What are you trying to do??\n')
				return 0

	def check_path(self, line):
		import string, re
		line = line.strip().split(' ')
		for item in line:
			if '/' in item:
				path_re = re.compile('('+string.join(path,'|')+')')
				match = path_re.match(item)
				if not match : 
					self.check_secure(forbidden[0])
					return 0

	def default(self, line):
		""" This method overrides the original default method. This method was originally used to
		warn when an unknown command was entered (*** Unknown syntax: blabla)
		It has been implemented in the __getattr__ method.
		So it has no use here. Its output is now empty.
		"""
		self.stdout.write('')

	def completenames(self, text, *ignored):
		""" This method overrides the original  completenames method to overload it's output
		with the command available in the 'allowed' variable
		This is useful when typing 'tab-tab' in the command prompt
		"""
		dotext = 'do_'+text
		names = self.get_names()
		for command in allowed: 
			names.append('do_' + command)
		return [a[3:] for a in names if a.startswith(dotext)]

	def onecmd(self, line):
		""" This method overrides the original onecomd method, to put the cmd, arg and line 
		variables in class global variables: self.g_cmd, self.g_arg and self.g_line
		Thos variables are then used by the __getattr__ method
		"""
		cmd, arg, line = self.parseline(line)
		self.g_cmd, self.g_arg, self.g_line = [cmd, arg, line] 
		if not line:
			return self.emptyline()
		if cmd is None:
			return self.default(line)
		self.lastcmd = line
		if cmd == '':
			return self.default(line)
		else:
			try:
				func = getattr(self, 'do_' + cmd)
			except AttributeError:
				return self.default(line)
			return func(arg)

	def emptyline(self):
		""" This method overrides the original emptyline method, so i doesn't repeat the 
		last command if last command was empty.
		I just found this annoying..
		"""
		if self.lastcmd:
			return 0

	def do_help(self, arg):
		""" This method overrides the original do_help method. Instead of printing out the
		that are documented or not, it returns the list of allowed commands when '?' or
		'help' is entered. Of course, it doesn't override the help function: any help_*
		method will be called (e.g. help_help(self) )
		""" 
		if arg:
			try:
				func = getattr(self, 'help_' + arg)
			except AttributeError:
				try:
					doc=getattr(self, 'do_' + arg).__doc__
					if doc:
						self.stdout.write("%s\n"%str(doc))
						return
				except AttributeError:
					pass
				self.stdout.write("%s\n"%str(self.nohelp % (arg,)))
				return
			func()
		else:
			# Get list of allowed commands, removes duplicate 'help' then sorts it
			list_tmp = dict.fromkeys(self.completenames('')).keys()
			list_tmp.sort()
			self.columnize(list_tmp)

	def help_help(self):
		self.stdout.write(help_help)

	def mytimer(self):
		""" This function is suppose to kick you out the the lshell after the 'timer' variable
		exprires. 'timer' is set in seconds.

		This function is still bugged as it creates a thread with the timer, then only kills 
		the thread and not the whole process.HELP!
		"""  
		self.stdout.write("Time's up! Exiting..\n")
		exit(0)


class check_config():

	def __init__(self, stdin=None, stdout=None):
		""" Force the calling of the methods below
		""" 
		if stdin is None:
			self.stdin = sys.stdin
		else:
			self.stdin = stdin
		if stdout is None:
			self.stdout = sys.stdout
		else:
			self.stdout = stdout

		self.config_file = self.usage()
		self.check_file(self.config_file)
		self.check_config_user()
		self.get_config_user()
		self.check_user_integrity()
		self.check_scp()
		self.check_passwd()

	def usage(self):
		""" This method checks the usage. lshell.py must be called with a configuration file.
		"""
		if len(sys.argv) < 2:
			#self.stdout.write('No config file specified. Using default file.\n')
			return 'lshell.conf'
		elif len(sys.argv) > 2 or sys.argv[1] in ['-h', '--help']:
			self.stdout.write(help)
			sys.exit(0)
		else: return sys.argv[1]

	def check_file(self, config_file):
		""" This method checks the existence of the "argumently" given configuration file.
		"""
		if os.path.exists(self.config_file) is False : 
			self.stdout.write("Error: Config file doesn't exist\n")
			sys.exit(0)
		else: self.config = ConfigParser.ConfigParser()

	def check_config_user(self):
		""" This method checks if the current user exists in the configuration file.
		If the user is not found, he is exited from lshell.
		If the user is found, it continues by calling check_user_integrity() then check_passwd()
		"""
		self.config.read(self.config_file)
		self.user = getuser() # to use getpass._raw_input('Enter username: '), 'username' must be entered in list_config
		if self.config.has_section(self.user) is False:
			self.stdout.write('Error: Unknown user "'+self.user+'"\n')
			sys.exit(0)

	def check_user_integrity(self):
		""" This method checks if all the required fields by user are present for the present user.
		In case fields are missing, the user is notified and exited from lshell
		"""
		global config_list
		quit = 0
		for item in config_list:
			if self.config.has_option(self.user, item) is False:
				self.stdout.write('Error: Missing parameter "' + item + '" for user ' + self.user + '\n')
				quit = 1
		if quit is 1: sys.exit(0)

	def get_config_user(self):
		""" Once all the checks above have passed, the configuration files values are entered
		in global variables to be used by the command line it self. The lshell command line
		is then launched!
		"""
		self.config.read(self.config_file)
		global username, allowed, forbidden, warning_counter, timer, path, scp
		username = self.user
		allowed = eval(self.config.get(self.user, 'allowed'))
		allowed.extend(['quit', 'EOF'])
		forbidden = eval(self.config.get(self.user, 'forbidden'))
		warning_counter = eval(self.config.get(self.user, 'warning_counter'))
		timer = eval(self.config.get(self.user, 'timer'))
		path = eval(self.config.get(self.user, 'path'))
		scp = eval(self.config.get(self.user, 'scp'))

	def check_scp(self):
		""" This method checks if the user is trying to SCP a file onto the server.
		If this is the case, it checks if the user is allowed to use SCP or not, and
		acts as requested. : )
		The detection part is a bit weird, but it works! (I still need your help if you've 
		got any idea). Actually, if I'm not wrong 'fd' the value of the file descriptor 
		associated with the stream, and termios.tcgetattr should return a list containing 
		the tty attributes for my file descriptor. In the case of scp, no there no tty attributes,
		so the command returns an error wich gets us to the except part, which deals with the scp.
		"""
		try:
			fd = sys.stdin.fileno()
			test = termios.tcgetattr(fd)
		except termios.error:
			if scp is 1: 
				os.system('scp -t .')
				sys.exit(0)
			else:
				self.stdout.write('Sorry..You are not allowed to use SCP.\n')
				sys.exit(0)

	def check_passwd(self):
		""" As a passwd field is required by user. This method checks in the configuration file
		if the password is empty, in wich case, no passwrd check is required. In the other case,
		the password is asked to be entered.
		If the entered password is wrong, the user is exited from lshell.
		"""
		passwd = self.config.get(self.user, 'passwd')
		if passwd is '' : return 0
		else:
			password = getpass("Enter "+self.user+"'s password: ")
			if password != passwd:
				self.stdout.write('Error: Wrong password \nExiting..\n')
				sys.exit(0)


if __name__=='__main__':

	try:
		check_config()
		cli = shell_cmd()
		cli.cmdloop()

	except (KeyboardInterrupt, EOFError):
		sys.stdout.write('\nExited on user request\n')
		sys.exit(0)

