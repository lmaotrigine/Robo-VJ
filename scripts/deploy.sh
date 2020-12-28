#!/bin/bash

# First argument: user, second argument host

echo "You will be asked to enter your SSH key password (if needed) and GitHub username and password twice each."
scp ../config.py ${1}@${2}:~/
ssh -t ${1}@${2} "sudo apt install git && git config --global credential.helper store && cd ~ && git clone https://github.com/darthshittious/Robo-VJ.git && cd Robo-VJ/scripts && bash -i ./aws_setup.sh"
