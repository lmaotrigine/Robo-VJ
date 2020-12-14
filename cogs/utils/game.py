import asyncio
import discord
import math
import time
from discord.ext import commands
from . import db


class GameTable(db.Table, table_name='game'):
    id = db.Column(db.Integer(big=True))
    name = db.Column(db.String)
    score = db.Column(db.Integer, default=0)


class BadGameArgument(commands.BadArgument):
    pass


def find_emoji(guild, name, case_sensitive=True):
    def lower(s):
        return s if case_sensitive else s.lower()

    return discord.utils.find(lambda e: lower(name) == lower(e.name), guild.emojis)


async def increment_score(connection, player, *, by=1):
    query = """INSERT INTO game VALUES ($1, $2, $3)
               ON CONFLICT (id) DO UPDATE
               SET score = game.score + $3"""
    await connection.execute(query, player.id, player.name, by)


class GameBase:
    __slots__ = (
        'bot', '_timeout', '_lock', '_max_score', '_state', '_running', '_message', '_task',
        'start_time', '_players', '_solution'
    )

    def __init__(self, bot, timeout=90, max_score=1000):
        self.bot = bot
        self._timeout = timeout
        self._lock = asyncio.Lock()
        self._max_score = max_score
        self.reset()

    async def __aenter__(self):
        await self._lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()

    def reset(self):
        self._state = None
        self._running = False
        self._message = None
        self._task = None
        self.start_time = -1
        self._players = set()
        self._solution = None

    @property
    def state(self):
        return self._state

    @property
    def score(self):
        end_time = time.time()
        if self._timeout is None:
            time_factor = 2 ** ((self.start_time - end_time) / 300.0)
        else:
            time_factor = (self._timeout - end_time + self.start_time) / self._timeout
        return max(int(math.ceil(self._max_score * time_factor)), 1)

    @property
    def running(self):
        return self._running

    @running.setter
    def running(self, state):
        self._running = state

    def __str__(self):
        pass

    def add_player(self, player):
        self._players.add(player)

    def get_player_names(self):
        return ', '.join(player.name for player in self._players)

    async def timeout(self, ctx):
        await asyncio.sleep(self._timeout)
        if self.running:
            await ctx.send('Time\'s up!')
            self.bot.loop.create_task(self.end(ctx, failed=True))

    async def start(self, ctx):
        def destroy_self(task):
            self._task = None

        self.running = True
        self._message = await ctx.send(self)
        if self._timeout is None:
            self._task = self.bot.loop.create_future()
        else:
            self._task = self.bot.loop.create_task(self.timeout(ctx))
        self._task.add_done_callback(destroy_self)
        self.start_time = time.time()

    async def end(self, ctx, failed=False, aborted=False):
        if self.running:
            if self._task and not self._task.done():
                self._task.cancel()
            return True
        return False

    async def show(self, ctx):
        if self.running:
            await self._message.delete()
            self._message = await ctx.send(self)
            return self._message
        return None

    async def award_points(self):
        score = max(math.ceil(self.score / len(self._players)), 1)
        async with self.bot.pool.acquire() as conn:
            for player in self._players:
                await increment_score(conn, player, by=score)
        return score
    
    async def get_solution_embed(self, *, failed=False, aborted=False):
        sprite_url = await self.bot.pokeapi.get_species_sprite_url(self._solution)
        return discord.Embed(
                title=self._solution['name'].title(),
                colour=discord.Colour.red() if failed or aborted else discord.Colour.green()
            ).set_image(url=sprite_url or discord.Embed.Empty)

class GameCogBase(commands.Cog):
    gamecls = None

    def _local_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage('This command cannot be used in private messages.')
        return True

    def __init__(self, bot):
        if self.gamecls is None:
            raise NotImplemented('This class must be subclassed.')
        self.bot = bot
        self.channels = {}

    def __getitem__(self, channel):
        if channel not in self.channels:
            self.channels[channel] = self.gamecls(self.bot)
        return self.channels[channel]

    async def game_cmd(self, cmd, ctx, *args, **kwargs):
        async with self[ctx.channel.id] as game:
            cb = getattr(game, cmd)
            if cb is None:
                await ctx.send(f'{ctx.author.mention}: Invalid command: '
                               f'{ctx.prefix}{self.gamecls.__class__.__name__.lower()} {cmd}', delete_after=10)
            else:
                await cb(ctx, *args, **kwargs)

    async def _error(self, ctx, exc):
        if isinstance(exc, BadGameArgument):
            await ctx.send(f'{ctx.author.mention}: Invalid arguments. '
                           f'Try using two numbers (i.e. 2 5) or a letter '
                           f'and a number (i.e. c2).',
                           delete_after=10)
