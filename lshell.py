#!/usr/bin/env python
#
#    Limited command Shell (lshell)
#  
#    $Id: lshell.py,v 1.2 2008-01-27 01:09:33 ghantoos Exp $
#
#    "Copyright 2008 Ignace Mouzannar ( http://ghantoos.org )"
#    Email: admin@ghantoos.org
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


# Global Variable config_list listing the required configuration fields per user
config_list = ['passwd', 'allowed', 'forbidden', 'warning_counter', 'timer']


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
		self.intro = 'Welcome to lshell!'		

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
		if self.g_cmd in ['quit', 'exit', 'EOF']:
			print '\nExiting..'
			sys.exit(1)
		elif self.g_cmd in allowed:
			os.system(self.g_line)
		elif self.g_cmd != '' : self.stdout.write('*** Unknown syntax: %s\n'%self.g_cmd) 
		self.g_cmd, self.g_arg, self.g_line = ['', '', ''] 
		return object.__getattribute__(self, attr)

	def check_secure(self,line):
		"""This method is used to check the content on the typed command.
		Its purpose is to forbid the user to user to override the lshell
		command restrictions. 
		The forbidden characters are placed in the 'forbidden' global variable.
		Feel free to update the list. Emptying it would be quite useless..: )

		A warining counter has been added, to kick out of lshell a user if he
		is warned more than X time. X beeing the 'forbidden_counter' global variable)
		"""
		for item in forbidden:
			if item in self.g_line:
				global warning_counter
				warning_counter -= 1
				if warning_counter == 0: 
					print 'I warned you.. See ya!'
					sys.exit(1)
				else:
					print 'WARNING: What are you trying to do??'
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
		"""This method overrides the original emptyline method, so i doesn't repeat the 
		last command if last command was empty.
		I just found this annoying..
		"""
		if self.lastcmd:
			return 0

	def mytimer():
		""" This function is suppose to kick you out the the lshell after the 'timer' variable
		exprires. 'timer' is set in seconds.

		This function is still bugged as it creates a thread with the timer, then only kills 
		the thread and not the whole process.HELP!
		"""  
		print "Time's up! Exiting..\n"
		exit(2)

	def getconfig(user):
		return 0


class check_config():

	def __init__(self):
		""" Force the calling of the methods below
		""" 
		self.usage()
		self.check_file()
		self.check_config_user()
		self.get_config_user()

	def usage(self):
		""" This method checks the usage. lshell.py must be called with a configuration file.
		"""
		if len(sys.argv) != 2:
		    print "Usage: ./lshell.py /path/to/config/file"
		    exit(0)

	def check_file(self):
		""" This method checks the existence of the "argumently" given configuration file.
		"""
		self.config_file = sys.argv[1]
		if os.path.exists(self.config_file) is False : 
			print "Error: Config file doesn't exist"
			exit(0)
		else: self.config = ConfigParser.ConfigParser()

	def check_config_user(self):
		""" This method checks if the current user exists in the configuration file.
		If the user is not found, he is exited from lshell.
		If the user is found, it continues by calling check_user_integrity() then check_passwd()
		"""
		self.config.read(self.config_file)
		self.user = getuser() # to use getpass._raw_input('Enter username: '), 'username' must be entered in list_config
		if self.config.has_section(self.user) is False:
			print 'Error: Unknown user!'
			sys.exit(0)
		else:
			self.check_user_integrity()
			self.check_passwd()

	def check_user_integrity(self):
		""" This method checks if all the required fields by user are present for the present user.
		In case fields are missing, the user is notified and exited from lshell
		"""
		global config_list
		quit = 0
		for item in config_list:
			if self.config.has_option(self.user, item) is False:
				print 'Error: Missing parameter "' + item + '" for user ' + self.user
				quit = 1
		if quit is 1: sys.exit(0)

	def check_passwd(self):
		""" As a passwd field is required by user. This method checks in the configuration file
		if the password is empty, in wich case, no passwrd check is required. In the other case,
		the password is asked to be entered.
		If the entered password is wrong, the user is exited from lshell.
		"""
		passwd = self.config.get(self.user, 'passwd')
		if passwd is '' : return 0
		else:
			password = getpass("Enter password :")
			if password != passwd:
				print 'Error: Wrong password \nExiting..'
				exit(0)

	def get_config_user(self):
		""" Once all the checks above have passed, the configuration files values are entered
		in global variables to be used by the command line it self. The lshell command line
		is then launched!
		"""
		self.config.read(self.config_file)
		global allowed, forbidden, warning_counter, timer, username
		allowed = eval(self.config.get(self.user, 'allowed'))
		allowed.extend(['quit', 'EOF'])
		forbidden = eval(self.config.get(self.user, 'forbidden'))
		warning_counter = eval(self.config.get(self.user, 'warning_counter'))
		timer = eval(self.config.get(self.user, 'timer'))
		username = self.user


if __name__=='__main__':

	try:
		check_config()
		cli = shell_cmd()
		cli.cmdloop()

	except KeyboardInterrupt:
		sys.exit(0)

