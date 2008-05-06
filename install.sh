#!/usr/bin/env bash
#
# Limited Shell (lshell) installation script
#
# $Id: install.sh,v 1.1 2008-05-06 10:10:26 ghantoos Exp $
#
# This script will:
#       - Create /usr/local/lshell/ directory
#       - Copy lshell.py, CHANGES, README & COPYING in 
#         /usr/local/lshell/
#       - Copy lshell.conf in /etc/
#
# This script needs to be run with root priviledges

INSTALLDIR="/usr/local/lshell/"
CONFIGDIR="/etc/"

press_any_key() {
	echo "-- press any key to continue --"
	read -n1 -t10 anykey
}

check_os() {
	# Check what is the OS install.sh is being executed on
	# It is for the moment compatible with Debian based and 
	# RedHat based architectures.

	OS=`uname -s`
	if [ "${OS}" = "Linux" ] ; then
		if [ -f /etc/redhat-release ] ; then
			INSTALL="yum -y install"
			CHECKPYTHON="rpm -q --queryformat '%{name}' python"
		elif [ -f /etc/SUSE-release ] ; then
			INSTALL="yast -i "
			CHECKPYTHON="rpm -q --queryformat '%{name}' python"
		elif [ -f /etc/mandrake-release ] ; then
			INSTALL="yum -y install"
			CHECKPYTHON="rpm -q --queryformat '%{name}' python"
		elif [ -f /etc/debian_version ] ; then
			INSTALL="apt-get -y install"
			CHECKPYTHON="dpkg-query -W -f=\'\${Package}\' python"
		fi
	else
		echo "Sorry, this installer is not compatible with your OS."
		echo -e "Please refer to the README file for information. \n"
		exit
	fi
}

check_python() {
	# Check if python packages are installed on the machine

	echo -n "checking for python installation..."
	rc=`${CHECKPYTHON}`
	if [ "${rc}" != "'python'" ]; then
		echo "${warn} not installed"
		echo -n "${question} install $1 ? [y/N] "
		read inst
		if [ "${inst}" == "y" ];then
			echo -n "installing $1..."
			${INSTALL} python >/dev/null 2>&1
			echo "done."
		fi
	else
		echo "OK"
	fi
}


install_menu(){
	# First installation menu

	while [ "${choice}" != "q" ]; do
		echo "----------------------------------------------"
		echo "[1] Install or update lshell ${INSTALLSTATUS}"
		echo "[2] Add / manage lshell users"
		echo "[q] Quit"
		echo "----------------------------------------------"
		echo -n "Your choice: "
		read choice
		case $choice in
			1)
				install_lshell
				;;
			2)
				user_menu
				;;
			q)
				echo "Exiting.."
				exit
				;;
		esac
	done
}

install_lshell() {
	# Installation of lshell

	echo -n "Enter install path [${INSTALLDIR}]: "
	read path
	if [ $path ]; then
		$INSTALLDIR = $path
	fi

	# configuration directory
	echo -n "Enter configuration path [${CONFIGDIR}]: "
	read path
	if [ $path ]; then
		$CONFIGDIR = $path
	fi

	# files copying
	test ! -d $INSTALLDIR && mkdir $INSTALLDIR
	echo -n "Copying files to ${INSTALLDIR}.."
	cp CHANGES COPYING lshell.py README $INSTALLDIR
	echo "done"
	echo -n "Copying files to ${CONFIGDIR}.."
	test -d $CONFIGDIR && mkdir $INSTALLDIR
	cp lshell.conf $CONFIGDIR
	echo "done"

	# adding lshell to /etc/shells
	echo -n "Adding lshell to /etc/shells.."
	shell_exist=`grep ${INSTALLDIR}lshell.py /etc/shells`
	if [ ! $shell_exist ]; then
		echo $INSTALLDIR"lshell.py" >> /etc/shells
		echo "done"
	else
		echo "already existed"
	fi
	INSTALLSTATUS="[done]"
	install_menu
}

user_menu() {
	# User configuration menu

	while [ "${choice}" != "q" ]; do
		echo "----------------------------------------------"
		echo "[1] Create new user using lshell as main shell"
		echo "[2] Change existing user's main shell"
		echo "[3] Reset user's lshell configuration"
		echo "[4] List users currently using lshell.py"
		echo "[q] Quit"
		echo "----------------------------------------------"
		echo -n "Your choice: "
		read choice
		case $choice in
			1)
				user_add
				;;
			2)
				user_modify
				;;
			3)
				user_reset
				;;
			4)
				user_list
				;;
			q)
				echo "Exiting.."
				exit
				;;
			*)
				echo -e "## Let's try it again.. ##"
				;;
		esac
	done
}

user_add() {
	# [1] Create new user using lshell as main shell

	echo -n "Enter the new username: "
	read username
	user_exist=`cat /etc/passwd | cut -d ":" -f1 | grep -w ${username}`
	if [ $user_exist ]; then
		# case user already exists
		echo "! ERROR: User ${username} already exists."
		echo "! ERROR: Try option [2] of next menu"
		press_any_key
	else
		# creates the new user and starts lshell configuration
		useradd -m -s $INSTALLDIR"lshell.py" $username
		passwd $username
		user_config $username
	fi
}

user_modify() {
	# [2] Change existing user's main shell and set his lshell configuration

	echo -n "Enter the new username to edit: "
	read username
	user_exist=`cat /etc/passwd | cut -d ":" -f1 | grep -w ${username}`
	if [ ! $user_exist ]; then
		echo "! ERROR: User ${username} does not exist."
		press_any_key
	else
		chsh -s $INSTALLDIR"lshell.py" $username
		user_exist=`grep -e "^\[${username}\]" $CONFIGDIR"lshell.conf"`
		if [ ! $user_exist ]; then
			user_config
		else
			user_reset $username
		fi
	fi
}

writetoconf() {
	echo $* | sed -e 's/_s_/ /g' -e 's/_t_/\t/g' -e 's/_n_//g' >> $CONFIGDIR"lshell.conf.tmp"
}

user_reset(){
	# [3] Reset user's lshell configuration (in lshell.conf)

	match=0
	if [ ! $1 ]; then
		echo -n "Enter the new username to edit: "
		read username
	else username=$1
	fi

	CONFIGCONTENT=`cat ${CONFIGDIR}"lshell.conf" | sed -e 's/ /_s_/g' -e 's/\t/_t_/g' -e 's/^/_n_/g'`
	for line in $CONFIGCONTENT
	do
		if [ $match == 1 ]; then
			[[ ! `echo $line | grep -e '^_n_\[.*\]$' ` == "" ]] && match=0 && writetoconf $line && continue
			[[ $line == "_n_" ]] && writetoconf $line && continue
			echo -n "Value for "`echo $line | sed -e 's/:/{/' -e 's/$/ }/' -e 's/_s_/ /g' -e 's/_t_/\t/g' -e 's/_n_//g'` ":"
			read input
			if [ $input ]; then
				writetoconf `echo $line | cut -d ":" -f1`": ${input}"
			else
				writetoconf $line
			fi
		fi

		[[ $match == 0 ]] && writetoconf $line
		[[ $line ==  "_n_[${username}]" ]] && match=1
	done
	mv $CONFIGDIR"lshell.conf.tmp" $CONFIGDIR"lshell.conf"
}

user_list(){
	# [4] List users currently using lshell.py as main shell

	num_users=`grep $INSTALLDIR"lshell.py" /etc/passwd | wc -l`
	echo "----------------------------------------------"
	echo "${num_users} users are currently using lshell:"
	grep $INSTALLDIR"lshell.py" /etc/passwd | cut -d ":" -f1 | sed 's/^/\t\(\*\)/'
	press_any_key
}

user_config() {
	# Add and configure a new user in lshell.conf
 
	echo -e "\n[${username}]" >> $CONFIGDIR"lshell.conf"
	echo -n 
	CONFIG_VARS="passwd-{} allowed-{-['ls','pwd','vim']-} forbidden-{-[';','&','|']-} warning_counter-{2} \
				timer-{0} path-{'/home/${username}'} home_path-{'/home/${username}'} env_path-{':'} scp-{0}"
	for var in $CONFIG_VARS
		do
			echo -n "Value for "`echo ${var} | sed 's/-/ /g'`":"
			read input
			if [ $input ]; then
				printf "%-20s : ${input}\n" `echo ${var} | sed 's/-.*/ /'` >> $CONFIGDIR"lshell.conf"
			else
				printf "%-20s : %s\n" `echo ${var} | sed 's/-.*//'` `echo ${var} | cut -d "-" -f2-5 | sed 's/[{}-]//g'` >> $CONFIGDIR"lshell.conf"
			fi
		done

}


### MAIN ###

if [ ! ${UID} -eq 0 ]; then
	echo "${warn} $0 must be run as root, exiting"
	exit 1
fi

check_os
check_python
install_menu
