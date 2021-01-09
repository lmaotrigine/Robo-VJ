import asyncio
import datetime
from contextlib import suppress
import discord
from discord.ext import commands, tasks
from .utils import db


class MessageLog(db.Table, table_name='message_log'):
    channel_id = db.Column(db.Integer(big=True), primary_key=True)
    message_id = db.Column(db.Integer(big=True), primary_key=True)
    guild_id = db.Column(db.Integer(big=True), index=True)
    user_id = db.Column(db.Integer(big=True), index=True)
    content = db.Column(db.String)
    nsfw = db.Column(db.Boolean, default=False)


class OptInStatus(db.Table, table_name='opt_in_status'):
    user_id = db.Column(db.Integer(big=True), primary_key=True, index=True)
    public = db.Column(db.Boolean, default=False)
    nsfw = db.Column(db.Boolean, default=False)


class Logging(commands.Cog):
    """Allows to opt in/out of message logging by the bot."""

    def __init__(self, bot):
        self.bot = bot
        self._opted_in = set()
        self._log_nsfw = set()
        self._batch_lock = asyncio.Lock()

        self._logging_task.start()

    def cog_unload(self):
        self._logging_task.stop()

    @tasks.loop(seconds=60.0)
    async def _logging_task(self):
        async with self._batch_lock:
            async with self.bot.pool.acquire(timeout=300.0) as con:
                if self.bot._message_log:
                    query = "INSERT INTO message_log VALUES ($1, $2, $3, $4, $5, $6);"
                    await con.executemany(query, *self.bot._message_log)

            self.bot._message_log.clear()

    @_logging_task.before_loop
    async def _before_logging_task(self):
        await self.bot.wait_until_ready()

        for record in await self.bot.pool.fetch("SELECT * FROM opt_in_status;"):
            self._opted_in.add(record['user_id'])
            if record['nsfw']:
                self._log_nsfw.add(record['user_id'])

    @commands.group(name='logging')
    async def logging(self, ctx):
        """Logging management commands."""

    @logging.command(name='start')
    async def logging_start(self, ctx):
        """Opt into logging."""
        optin_status = await ctx.db.fetchrow("SELECT * FROM opt_in_status WHERE user_id = $1;", ctx.author.id)
        if optin_status:
            return await ctx.send('You have already opted in to logging.')
        await ctx.db.execute('INSERT INTO opt_in_status (user_id) VALUES ($1);', ctx.author.id)
        self._opted_in.add(ctx.author.id)
        await ctx.send(ctx.tick(True))

    @logging.command(name='stop')
    async def logging_stop(self, ctx):
        """Opt out of logging."""
        optin_status = await ctx.db.fetchrow("SELECT * FROM opt_in_status WHERE user_id = $1;", ctx.author.id)
        if not optin_status:
            return await ctx.send(f'You have not opted in to logging. You can do so with `{ctx.prefix}logging start`')
        await ctx.db.execute('DELETE FROM opt_in_status WHERE user_id = $1;', ctx.author.id)
        self._opted_in.remove(ctx.author.id)

        await ctx.send(ctx.tick(True))

    @logging.command(name='public')
    async def logging_public(self, ctx, public: bool):
        """Set your logging visibility preferences."""
        optin_status = await ctx.db.fetchrow("SELECT * FROM opt_in_status WHERE user_id = $1;", ctx.author.id)
        if not optin_status:
            return await ctx.send(f'You have not opted in to logging. You can do so with `{ctx.prefix}logging start`')
        await ctx.db.execute("UPDATE opt_in_status SET public = $1 WHERE user_id = $2;", public, ctx.author.id)
        await ctx.send(ctx.tick(True))

    @logging.command(name='nsfw')
    async def logging_nsfw(self, ctx, nsfw: bool):
        """Set your NSFW channel logging preferences."""
        optin_status = await ctx.db.fetchrow("SELECT * FROM opt_in_status WHERE user_id = $1;", ctx.author.id)
        if not optin_status:
            return await ctx.send(f'You have not opted in to logging. You can do so with `{ctx.prefix}logging start`')
        await ctx.db.execute("UPDATE opt_in_status SET nsfw = $1 WHERE user_id = $2;", nsfw, ctx.author.id)
        if nsfw:
            self._log_nsfw.add(ctx.author.id)
        else:
            with suppress(KeyError):
                self._log_nsfw.remove(ctx.author.id)
        await ctx.send(ctx.tick(True))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.content is None:
            return

        if message.author.id not in self._opted_in:
            return

        if message.guild is None:
            return

        if message.channel.is_nsfw() and message.author.id not in self._log_nsfw:
            return

        self.bot._message_log.append((message.channel.id, message.id, message.guild.id,
                                      message.author.id, message.content, message.channel.is_nsfw()))


def setup(bot):
    if not hasattr(bot, '_logging'):
        bot._logging = True
        bot._message_log = list()
    bot.add_cog(Logging(bot))
