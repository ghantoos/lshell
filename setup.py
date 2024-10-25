""" Setup script for lshell """

import os
import shutil
from setuptools import setup, find_packages
from setuptools.command.install import install

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

    with open("README.md", "r") as f:
        long_description = f.read()

    setup(
        name="limited-shell",
        version=__version__,
        description="lshell - Limited Shell",
        long_description=long_description,
        long_description_content_type="text/markdown",
        author="Ignace Mouzannar",
        author_email="ghantoos@ghantoos.org",
        maintainer="Ignace Mouzannar",
        maintainer_email="ghantoos@ghantoos.org",
        keywords=["limited", "shell", "security", "python"],
        url="https://github.com/ghantoos/lshell",
        project_urls={
            "GitHub": "https://github.com/ghantoos/lshell",
            "Changelog": "https://github.com/ghantoos/lshell/blob/master/CHANGELOG.md",
        },
        license="GPL-3",
        platforms=["UNIX"],
        scripts=["bin/lshell"],
        package_dir={"lshell": "lshell"},
        packages=find_packages(exclude=["test", "test.*"]),
        include_package_data=True,
        data_files=[
            ("etc", ["etc/lshell.conf"]),
            ("etc/logrotate.d", ["etc/logrotate.d/lshell"]),
            (
                "share/doc/lshell",
                ["README.md", "COPYING", "CHANGELOG.md", "SECURITY.md"],
            ),
            ("share/man/man1/", ["man/lshell.1"]),
        ],
        classifiers=[
            "Development Status :: 5 - Production/Stable",
            "Environment :: Console",
            "Intended Audience :: Information Technology",
            "Intended Audience :: System Administrators",
            "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
            "Operating System :: POSIX",
            "Programming Language :: Python :: 3",
            "Topic :: Security",
            "Topic :: System :: Shells",
            "Topic :: System :: System Shells",
            "Topic :: System :: Systems Administration",
            "Topic :: Terminals",
        ],
        python_requires=">=3.6",
        install_requires=[],
        cmdclass={
            "install": CustomInstallCommand,  # Use custom install command
        },
    )
