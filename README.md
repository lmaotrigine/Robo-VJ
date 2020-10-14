# Robo-VJ

A personal bot that runs on Discord, originally designed for online quizzes.

## Running

I would prefer if you don't run an instance of my bot. Just call the join command to invite it to your server. The source here is provided for educational purposes and for ease of collaboration.

Nevertheless, the installation steps are as follows:

1. **Make sure to get Python 3.8**

This is required to actually run the bot.

2. **Set up venv**

Just do `python3.8 -m venv venv`

3. **Install dependencies**

This is `pip install -U -r requirements.txt`

4. **Create the database in PostgreSQL**

You will need PostgreSQL 12 or higher and type the following
in the `psql` tool:

```sql
CREATE ROLE robovj WITH LOGIN PASSWORD 'yourpw';
CREATE DATABASE robovj OWNER robovj;
```

5. **Setup configuration**

The next step is just to create a `config.py` file in the root directory where
the bot is with the following template:

```py
token = '' # your bot's token
postgresql = 'postgresql://user:password@host/database' # your postgresql info from above.
# If your password contains non-ASCII characters, you will need to percent encode it.
```

6. **Directly running from terminal**

Simply run `bot.py` from your venv. To configure `bot.service` and use systemd, see below.

7. **Configuring systemd to run the bot on reboot**

Open `bot.service` and edit the path to your python environment, working directory, and path to the `bot.py` as needed and then run the following: 
```sh
sudo cp bot.service /etc/systemd/system/
sudo systemctl enable bot && sudo systemctl start bot
```


## [Additional information] Migrating between database instances

To copy the remote database from source to target:
  - If PostgreSQL not installed, follow instructions [here](https://www.postgresql.org/download/)
  - Quick setup: `$ pg_dump -C -h source_host -U user source_db | psql -h target_host -U user target_db`
  - Recommeded setup for large databases:
    - on source: `$ pg_dump -U user -O -d source_db -f source_db.sql`
    - copy `source_db.sql` to target server
    - on target: `$ psql -U user -d target_db -f source_db.sql` (You should have target_db created already)


## Requirements

- Python 3.8.x
- v1.5.0 of discord.py
- psutil
