# Robo-VJ

[![discord.py Version](https://img.shields.io/badge/discord.py-1.6-blue)](https://github.com/Rapptz/discord.py)
[![python version](https://img.shields.io/badge/python-3.8|3.9-blue)](https://www.python.org/downloads/)
[![PostgreSQL version](https://img.shields.io/badge/psql-12|13-blue)](https://www.postgresql.org/download/)
[![Server Invite](https://discord.com/api/guilds/746769944774967440/embed.png)](https://discord.gg/rqgRyF8) \
A personal bot that runs on Discord, originally designed for online quizzes.

## Adding the bot

To use Robo VJ on your server, you can add my public instance by [clicking here][oauth2-invite]

You can also host the bot yourself, however I don't provide support for people that try to self-host.
I don't want to spend time trying to troubleshoot issues that happen only with self-hosting,
so you should at least know enough python, SQL and whatever else to troubleshoot issues, if you find any.

## Running

I would prefer if you don't run an instance of my bot. Just call the join command to invite it to your server.
The source here is provided for educational purposes and for ease of collaboration.

In case you aren't able to add the bot to your server because I haven't verified (nor am I going to),
you may want to self-host. I will try to explain the steps here, but as mentioned earlier,
I will not provide any support for this.

### Self-hosting conditions/warnings
If you are planning to self-host the bot, here are some things to keep in mind:
1. The source code is kept open so that people can see, learn, and if possible,
   help the project with features and bug fixes; and also because it contains code borrowed from [R. Danny][rdanny-repo]
   which is licensed under the [MPL][rdanny-license].
  
2. If you make changes to the source code, you need to follow the [MPL](LICENSE) and keep the changes open source.
If you want to help in development, why not create a pull request?
   
3. Again, I will **not** give support for self-hosted instances. You need to know how to troubleshoot the issues yourself.
I've tried to make the self-host process as painless as possible, but it is impossible for me to identify all the
   different issues you may find.
   
4. Credit the original creators (myself and Danny), and release all files you use from here under the same license.
5. Many API keys are required for some features to work. While they aren't required, you may face issues when trying to use some features.
6. Most of the assets are not shipped with this source code, and at least one dependency is something I wrote on my own and isn't OSS.
You will need to create and include your own assets. (Stockfish binaries have been included because I switched hosts a lot, and I needed the portability)
   
7. I run the bot on Ubuntu focal (20.04), hence the [deploy](scripts/deploy.sh) and [setup](scripts/setup.sh) scripts assume that this is the OS.
However, it may work on other Linux distros, and will require extra work on Windows.
   
8. To avoid confusion, you are **not allowed** to use the name "Robo VJ" or anything similar for your self-hosted version.
Call it "Katya" if you aren't creative enough, or generate your own name [here](https://www.behindthename.com/random/).
   
### Prerequisites

1. **Make sure to get Python 3.8+**

This is required to actually run the bot.

2. **Clone the repository**
   
Make sure you have Git installed, and run
```shell
git clone https://github.com/darthshittious/Robo-VJ.git
```
2. **Set up venv**

Just do `python3.8 -m venv venv`

3. **Install dependencies**

This is `pip install -U -r requirements.txt`
This might fail because one of the [dependencies][d20-permalink] is not OSS.
You can delete this line and run the command again, and it should finish without errors.

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
client_id = ''  # your bot's client ID
token = '' # your bot's token
postgresql = 'postgresql://user:password@host/database' # your postgresql info from above.
# If your password contains non-ASCII characters, you will need to percent encode it.
# This process is simple. To do this in python, replace the postgresql declaration in your config.py with these lines
from urllib.parse import quote
postgresql = f"postgresql://user:{quote('password')}@host/database"
# There are other API keys and tokens required, all of which are not documented.
# Since new features are added almost every week, I can't keep the README up to date.
# This is one important reason why I don't support self hosting.
```

6. **Configuration of database**

To configure the PostgreSQL database for use by the bot, go to the directory where `launcher.py` is located, and run the script by doing `python3.8 launcher.py db init`

7. **Set up Lavalink server (for Music cog)**

To set up a Lavalink server, download OpenJDK 13.0.2, and the latest release of Lavalink.jar, and run `java -jar Lavalink.jar`

8. **Running the bot**

Running on Ubuntu 20.04 will be much easier as there are pre-written shell scripts [here](scripts) that do most of the work for you.

Essentially you would need to use a process manager to run `launcher.py`

## [Additional information] Migrating between database instances

To copy the remote database from source to target:
  - Quick setup: `$ pg_dump -C -h source_host -U user source_db | psql -h target_host -U user target_db`
  - Recommended setup for large databases:
    - on source: `$ pg_dump -U user -O -d source_db -f source_db.sql`
    - copy `source_db.sql` to target server
    - on target: `$ psql -U user -d target_db -f source_db.sql` (You should have target_db created already)


## Requirements

- Python 3.8+
- v1.6.0+ of discord.py
- psutil
- OpenJDK 13.0.2
- Lavalink.jar

## Credits
[Danny](https://github.com/Rapptz) for code in stats, tags, stars, reminder, and utils.db


[oauth2-invite]: https://discord.com/oauth2/authorize?client_id=743900453649252464&scope=bot&permissions=8
[rdanny-repo]: https://github.com/Rapptz/RoboDanny
[d20-permalink]: https://github.com/darthshittious/Robo-VJ/blob/9b5b3800d6bd5721032097539125104588be2d3d/requirements.txt#L3
[rdanny-license]: https://github.com/Rapptz/RoboDanny/blob/rewrite/LICENSE.txt
