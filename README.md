# Robo-VJ
[![license](https://img.shields.io/github/license/darthshittious/Robo-VJ)](https://www.mozilla.org/en-US/MPL/2.0/)
[![discord.py Version](https://img.shields.io/badge/discord.py-1.6-blue)](https://github.com/Rapptz/discord.py)
[![python version](https://img.shields.io/badge/python-3.8|3.9-blue)](https://www.python.org/downloads/release/python-386/)
[![PostgreSQL version](https://img.shields.io/badge/psql-12|13-blue)](https://www.postgresql.org/download/)
[![Server Invite](https://discord.com/api/guilds/746769944774967440/embed.png)](https://discord.gg/rqgRyF8) \
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
CREATE EXTENSION pg_trgm;
```

5. **Setup configuration**

The next step is just to create a `config.py` file in the root directory where
the bot is with the following template:

```py
token = '' # your bot's token
postgresql = 'postgresql://user:password@host/database' # your postgresql info from above.
# If your password contains non-ASCII characters, you will need to percent encode it.
# This process is simple. To do this in python, replace the postgresql declaration in your config.py with these lines
from urllib.parse import quote
postgresql = f"postgresql://user:{quote('password')}@host/database"
```

6. **Configuration of database**

To configure the PostgreSQL database for use by the bot, go to the directory where `launcher.py` is located, and run the script by doing `python3.8 launcher.py db init`

7. **Set up Lavalink server (for Music cog)**

To set up a Lavalink server, download OpenJDK 13.0.2, and the latest release of Lavalink.jar, and run `java -jar Lavalink.jar`

8. **Running the bot**

You can use the provided `bot.service` file to use systemd to launch the bot after every reboot.

## [Additional information] Migrating between database instances

To copy the remote database from source to target:
  - Quick setup: `$ pg_dump -C -h source_host -U user source_db | psql -h target_host -U user target_db`
  - Recommeded setup for large databases:
    - on source: `$ pg_dump -U user -O -d source_db -f source_db.sql`
    - copy `source_db.sql` to target server
    - on target: `$ psql -U user -d target_db -f source_db.sql` (You should have target_db created already)


## Requirements

- Python 3.8.x
- v1.6.0+ of discord.py
- psutil
