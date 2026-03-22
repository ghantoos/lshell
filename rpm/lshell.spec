Name:           lshell
Version:        0.11.0
Release:        1%{?dist}
Summary:        Limited shell implementation in Python

License:        GPL-3.0-or-later
URL:            https://github.com/ghantoos/lshell
Source0:        %{name}-%{version}.tar.gz
Source1:        preinstall
Source2:        postinstall
Source3:        postuninstall

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  pyproject-rpm-macros
Requires:       python3
Requires:       python3-pyparsing >= 3.0.0
Requires:       bash-completion

%description
lshell is a shell coded in Python that lets you restrict a user's environment
to limited sets of commands, choose to enable/disable any command over SSH
(e.g. SCP, SFTP, rsync, etc.), log user commands, implement timing
restrictions, and more.

%prep
%setup -q

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
rm -rf %{buildroot}
%pyproject_install

%pre -f %{SOURCE1}

%post -f %{SOURCE2}

%postun -f %{SOURCE3}

%files
%license COPYING
%doc %{_datadir}/doc/lshell/*
%{_bindir}/lshell
%config(noreplace) %{_prefix}/etc/lshell.conf
%config(noreplace) %{_prefix}/etc/logrotate.d/lshell
%{_datadir}/bash-completion/completions/lshell
%{python3_sitelib}/lshell/
%{python3_sitelib}/limited_shell-*.dist-info
%{_mandir}/man1/lshell.1*

%changelog
* Wed Mar 11 2026 lshell maintainers <ghantoos@ghantoos.org> - 0.11.0-1
- Refresh spec for Python 3 packaging and current project metadata
- Use external pre/post install hooks from rpm/
