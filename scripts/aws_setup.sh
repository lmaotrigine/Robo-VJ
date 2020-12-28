#!/bin/bash
cat ./alias.sh >> ~/.bash_aliases
source ~/.bashrc
if test -f "$HOME/config.py"; then
    mv $HOME/config.py ../
fi

cd ..
git config --global credential.helper store
git config --global user.name darthshittious
git config --global user.email varunj26012001@gmail.com

sudo apt update && sudo apt upgrade -y
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.9 python3.9-venv python3.9-dev libjpeg zlib libtiff libfreetype
if [[ -n $SSH_CONNECTION ]] ; then
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
