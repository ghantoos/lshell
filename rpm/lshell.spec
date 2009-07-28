%define name lshell
%define version 0.9.4
%define release 1

Summary: Limited Shell
Name: %{name}
Version: %{version}
Release: %{release}
Source0: %{name}-%{version}.tar.gz
License: GPL
Group: Development/Libraries
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot
Prefix: %{_prefix}
BuildArch: noarch
Vendor: Ignace Mouzannar (ghantoos) <ghantoos@ghantoos.org>
Url: http://ghantoos.org/limited-shell-lshell/

%description
Limited Shell (lshell) is lets you restrict the environment of any user. It provides an easily configurable shell: just choose a list of allowed commands for every limited account.

%prep
%setup -q

%build
python setup.py build

%install
python setup.py install --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES --skip-build

%clean
rm -rf $RPM_BUILD_ROOT

%pre
#!/bin/sh
#
# $Id: lshell.spec,v 1.1 2009-07-28 14:31:56 ghantoos Exp $
#
# RPM build preinstall script

# Save the configuration
if [ -f "/etc/lshell.conf" ]; then
    cp /etc/lshell.conf /etc/lshell.conf-preinstall
fi

exit 0


%post
#!/bin/sh
#
# $Id: lshell.spec,v 1.1 2009-07-28 14:31:56 ghantoos Exp $
#
# RPM build postinstall script

# Check if rpm is being _installed_ (as opposed to _upgraded_)
# if installation process, then proceed
# source: http://www.ibm.com/developerworks/library/l-rpm3.html
# case of installation
if [ "$1" = "1" ] ; then
    groupadd --force lshellg
    mkdir -p /var/log/lshell/
    chown root:lshellg /var/log/lshell/
    chmod -R 770 /var/log/lshell/


    #####
    # This part is taken from debian add-shell(8) script
    #####

    lshell=/usr/bin/lshell
    file=/etc/shells
    tmpfile=${file}.tmp

    set -o noclobber

    trap "rm -f ${tmpfile}" EXIT

    if ! cat ${file} > ${tmpfile}
    then
            cat 1>&2 <<EOF
    Either another instance of $0 is running, or it was previously interrupted.
    Please examine ${tmpfile} to see if it should be moved onto ${file}.
EOF
            exit 1
    fi


    if ! grep -q "^${lshell}" ${tmpfile}
    then
        echo ${lshell} >> ${tmpfile}
    fi
    chmod --reference=${file} ${tmpfile}
    chown --reference=${file} ${tmpfile}

    mv ${tmpfile} ${file}

    trap "" EXIT
    exit 0

# case of upgrade
else
    mkdir -p /var/log/lshell/
    chown root:lshellg /var/log/lshell/
    chmod -R 774 /var/log/lshell/

    mv /etc/lshell.conf /etc/lshell.conf-rpm
    mv /etc/lshell.conf-preinstall /etc/lshell.conf
    exit 0

fi



%postun
#!/bin/sh
#
# $Id: lshell.spec,v 1.1 2009-07-28 14:31:56 ghantoos Exp $
#
# RPM build postuninstall script

# Check if rpm is being _removed_ (as opposed to _upgraded_)
# if deletion process, then proceed, else, exit 0
# source: http://www.ibm.com/developerworks/library/l-rpm3.html
if [ "$1" != "0" ] ; then
    if [ -f "/etc/lshell.conf" ]; then
        cp /etc/lshell.conf /etc/lshell.conf-preinstall
    fi
    exit 0
fi

#groupdel lshellg
rm -f /etc/lshell.conf-rpm

#####
# This part is taken from debian remove-shell(8) script
#####

lshell=/usr/bin/lshell
file=/etc/shells
# I want this to be GUARANTEED to be on the same filesystem as $file
tmpfile=${file}.tmp
otmpfile=${file}.tmp2

set -o noclobber

trap "rm -f ${tmpfile} ${otmpfile}" EXIT
        
if ! cat ${file} > ${tmpfile}
then
        cat 1>&2 <<EOF
Either another instance of $0 is running, or it was previously interrupted.
Please examine ${tmpfile} to see if it should be moved onto ${file}.
EOF
        exit 1
fi

# this is supposed to be reliable, not pretty
grep -v "^${lshell}$" ${tmpfile} > ${otmpfile} || true
mv ${otmpfile} ${tmpfile}

chmod --reference=${file} ${tmpfile}
chown --reference=${file} ${tmpfile}

mv ${tmpfile} ${file}

trap "" EXIT
exit 0



%files -f INSTALLED_FILES
%defattr(-,root,root)
