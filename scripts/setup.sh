#!/bin/bash

# Must be run in an interactive shell
# If you're not me, don't blindly run this. Most of it will fail without the right credentials.

# Set up aliases for git and venv
cat ./alias.sh >> ~/.bashrc
source ~/.bashrc

# Move config file to bot directory if exists
if test -f "$HOME/config.py"; then
    mv $HOME/config.py ../
fi

# Git config NOTE: Use PAT, not password
git config --global credential.helper store
git config --global user.name darthshittious
git config --global user.email varunj26012001@gmail.com

# Update and install packages
sudo apt update && sudo apt upgrade -y
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.9 python3.9-pip python3.9-venv python3.9-dev libjpeg-dev libtiff-dev libcairo2-dev
python3.9 -m pip install -U psutil

# I like emacs, so I will install it. You can comment these lines out if you wish.
# I also choose to install Neofetch and mlocate
# emacs 27: Current version as of January 2021
sudo add-apt-repository ppa:kelleyk/emacs
sudo apt install emacs27 neofetch mlocate

# Install PostgreSQL, and add .service file to systemd, if on remote server
if [[ -n $SSH_CONNECTION ]] ; then
    bash -i ./get_postgres.sh
    sudo cp bot.service /etc/systemd/system/bot.service
    # PostgreSQL 13: Latest as of 28-01-2021

    # Add md5 authentication for all users on localhost
    sudo sed -i "s/\(local\s*all\s*all\s*)peer/\1md5/" /etc/postgresql/13/main/pg_hba.conf
    sudo systemctl restart postgresql

    # Setup robovj role and database
    echo 'Enter the password for robovj role in PostgreSQL and hit [ENTER]:'
    read passwordd
    echo 'Creating role with password...'
    sudo -u postgres psql -c "CREATE ROLE robovj WITH LOGIN PASSWORD $passwordd;"
    echo 'Done.'
    echo 'Creating database...'
    sudo -u postgres psql -c "CREATE DATABASE robovj WITH OWNER robovj;"
    echo 'Done.'
    
    # Add pg_trgm extension for similarity ordering
    echo 'Creating pg_trgm extension...'
    sudo -u postgres psql -c "CREATE EXTENSION pg_trgm;"
    echo 'Done.'

    # Import records from SQL file, if present
    if test -f "$HOME/robovj.sql"; then
	echo 'SQL file found. Importing records...'
        psql -U robovj -d robovj -f $HOME/robovj.sql
	echo 'Done. You may now delete this file.'
    fi
    sudo systemctl daemon-reload
fi

# Install core dependencies
cd ..
python3.9 -m venv venv
source venv/bin/activate
pip install -U pip setuptools wheel

# Set up Rust compiler, for Markov wrapper
if [[ -n $SSH_CONNECTION ]] ; then
    curl https://sh.rustup.rs -sSf | sh
fi
source $HOME/.cargo/env

# Install bot requirements
pip install -U -r requirements.txt

# Clone assets. I'm not making this a submodule because it rarely changes, and I want to avoid detached HEADs
git clone https://github.com/darthshittious/Robo-VJ-assets.git ./assets

# Get things rolling
if [[ -n $SSH_CONNECTION ]] ; then
  sudo systemctl enable bot 
  sudo systemctl start bot
  sudo systemctl status bot
fi

