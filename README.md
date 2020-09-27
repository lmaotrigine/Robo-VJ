# Robo-VJ

## Since hosting is expensive, clone this repo to run bot on other instances

## To run:
1. Requires python 3.8. If not installed, run the following:
```
$ sudo add-apt-repository ppa:deadsnakes/ppa
$ sudo apt update
$ sudo apt install python3.8
```
2. `$ python3.8 -m pip install --user -U virtualenv`
3. `user@host:~$virtualenv modmail_env`
4. `user@host:~$source modmail_env/bin/activate`
5. `user@host:~$git clone https://github.com/bowtiesarecool26/Modmail.git`
6. `user@host:~$pip install -r requirements.txt`
4. `user@host:~$vi Modmail/.env` and write the following, then Save-Exit
  ```
  # .env
  SCOREKEEPER_TOKEN=<bot token>
  HOST=<postgresql host address>
  DATABASE=<database name> # defaults to scorekeeper_data if not specified
  DBUSERNAME=<username for accessing the remote database> # defaults to postgres if not specified
  PASSWORD=<password for the user>
  JISHAKU_HIDE=true
  ```
5. To copy the remote database from source to target:
  - If PostgreSQL not installed, follow instructions [here](https://www.postgresql.org/download/linux/ubuntu/)
  - Quick setup: `$ pg_dump -C -h source_host -U postgres source_db | psql -h target_host -U postgres target_db`
  - Recommeded setup for large databases:
    - on source: `$ pg_dump -U postgres -O source_db -f source_db.sql`
    - copy `source_db.sql` to target server
    - on target: `$ psql -U postgres -d target_db -f source_db.sql` (You should have target_db created already)
    
6. `user@host:~$vi Robo-VJ/bot.service` and edit the username, group, working directory and path to bot.py
7. `user@host:~$sudo cp Robo-VJ/bot.service /etc/systemd/system/bot.service`
8. `user@host:~$sudo systemctl enable bot && sudo systemctl start bot`

Verify status with `user@host:~$sudo systemctl status bot`
