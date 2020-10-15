
__version__ = "3.1.0"
__author__ = "Varun J"

import aiohttp
import datetime
import os
import random
import asyncpg
import config
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import sys
from collections import Counter, deque, defaultdict
from cogs.utils.config import Config
from cogs.utils import time
import logging
import traceback

# Some custom greetings I had made for my friends.
try:
    from assets.hello import Greeter
except ImportError:
    Greeter = None

log = logging.getLogger(__name__)
load_dotenv()

def pfx_helper(message):
    """helper to get prefix"""
    if not message.guild:
        return '!'
    return bot.prefixes.get(message.guild.id, '!')



def get_prefix(bot, message):
    """
    loads the prefix for a guild from file
    """
    return commands.when_mentioned_or(pfx_helper(message))(bot, message)

async def create_db_pool():
    try:
        bot.db = await asyncpg.create_pool(config.postgresql)
    except KeyboardInterrupt:
        await bot.db.close()

async def close_db():
    await bot.db.close()
    await bot.session.close()


# initialise bot
class RoboVJ(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.blacklist = Config('blacklist.json')
        self.spam_control = commands.CooldownMapping.from_cooldown(10, 12.0, commands.BucketType.user)
        self._auto_spam_count = Counter()
        self.session = aiohttp.botSession(loop=self.loop)

    async def init_db(self):    
        await self.db.execute("""CREATE TABLE IF NOT EXISTS servers (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT,
            prefix TEXT,
            qchannel BIGINT,
            pchannel BIGINT,
            modlog BIGINT
        );
        CREATE TABLE IF NOT EXISTS blocks (
            user_id BIGINT,
            guild_id BIGINT,
            channel_id BIGINT,
            block_until TIMESTAMP WITH TIME ZONE
        );
        CREATE TABLE IF NOT EXISTS mutes (
            user_id BIGINT,
            guild_id BIGINT,
            mute_until TIMESTAMP WITH TIME ZONE
        );
        CREATE TABLE IF NOT EXISTS named_servers (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT,
            name TEXT
        );
        CREATE TABLE IF NOT EXISTS warns (
            user_id BIGINT,
            guild_id BIGINT,
            num INTEGER
        );
        """)

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

    async def on_ready(self):
        if not hasattr(self, 'uptime'):
            self.uptime = datetime.datetime.utcnow()

        print(f'Ready: {self.user} (ID: {self.user.id})')

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

bot = RoboVJ(command_prefix=get_prefix, status=discord.Status.online, activity=discord.Activity(
    name=f"!help", type=discord.ActivityType.listening), owner_id=411166117084528640,
    #help_command=EmbedHelpCommand(dm_help=None),
    help_command=commands.DefaultHelpCommand(width=150, no_category='General', dm_help=None),
    case_insensitive=True, intents=discord.Intents.all())

bot.version = __version__
bot.prefixes = {}
bot.qchannels = {}
bot.pchannels = {}
bot.modlogs = {}

@tasks.loop(count=1)
async def startup():
    await bot.init_db()
    bot.owner = bot.get_user(bot.owner_id)
    data = await bot.db.fetch("SELECT * FROM servers")
    for record in data:
        bot.prefixes[record['guild_id']] = record['prefix']
        bot.qchannels[record['guild_id']] = record['qchannel']
        bot.pchannels[record['guild_id']] = record['pchannel']
        bot.modlogs[record['guild_id']] = record['modlog']

    print('Data loaded')



@startup.before_loop
async def before_startup():
    await bot.wait_until_ready()


# Return prefix on being mentioned
@bot.event
async def on_message(message):
    if message.content.strip() in ['<@743900453649252464>', '<@!743900453649252464>']:
        pfx = pfx_helper(message)
        await message.channel.send(f"My prefix is `{pfx}`. Use `{pfx}help` for more information.")
    await bot.process_commands(message)


# Load cogs
bot.load_extension("cogs.admin")
for filename in os.listdir('./cogs'):
    if filename.endswith('.py'):
        bot.load_extension(f'cogs.{filename[:-3]}')


# update prefixes on joining a server
@bot.event
async def on_guild_join(guild):
    if guild.id not in bot.prefixes.keys() or not await bot.db.fetchrow("SELECT prefix FROM servers WHERE guild_id = $1", guild.id):
        bot.prefixes[guild.id] = '!'
        connection = await bot.db.acquire()
        async with connection.transaction():
            await bot.db.execute(f"INSERT INTO servers (guild_id, prefix) VALUES ({guild.id}, '!')")
            if not await bot.db.fetchrow("SELECT name FROM named_servers WHERE guild_id = $1", guild.id):
                await bot.db.execute("INSERT INTO named_servers (guild_id, name) VALUES ($1, $2)", guild.id, guild.name)
        await bot.db.release(connection)
    pfx = bot.prefixes[guild.id]
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
    embed.set_footer(text=f"Made by {bot.owner}", icon_url=bot.owner.avatar_url)
    await send_here.send(embed=embed)

@bot.event
async def on_guild_update(before, after):
    if before.name != after.name:
        await bot.db.execute("UPDATE named_servers SET name = $1 WHERE guild_id = $2", after.name, after.id)

# General commands
@bot.command(aliases=["hi"])
async def hello(ctx):
    """Go ahead, say hi!"""
    if Greeter:
        coro = Greeter.greet(ctx)
        if coro:
            return await eval(coro)
    greeting = random.choice(["Hello!", "Hallo!", "Hi!", "Nice to meet you", "Hey there!", "Beep boop!"])
    owner = bot.get_user(bot.owner_id)
    await ctx.send(f"{greeting} I'm a robot! {str(owner)} made me.")


@bot.command(aliases=['invite'])
async def join(ctx):
    """Get the invite link to add the bot to your server"""
    embed = discord.Embed(title="Click here to add me to your server", colour=discord.Colour(0xFF0000),
                          url=discord.utils.oauth_url(bot.user.id, discord.Permissions(administrator=True)))
    embed.set_author(name=bot.user.display_name if ctx.guild is None else ctx.guild.me.display_name, icon_url=bot.user.avatar_url)
    await ctx.send(embed=embed)

# leave a guild
@bot.command(hidden=True)
@commands.is_owner()
async def leave(ctx, guild_id = None):
    if not await bot.is_owner(ctx.author):
        return
    if not guild_id:
        guild = ctx.guild
    elif not guild_id.isnumeric():
        return await ctx.send("Enter a valid guild ID", delete_after=30.0)

    if guild_id:
        guild = bot.get_guild(guild_id)
    if not guild:
        guild = await bot.fetch_guild(guild_id)
    name = guild.name
    await guild.leave()
    await bot.owner.send(f"Left '{name}'")

@bot.command(hidden=True, aliases=["good bot"])
async def goodbot(ctx):
    """Appreci8 that wun"""
    await ctx.send(f"Thanks {ctx.author.mention}, I try :slight_smile:")


@bot.command(hidden=True)
async def ping(ctx):
    """
    Returns bot latency
    """
    await ctx.send(f"Pong! {round(bot.latency * 1000)}ms")


@bot.command()
async def support(ctx):
    """Join the support server to report issues or get updates or just hang out"""
    embed = discord.Embed(title="Click here to join the support server", colour=discord.Colour(0xFF0000),
                          url="https://discord.gg/rqgRyF8")
    embed.set_author(name=bot.user.display_name if ctx.guild is None else ctx.guild.me.display_name, icon_url=bot.user.avatar_url)
    await ctx.send(embed=embed)

# Get things rolling

startup.start()
try:
    bot.loop.run_until_complete(create_db_pool())
    bot.loop.run_until_complete(bot.start(config.token))
except KeyboardInterrupt:
    bot.loop.run_until_complete(bot.logout())
    bot.loop.run_until_complete(close_db())
finally:
    bot.loop.close()
#bot.run(TOKEN)
startup.cancel()
