# Robo-VJ

## Since hosting is expensive, clone this repo to run bot on other instances

## To run:
1. `user@host:~$git clone https://github.com/bowtiesarecool26/Robo-VJ.git`
2. `user@host:~$vi Robo-VJ/.env` and write the following, then Save-Exit
  ```
  # .env
  SCOREKEEPER_TOKEN=<bot token>
  HOST=<postgresql host address>
  PASSWORD=<password for user postgres>
  JISHAKU_HIDE=true
  ```
3. `user@host:~$vi Robo-VJ/bot.service` and edit the username, group, working directory and path to bot.py
4. `user@host:~$sudo cp Robo-VJ/bot.service /etc/systemd/system/bot.service`
5. `user@host:~$sudo systemctl enable bot && sudo systemctl start bot`

Verify status with `user@host:~$sudo systemctl status bot`
