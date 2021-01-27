#!/bin/bash
echo 'alias postgres="psql -h database.varunj.tk -U robovj -d robovj"' >> $HOME/.bash_aliases
cat ./alias.sh >> ~/.bashrc
source ~/.bashrc
if test -f "$HOME/config.py"; then
    mv $HOME/config.py ../
fi

git config --global credential.helper store
git config --global user.name darthshittious
git config --global user.email varunj26012001@gmail.com

sudo apt update && sudo apt upgrade -y
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.9 python3.9-venv python3.9-dev libjpeg-dev libtiff-dev libcairo2-dev

curl https://sh.rustup.rs -sSf | sh
source $HOME/.cargo/env

if [[ -n $SSH_CONNECTION ]] ; then
    bash -i ./get_postgres.sh
    sudo cp bot.service /etc/systemd/system/bot.service
    sudo systemctl daemon-reload
fi
cd ..
venv
pip install -U -r requirements.txt

if [[ -n $SSH_CONNECTION ]] ; then
  sudo systemctl enable bot 
  sudo systemctl start bot
  sudo systemctl status bot
fi
