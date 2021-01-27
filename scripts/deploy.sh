#!/bin/bash

# First argument: user, second argument host
# TODO: Rewrite this whole bloody thing. I can't find a way to make this work, this is pretty much useless, please don't use this.

echo "You will be asked to enter your SSH key password (if needed) and GitHub username and password twice each."
scp ../config.py ${1}@${2}:~/
ssh -t ${1}@${2} "sudo apt install git && git config --global credential.helper store && cd ~ && git clone https://github.com/darthshittious/Robo-VJ.git && cd Robo-VJ/scripts && bash -i ./setup.sh"
