%define name lshell
%define version 0.9.16
%define release 1
%define python_sitelib %(python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")

Summary: Limited Shell
Name: %{name}
Version: %{version}
Release: %{release}
Source0: %{name}-%{version}.tar.gz
License: GPL
Group: System Environment/Shells
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot
Prefix: %{_prefix}
BuildRequires:  python >= 2.4
Requires:   python >= 2.4
BuildArch: noarch
Vendor: Ignace Mouzannar (ghantoos) <mouzannar@gmail.com>
Url: http://lshell.ghantoos.org

%description
lshell is a shell coded in Python that lets you restrict a user's environment
to limited sets of commands, choose to enable/disable any command over SSH
(e.g. SCP, SFTP, rsync, etc.), log user's commands, implement timing
restrictions, and more.

%prep
%setup -q

%build
%{__python} setup.py build

%install
%{__python} setup.py install --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES --skip-build

%clean
rm -rf $RPM_BUILD_ROOT

%post
#!/bin/sh
#
# $Id: lshell.spec,v 1.14 2010-10-17 15:47:21 ghantoos Exp $
#
# RPM build postinstall script

# case of installation
if [ "$1" = "1" ] ; then
    if ! getent group lshell 2>&1 > /dev/null; then
        # thank you Michael Mansour for your suggestion to use groupadd
        # instead of addgroup
        groupadd -r lshell
    fi
    mkdir -p /var/log/lshell/
    chown root:lshell /var/log/lshell/
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
    chown root:lshell /var/log/lshell/
    chmod -R 774 /var/log/lshell/

    exit 0

fi



%postun
#!/bin/sh
#
# $Id: lshell.spec,v 1.14 2010-10-17 15:47:21 ghantoos Exp $
#
# RPM build postuninstall script

    if [ -x /usr/sbin/remove-shell ] && [ -f /etc/shells ]; then
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
    fi

%files
%defattr(644,root,root,755)
%doc /usr/share/doc/lshell/*
%config(noreplace) %verify(not md5 mtime size) %{_sysconfdir}/*
%attr(755,root,root) %{_bindir}/lshell
%{python_sitelib}/*
%{_mandir}/man1/lshell.1*
