"""
Basic Discord bot skeleton with some external cogs
"""
import aiohttp
import datetime
import os
import json
import random
import time
from dotenv import load_dotenv
import asyncpg
import discord
from discord.ext import commands, tasks
import sys
from collections import Counter, deque, defaultdict
from cogs.utils.config import Config
import logging
import traceback

__version__ = "3.0.0"
__author__ = "Varun J"

log = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv('SCOREKEEPER_TOKEN')
HOST = os.getenv('HOST')
PASSWORD = os.getenv('PASSWORD')
DATABASE = os.getenv('DATABASE') or 'scorekeeper_data'
USER = os.getenv('DBUSERNAME') or 'postgres'

def pfx_helper(message):
    """helper to get prefix"""
    #with open('readonly/prefixes.json', 'r') as file:
    #    prefixes = json.load(file)
    #if message.guild:
    #    return prefixes.get(str(message.guild.id), '!')
    #else:
    #    return "!"
    if not message.guild:
        return '!'
    return client.prefixes.get(message.guild.id, '!')



def get_prefix(bot, message):
    """
    loads the prefix for a guild from file
    """
    return commands.when_mentioned_or(pfx_helper(message))(bot, message)


def get_uptime():
    current_time = time.time()
    difference = int(round(current_time - start_time))
    ut = str(datetime.timedelta(seconds=difference))
    if ',' in ut:
        days = f"{ut.split('d')[0].strip()}d "
        new_ut = ut.split(',')[1].strip()
    else:
        days = ''
        new_ut = ut
    components = new_ut.split(':')
    suffixes = ['h', 'm', 's']
    text = days
    for idx in range(len(components)):
        text += f"{components[idx]}{suffixes[idx]} "

    return text

async def create_db_pool():
    credentials = {"user": USER, "password": PASSWORD, "database": DATABASE, "host": HOST}
    try:
        client.db = await asyncpg.create_pool(**credentials)
    except KeyboardInterrupt:
        await client.db.close()

async def close_db():
    await client.db.close()
    await client.session.close()

# initialise client
class RoboVJ(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.blacklist = Config('blacklist.json')
        self.spam_control = commands.CooldownMapping.from_cooldown(10, 12.0, commands.BucketType.user)
        self._auto_spam_count = Counter()
        self.session = aiohttp.ClientSession(loop=self.loop)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.author.send('This command cannot be used in private messages.')
        elif isinstance(error, commands.DisabledCommand):
            await ctx.author.send('Sorry. This command is disabled and cannot be used.')
        elif isinstance(error, commands.CommandInvokeError):
            original = error.original
            if not isinstance(original, discord.HTTPException):
                print(f'In {ctx.command.qualified_name}:', file=sys.stderr)
                traceback.print_tb(original.__traceback__)
                print(f'{original.__class__.__name__}: {original}', file=sys.stderr)
        elif isinstance(error, commands.ArgumentParsingError):
            await ctx.send(error)
        else:
            print("Ignoring exception in command {}:".format(ctx.command), file=sys.stderr)
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    async def add_to_blacklist(self, object_id):
        await self.blacklist.put(object_id, True)

    async def remove_from_blacklist(self, object_id):
        try:
            await self.blacklist.remove(object_id)
        except KeyError:
            pass
    @discord.utils.cached_property
    def stats_webhook(self):
        wh_url = "https://discordapp.com/api/webhooks/759357220022124604/qs9KdS8X0xaENc1SjraEgXgx0B6fusuGg2WFiXDtBkWX-OGfGEyeeM4wwiVQglV6W8LB"
        hook = discord.Webhook.from_url(wh_url, adapter=discord.AsyncWebhookAdapter(self.session))
        return hook

    def log_spammer(self, ctx, message, retry_after, *, autoblock=False):
        guild_name = getattr(ctx.guild, 'name', 'No Guild (DMs)')
        guild_id = getattr(ctx.guild, 'id', None)
        fmt = 'User %s (ID %s) in guild %r (ID %s) spamming, retry_after: %.2fs'
        log.warning(fmt, message.author, message.author.id, guild_name, guild_id, retry_after)
        if not autoblock:
            return

        wh = self.stats_webhook
        embed = discord.Embed(title='Auto-blocked Member', colour=0xDDA453)
        embed.add_field(name='Member', value=f'{message.author} (ID: {message.author.id})', inline=False)
        embed.add_field(name='Guild Info', value=f'{guild_name} (ID: {guild_id})', inline=False)
        embed.add_field(name='Channel Info', value=f'{message.channel} (ID: {message.channel.id}', inline=False)
        embed.timestamp = datetime.datetime.utcnow()
        return wh.send(embed=embed)

    async def process_commands(self, message):
        ctx = await self.get_context(message)

        if ctx.command is None:
            return

        if ctx.author.id in self.blacklist:
            return

        if ctx.guild is not None and ctx.guild.id in self.blacklist:
            return

        bucket = self.spam_control.get_bucket(message)
        current = message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp()
        retry_after = bucket.update_rate_limit(current)
        author_id = message.author.id
        if retry_after and author_id != self.owner_id:
            self._auto_spam_count[author_id] += 1
            if self._auto_spam_count[author_id] >= 5:
                await self.add_to_blacklist(author_id)
                del self._auto_spam_count[author_id]
                await self.log_spammer(ctx, message, retry_after, autoblock=True)
            else:
                self.log_spammer(ctx, message, retry_after)
            return
        else:
            self._auto_spam_count.pop(author_id, None)

        await self.invoke(ctx)

client = RoboVJ(command_prefix=get_prefix, status=discord.Status.online, activity=discord.Activity(
    name=f"!help", type=discord.ActivityType.listening), owner_id=411166117084528640,
    #help_command=EmbedHelpCommand(dm_help=None),
    help_command=commands.DefaultHelpCommand(width=150, no_category='General', dm_help=None),
    case_insensitive=True, intents=discord.Intents.all())
client.version = __version__
client.prefixes = {}
client.qchannels = {}
client.pchannels = {}
client.modlogs = {}

@tasks.loop(count=1)
async def startup():
    global start_time
    start_time = time.time()
    print("Bot is ready")
    print()
    print(f"Logged in as: {client.user}\nID: {client.user.id}")
    print("----------------")

    client.owner = client.get_user(client.owner_id)
    data = await client.db.fetch("SELECT * FROM servers")
    for record in data:
        client.prefixes[record['guild_id']] = record['prefix']
        client.qchannels[record['guild_id']] = record['qchannel']
        client.pchannels[record['guild_id']] = record['pchannel']
        client.modlogs[record['guild_id']] = record['modlog']

    print('Data loaded')



@startup.before_loop
async def before_startup():
    await client.wait_until_ready()


# Return prefix on being mentioned
@client.event
async def on_message(message):
    if message.content.strip() in ['<@743900453649252464>', '<@!743900453649252464>']:
        pfx = pfx_helper(message)
        await message.channel.send(f"My prefix is `{pfx}`. Use `{pfx}help` for more information.")
    await client.process_commands(message)


# Load cogs
client.load_extension("cogs.admin")
for filename in os.listdir('./cogs'):
    if filename.endswith('.py'):
        client.load_extension(f'cogs.{filename[:-3]}')


# update prefixes on joining a server
@client.event
async def on_guild_join(guild):
    if guild.id not in client.prefixes.keys() or not await client.db.fetchrow("SELECT prefix FROM servers WHERE guild_id = $1", guild.id):
        client.prefixes[guild.id] = '!'
        connection = await client.db.acquire()
        async with connection.transaction():
            await client.db.execute(f"INSERT INTO servers (guild_id, prefix) VALUES ({guild.id}, '!')")
            if not await client.db.fetchrow("SELECT name FROM named_servers WHERE guild_id = $1", guild.id):
                await client.db.execute("INSERT INTO named_servers (guild_id, name) VALUES ($1, $2)", guild.id, guild.name)
        await client.db.release(connection)
    pfx = client.prefixes[guild.id]
    if guild.system_channel:
        send_here = guild.system_channel
    else:
        for channel in guild.text_channels:
            if channel.overwrites_for(guild.default_role).read_messages:
                send_here = channel
                break
    embed = discord.Embed(title="Thanks for adding me to your server! :blush:", colour=discord.Colour.blurple())
    embed.description = f"""Robo VJ was originally made to keep scores during online quizzes, but has since evolved to support moderation commands and some fun here and there.
For a full list of commands, use `{pfx}help`.

Be mindful of hierarchy while using commands that involve assigning or removing roles, or editing nicknames. It is advisable to give the bot the highest role in the server if you are unfamiliar with Discord hierarchy and permission flow.

Some easter egg commands are not included in the help page. Others like the `utils` group have been deliberately hidden because they are reserved for the bot owner.

If you have any questions, or need help with the bot, or want to report bugs or request features, [click here](https://discord.gg/rqgRyF8) to join the support server."""
    embed.set_footer(text=f"Made by {client.owner}", icon_url=client.owner.avatar_url)
    await send_here.send(embed=embed)

@client.event
async def on_guild_update(before, after):
    if before.name != after.name:
        await client.db.execute("UPDATE named_servers SET name = $1 WHERE guild_id = $2", after.name, after.id)

# General commands
@client.command(aliases=["hi"])
async def hello(ctx):
    """I was programmed to be nice :)"""
    if ctx.author.id == 711301834018521102:  # Ananya
        await ctx.send(f"Akka namskara! {ctx.author.mention}")
    elif ctx.author.id == 411166117084528640:  # Me
        return await ctx.send(f"{ctx.author.mention} who the hell are you?")
    elif ctx.author.id == 173357402639433729:  # Jay
        await ctx.send(f"Hello {ctx.author.mention}. Got any gummy bears on you?")
    elif ctx.author.id == 439065755242332160:  # PJ
        await ctx.send(f"{ctx.author.mention}", file=discord.File('assets/PJ.jpeg'))
    elif ctx.author.id == 557595185903566879:  # Kannan
        await ctx.send(content=f"{ctx.author.mention} Oink oink, ya Capitalist Pig!", file=discord.File('assets/kannan.jpg'))
    elif ctx.author.id == 312265075933315074:  # Jakus
        await ctx.send(content="Jaaaaaaaaaaaaaake 😍😍🥰🥰", file=discord.File('assets/Jake.gif'))
    elif ctx.author.id == 727521754313916487:  # kwee
        await ctx.send(content="Kweeeeeeeeeeeeeeeeeeeeeeee")
    elif ctx.author.id == 712327512826314835:  # Sanjeev
        await ctx.send(content=f"{ctx.author.mention} Sex bro?")
    elif ctx.author.id == 380988746197237760:  # Aryaman
        await ctx.send("Moshi Moshi from Rasputin chan", file=discord.File('assets/Rasputin.jpeg'))
    elif ctx.author.id == 758721255477477376: # Gijo
        await ctx.send("All hail The Homie, Claimer of Ass!")
    elif ctx.author.id == 758715042609889322: # Vishaan
        await ctx.send("Hellu ya fookin drug-addled delinquent", file=discord.File('assets/Vishaan.gif'))
    elif ctx.author.id == 585085025305755687: # Rida ew
        await ctx.send(f"{ctx.author.mention} sup clownass bitch")
    elif ctx.author.id == 750258404823662613: # Sanyaaaa
        await ctx.send(f"{ctx.author.mention}", file=discord.File('assets/Saanya.png'))
    else:
        greeting = random.choice(["Hello!", "Hallo!", "Hi!", "Nice to meet you", "Hey there!"])
        owner = client.get_user(client.owner_id)
        await ctx.send(f"{greeting} I'm a robot! {owner.name}#{owner.discriminator} made me.")


@client.command(aliases=['join'])
async def invite(ctx):
    """Get the invite link to add the bot to your server"""
    embed = discord.Embed(title="Click here to add me to your server", colour=discord.Colour(0xFF0000),
                          url=discord.utils.oauth_url(client.user.id, discord.Permissions(administrator=True)))
    embed.set_author(name=client.user.display_name if ctx.guild is None else ctx.guild.me.display_name, icon_url=client.user.avatar_url)
    await ctx.send(embed=embed)

# leave a guild
@client.command(hidden=True)
@commands.is_owner()
async def leave(ctx, guild_id = None):
    if not await client.is_owner(ctx.author):
        return
    if not guild_id:
        guild = ctx.guild
    elif not guild_id.isnumeric():
        return await ctx.send("Enter a valid guild ID", delete_after=30.0)

    if guild_id:
        guild = client.get_guild(guild_id)
    if not guild:
        guild = await client.fetch_guild(guild_id)
    name = guild.name
    await guild.leave()
    await client.owner.send(f"Left '{name}'")

@client.command(hidden=True, aliases=["good bot"])
async def goodbot(ctx):
    """Appreci8 that wun"""
    await ctx.send(f"Thanks {ctx.author.mention}, I try :slight_smile:")


@client.command(hidden=True)
async def ping(ctx):
    """
    Returns bot latency
    """
    await ctx.send(f"Pong! {round(client.latency * 1000)}ms")


@client.command()
async def support(ctx):
    """Join the support server to report issues or get updates or just hang out"""
    embed = discord.Embed(title="Click here to join the support server", colour=discord.Colour(0xFF0000),
                          url="https://discord.gg/rqgRyF8")
    embed.set_author(name=client.user.display_name if ctx.guild is None else ctx.guild.me.display_name, icon_url=client.user.avatar_url)
    await ctx.send(embed=embed)


@client.command(name="about")
async def _info(ctx):
    """Some info about the bot"""
    embed = discord.Embed(colour=discord.Colour(0xFF0000))
    name = client.user.display_name
    if ctx.guild and ctx.guild.me.nick:
        name += f" ({ctx.guild.me.nick})"
    embed.set_author(name=f"{name} - v{client.version}", icon_url=client.user.avatar_url)
    #embed.set_thumbnail(url=client.user.avatar_url)
    embed.add_field(name="Creator", value=f"{client.get_user(411166117084528640).mention}", inline=False)
    embed.add_field(name="Servers", value=f"{len(client.guilds)}", inline=True)
    embed.add_field(name="Commands", value=f"{len(list(filter(lambda x: not x.hidden, client.commands)))}", inline=True)
    embed.add_field(name="Uptime", value=f"{get_uptime()}", inline=True)
    embed.add_field(name="Support", value=f"[Join the support server for announcements and to report issues](https://discord.gg/rqgRyF8)",
                    inline=False)
    embed.add_field(name="Invite",
                    value=f"[Click here to add me to your server.]({discord.utils.oauth_url(client.user.id, discord.Permissions(administrator=True))})",
                    inline=False)
    embed.add_field(name="Library", value="[discord.py](https://github.com/Rapptz/discord.py)")
    await ctx.send(embed=embed)

@client.command(name="uptime", hidden=True)
async def _uptime(ctx):
    await ctx.send(f"{get_uptime()}")


# Get things rolling

startup.start()
try:
    client.loop.run_until_complete(create_db_pool())
    client.loop.run_until_complete(client.start(TOKEN))
except KeyboardInterrupt:
    client.loop.run_until_complete(client.logout())
    client.loop.run_until_complete(close_db())
finally:
    client.loop.close()
#client.run(TOKEN)
startup.cancel()
