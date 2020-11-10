import random
from datetime import datetime

import discord
import pytz
from discord.ext import commands, menus
from fuzzywuzzy import process
from .utils import db, time
from .utils.paginator import RoboPages

PYTZ_LOWER_TIMEZONES = [*map(str.lower, pytz.all_timezones)]

class TZMenuSource(menus.ListPageSource):
    def __init__(self, data, embeds):
        self.data = data
        self.embeds = embeds
        super().__init__(data, per_page=1)

    async def format_page(self, menu, page):
        return self.embeds[page]

class TimeTable(db.Table, table_name='tz_store'):
    """Table for timezones. Unique per user, with guild array."""
    user_id = db.Column(db.Integer(big=True), primary_key=True)
    guild_ids = db.Column(db.Array(db.Integer(big=True)))
    tz = db.Column(db.String, unique=True)

class TimezoneConverter(commands.Converter):
    async def convert(self, ctx, argument: str):
        query = process.extract(query=argument.lower(), choices=pytz.all_timezones_set, limit=5)
        if argument.lower() not in {timezone.lower() for timezone in pytz.all_timezones_set}:
            matches = '\n'.join([f'`{index + 1}.` {match[0]}' for index, match in enumerate(query)])
            raise commands.BadArgument(f'That was not a recognised timezone. Maybe you meant one of these?\n{matches}')
        return pytz.timezone(query[0][0])

class Time(commands.Cog):
    """Time cog for fun time stuff."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        query = """WITH corrected AS (
                       SELECT user_id, array_agg(guild_id) new_guild_ids
                       FROM tz_store, unnest(guild_ids) WITH ORDINALITY guild_id
                       WHERE guild_id != $1
                       GROUP BY user_id
                   )
                   UPDATE tz_store
                   SET guild_ids = new_guild_ids
                   FROM corrected
                   WHERE guild_ids <> new_guild_ids
                   AND tz_store.user_id = corrected.user_id;
                """
        return await self.bot.pool.execute(query, guild.id)

    async def cog_command_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, commands.BadArgument):
            return await ctx.send(str(error))

    def _gen_tz_embeds(self, requester: str, iterable: list):
        embeds = []
        for item in iterable:
            embed = discord.Embed(title='Timezone lists', colour=discord.Colour.green())
            embed.description = '\n'.join(item)
            fmt = f'Page {iterable.index(item) + 1}/{len(iterable)}'
            embed.set_footer(text=f'{fmt} | Requested by: {requester}')
            embeds.append(embed)
        return embeds

    def _curr_tz_time(self, curr_timezone: pytz.BaseTzInfo, *, ret_datetime: bool=False):
        # We assume it's a good TZ here
        dt_obj = datetime.now(curr_timezone)
        if ret_datetime:
            return dt_obj
        return time.hf_time(dt_obj)

    @commands.command(aliases=['tz'])
    async def timezone(self, ctx, *, timezone: TimezoneConverter=None):
        """This will return the time in a specified timezone."""
        if not timezone:
            timezone = random.choice(pytz.all_timezones)
        embed = discord.Embed(title=f'Current time in {timezone}', description=f'```\n{self._curr_tz_time(timezone, ret_datetime=False)}\n```')
        embed.set_footer(text=f'Requested by: {ctx.author}')
        embed.timestamp = datetime.utcnow()
        return await ctx.send(embed=embed)

    @commands.command(aliases=['tzs'])
    @commands.cooldown(1, 15, commands.BucketType.channel)
    async def timezones(self, ctx):
        tz_list = [pytz.all_timezones[x:x+15]
                   for x in range(0, len(pytz.all_timezones), 15)]
        embeds = self._gen_tz_embeds(str(ctx.author), tz_list)
        pages = RoboPages(source=TZMenuSource(range(0, 40), embeds))
        await pages.start(ctx)

    @commands.group(name='time', invoke_without_command=True)
    @commands.guild_only()
    async def _time(self, ctx, *, member: discord.Member=None):
        """Let's look at storing member's tz."""
        if ctx.invoked_subcommand:
            pass
        member = member or ctx.author
        query = """SELECT *
                   FROM tz_store
                   WHERE user_id = $1
                   AND $2 = ANY(guild_ids)
                """
        result = await self.bot.pool.fetchrow(query, member.id, ctx.guild.id)
        if not result:
            return await ctx.send(f'No timezone for {member} set or it\'s not public in this guild.')
        member_timezone = result['tz']
        tz = await TimezoneConverter().convert(ctx, member_timezone)
        current_time = self._curr_tz_time(tz, ret_datetime=False)
        embed = discord.Embed(title=f'Time for {member}', description=f'```\n{current_time}\n```')
        embed.set_footer(text=member_timezone)
        embed.timestamp = datetime.utcnow()
        return await ctx.send(embed=embed)

    @_time.command(name='set')
    @commands.guild_only()
    async def time_set(self, ctx, *, set_timezone: TimezoneConverter):
        """Add your timezone, with a warning about public info."""
        query = """INSERT INTO tz_store (user_id, guild_ids, tz)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (user_id) DO UPDATE
                   SET guild_ids = tz_store.guild_ids || $2, tz = $3
                   WHERE tz_store.user_id = $1;
                """
        confirm = await ctx.prompt('This will make your timezone public in this guild. confirm?', reacquire=False)
        if not confirm:
            return
        await self.bot.pool.execute(query, ctx.author.id, [ctx.guild.id], set_timezone.zone)
        return await ctx.message.add_reaction(ctx.tick(True))

    @_time.command(name='remove')
    @commands.guild_only()
    async def time_remove(self, ctx):
        """Remove your timezone from this guild."""
        query = """WITH corrected AS (
                       SELECT user_id, array_agg(guild_id) new_guild_ids
                       FROM tz_store, unnest(guild_ids) WITH ORDINALITY guild_id
                       WHERE guild_id != $2
                       AND user_id = $1
                       GROUP BY user_id
                   )
                   UPDATE tz_store
                   SET guild_ids = new_guild_ids
                   FROM corrected
                   WHERE guild_ids <> new_guild_ids
                   AND tz_store.user_id = corrected.user_id;
                """
        await self.bot.pool.execute(query, ctx.author.id, ctx.guild.id)
        return await ctx.message.add_reaction(ctx.tick(True))

    @_time.command(name='clear')
    async def time_clear(self, ctx):
        """Clears your timezones from all guilds."""
        query = "DELETE FROM tz_store WHERE user_id = $1;"
        confirm = await ctx.prompt("Are you sure you wish to purge your timezone from all guilds?")
        if not confirm:
            return
        await self.bot.pool.execute(query, ctx.author.id)
        return await ctx.message.add_reaction(ctx.tick(True))

    async def _time_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send("How am I supposed to do this if you don't supply the timezone?")

def setup(bot):
    bot.add_cog(Time(bot))