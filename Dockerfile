# Define the base image dynamically using build argument
ARG DISTRO=ubuntu:latest
FROM ${DISTRO} AS base

# Install dependencies based on the distribution
RUN \
    # For Debian/Ubuntu
    if [ -f /etc/debian_version ]; then \
        apt-get update && \
        apt-get install -y python3 python3-pip git flake8 pylint python3-pytest python3-pexpect python3-setuptools python3-pyparsing vim procps && \
        apt-get clean; \
        useradd -m -d /home/testuser -s /bin/bash testuser; \
    # For Fedora
    elif [ -f /etc/fedora-release ]; then \
        dnf install -y python3 python3-pip python3-pytest git flake8 pylint python3-pexpect python3-setuptools python3-pyparsing vim; \
        useradd -m -d /home/testuser -s /bin/bash testuser; \
    # For CentOS
    elif [ -f /etc/centos-release ]; then \
        # Update CentOS repository to use vault.centos.org
        sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-* && \
        sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-* && \
        yum install -y python3 python3-pip python3-pytest git vim && \
        yum install -y python3-devel gcc && \
        python3 -m pip install flake8 pylint pexpect setuptools pyparsing; \
        yum clean all; \
        useradd -m -d /home/testuser -s /bin/bash testuser; \
    # For Alpine
    elif [ -f /etc/alpine-release ]; then \
        apk add --no-cache --upgrade python3 py3-pip py3-pytest py3-flake8 py3-pylint py3-pexpect py3-setuptools py3-pyparsing grep vim; \
        addgroup -S testuser && adduser -S testuser -G testuser; \
    fi

# Set permissions for the user to access /app
RUN mkdir /home/testuser/lshell && chown -R testuser:testuser /home/testuser/lshell

# Set working directory to /home/testuser
WORKDIR /home/testuser/lshell

# Set PYTHONPATH to the current working directory
ENV PYTHONPATH=/home/testuser/lshell

# Copy the code and requirements
COPY . /home/testuser/lshell

# Install lshell from the source
RUN python3 setup.py install

# Switch to `testuser`
USER testuser

# Entry point for interactive lshell (overridden in Docker Compose for tests)
CMD ["lshell"]
