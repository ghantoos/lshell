#
#  Limited command Shell (lshell)
#
#  Copyright (C) 2008-2024 Ignace Mouzannar <ghantoos@ghantoos.org>
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

from setuptools import setup, find_packages
import os
from setuptools.command.install import install
import shutil

# import lshell specifics
from lshell.variables import __version__


class CustomInstallCommand(install):
    """Customized setuptools install command to handle etc files."""

    def run(self):
        # Call the standard install first
        install.run(self)

        # Determine correct configuration paths
        if os.geteuid() != 0:  # If not root, use ~/.local/etc
            etc_install_dir = os.path.join(os.path.expanduser("~"), ".local/etc")
        else:  # For system-wide install, use /etc
            etc_install_dir = "/etc"

        # Create necessary directories if they don't exist
        os.makedirs(os.path.join(etc_install_dir, "logrotate.d"), exist_ok=True)

        # Copy configuration files to appropriate directories
        shutil.copy("etc/lshell.conf", etc_install_dir)
        shutil.copy(
            "etc/logrotate.d/lshell", os.path.join(etc_install_dir, "logrotate.d")
        )


if __name__ == "__main__":

    setup(
        name="lshell",
        version=__version__,
        description="Limited Shell",
        long_description="""Limited Shell (lshell) lets you restrict the \
environment of any user. It provides an easily configurable shell: just \
choose a list of allowed commands for every limited account.""",
        long_description_content_type="text/markdown",
        author="Ignace Mouzannar",
        author_email="ghantoos@ghantoos.org",
        maintainer="Ignace Mouzannar",
        maintainer_email="ghantoos@ghantoos.org",
        keywords=["limited", "shell", "security", "python"],
        url="https://github.com/ghantoos/lshell",
        license="GPL",
        platforms=["UNIX"],
        scripts=["bin/lshell"],
        package_dir={"lshell": "lshell"},
        packages=find_packages(),
        include_package_data=True,
        data_files=[
            ("share/doc/lshell", ["README.md", "COPYING", "CHANGES", "SECURITY.md"]),
            ("share/man/man1/", ["man/lshell.1"]),
        ],
        classifiers=[
            "Development Status :: 5 - Production/Stable",
            "Environment :: Console",
            "Intended Audience :: Advanced End Users",
            "Intended Audience :: System Administrators",
            "License :: OSI Approved :: GNU General Public License v3",
            "Operating System :: POSIX",
            "Programming Language :: Python :: 3",
            "Topic :: Security",
            "Topic :: System :: Shells",
            "Topic :: Terminals",
        ],
        python_requires=">=3.6",
        install_requires=[],
        cmdclass={
            "install": CustomInstallCommand,  # Use custom install command
        },
    )
