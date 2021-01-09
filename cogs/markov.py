from functools import partial
import asyncpg
from typing import Awaitable, Dict, List, Optional, Tuple

import rusty_markov as markov

import discord
from discord.ext import commands

MAX_TRIES = 32


def make_sentence(model: markov.Markov, order: int, *, seed: str = None, tries=MAX_TRIES) -> Optional[str]:
    while tries >= 0:
        try:
            if seed is None:
                sentence = model.generate()
            else:
                sentence = model.generate_seeded(seed)

            if len(sentence.split()) < order * 4 and tries > 0:
                raise Exception('Markov too small.')
            return sentence

        except Exception:
            return make_sentence(model, order, seed=seed, tries=tries - 1)
    return None


def make_code(model: markov.Markov, order: int, *, seed: str = None, tries=MAX_TRIES * 8) -> Optional[str]:
    while tries >= 0:
        try:
            sentence = model.generate()

            if '```' not in sentence:
                raise Exception('Not a code block.')

            if len(sentence.split()) < order * 8 and tries > 0:
                raise Exception('Markov too small.')

            return sentence

        except Exception:
            return make_code(model, order, tries=tries - 1)
    return None


class Markov(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model_cache: Dict[Tuple[int, ...], markov.Markov] = markov.LRUDict(max_size=12)  # idk about a good size

    async def get_model(self, query: Tuple[int, ...], *coros: Awaitable[List[asyncpg.Record]], order: int = 2) -> markov.Markov:
        # Return cached model if one exists
        if query in self.model_cache:
            return self.model_cache[query]

        # Generate the model
        data: List[str] = list()
        for coro in coros:
            records: List[asyncpg.Record] = await coro
            data.extend([record['content'] for record in records])
        if not data:
            raise commands.BadArgument('There was not enough message log data, please try again later.')

        def generate_model():
            model = markov.Markov(order)
            model.train(data)
            return model

        self.model_cache[query] = m = await self.bot.loop.run_in_executor(None, generate_model)
        return m

    async def send_markov(self, ctx, model: markov.Markov, order: int, *, seed: str = None, callable=make_sentence):
        markov_call = partial(callable, model, order, seed=seed)
        markov = await self.bot.loop.run_in_executor(None, markov_call)

        if not markov:
            raise commands.BadArgument('Markov could not be generated.')
        allowed_mentions = discord.AllowedMentions(users=True)

        await ctx.send(markov, allowed_mentions=allowed_mentions)

    @commands.command(aliases=['um'])
    async def user_markov(self, ctx, *, user: discord.User = None):
        """Generate a markov chain based off a user's messages."""

        user = user or ctx.author

        async with ctx.typing():
            query = "SELECT * FROM opt_in_status WHERE user_id = $1;"
            data = await ctx.db.fetchrow(query, user.id)
            if not data:
                if user == ctx.author:
                    return await ctx.send(f'You have not opted in to logging. You can do so with `{ctx.prefix}logging start`')
                else:
                    return await ctx.send(f'User "{user}" has not opted in to logging.')

            if user != ctx.author and not data['public']:
                return await ctx.send(f'User "{user}" has not made their logs public.')

            query = "SELECT content FROM message_log WHERE user_id = $1 and nsfw <= $2 AND content LIKE '% %';"
            nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
            coro = ctx.db.fetch(query, user.id, nsfw)
            args = (nsfw, 2, user.id)
            model = await self.get_model(args, coro, order=2)

        await self.send_markov(ctx, model, 2)

    @commands.command(aliases=['sum'])
    async def seeded_user_markov(self, ctx, user: discord.User = None, *, seed: str):
        """Generate a markov chain based off a users messages which starts with a given seed."""

        user = user or ctx.author

        async with ctx.typing():
            query = "SELECT * FROM opt_in_status WHERE user_id = $1;"
            data = await ctx.db.fetchrow(query, user.id)
            if not data:
                if user == ctx.author:
                    return await ctx.send(f'You have not opted in to logging. You can do so with `{ctx.prefix}logging start`')
                else:
                    return await ctx.send(f'User "{user}" has not opted in to logging.')

            if user != ctx.author and not data['public']:
                return await ctx.send(f'User "{user}" has not made their logs public.')

            query = "SELECT content FROM message_log WHERE user_id = $1 and nsfw <= $2 AND content LIKE '% %';"
            nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
            coro = ctx.db.fetch(query, user.id, nsfw)
            args = (nsfw, 2, user.id)
            model = await self.get_model(args, coro, order=2)

        await self.send_markov(ctx, model, 2, seed=seed.lower())

    @commands.command(aliases=['mum'])
    async def multi_user_markov(self, ctx, *users: discord.User):
        """Generate a markov chain based off a list of users messages."""
        users = set(users)
        if len(users) < 2:
            return await ctx.send('You need to specify at least two users.')

        is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
        coros = list()

        async with ctx.typing():
            for user in users:
                query = "SELECT * FROM opt_in_status WHERE user_id = $1;"
                data = await ctx.db.fetchrow(query, user.id)
                if not data:
                    if user == ctx.author:
                        return await ctx.send(f'You have not opted in to logging. You can do so with `{ctx.prefix}logging start`')
                    else:
                        return await ctx.send(f'User "{user}" has not opted in to logging.')

                if user != ctx.author and not data['public']:
                    return await ctx.send(f'User "{user}" has not made their logs public.')

                query = "SELECT content FROM message_log WHERE user_id = $1 and nsfw <= $2 AND content LIKE '% %';"
                nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
                coros.append(ctx.db.fetch(query, user.id, nsfw))
            args = (nsfw, 3) + tuple(user.id for user in users)
            model = await self.get_model(args, *coros, order=3)

        await self.send_markov(ctx, model, 3)

    @commands.command(aliases=['dum'])
    async def dual_user_markov(self, ctx, *, user: discord.User):
        """Generate a markov chain based off you and another users messages."""
        if user == ctx.author:
            return await ctx.send('You can\'t generate a dual user markov with yourself.')

        await ctx.invoke(self.multi_user_markov, ctx.author, user)

    @commands.command(aliases=['gm'])
    @commands.guild_only()
    async def guild_markov(self, ctx):
        """Generates a markov chain based off messages in the server."""
        async with ctx.typing():
            is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
            args = (is_nsfw, 3, ctx.guild.id)
            query = "SELECT content FROM message_log WHERE guild_id = $1 AND nsfw <= $2 AND content LIKE '% %'"
            coro = ctx.db.fetch(query, ctx.guild.id, is_nsfw)
            model = await self.get_model(args, coro, order=3)
        await self.send_markov(ctx, model, 3)

    @commands.command(aliases=['cgm'])
    @commands.guild_only()
    async def code_guild_markov(self, ctx):
        """Generate a markov chain code block."""
        async with ctx.typing():
            is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
            args = (is_nsfw, 2, ctx.guild.id)
            query = "SELECT content FROM message_log WHERE guild_id = $1 AND nsfw <= $2 AND content LIKE '% %'"
            coro = ctx.db.fetch(query, ctx.guild.id, is_nsfw)
            model = await self.get_model(args, coro, order=2)
        await self.send_markov(ctx, model, 2, callable=make_code)

    @commands.command(aliases=['cum'])
    async def code_user_markov(self, ctx, user: discord.User = None):
        """Generate a markov chain code block."""
        user = user or ctx.author

        async with ctx.typing():
            query = "SELECT * FROM opt_in_status WHERE user_id = $1;"
            data = await ctx.db.fetchrow(query, user.id)
            if not data:
                if user == ctx.author:
                    return await ctx.send(
                        f'You have not opted in to logging. You can do so with `{ctx.prefix}logging start`')
                else:
                    return await ctx.send(f'User "{user}" has not opted in to logging.')

            if user != ctx.author and not data['public']:
                return await ctx.send(f'User "{user}" has not made their logs public.')
            is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
            args = (is_nsfw, 2, user.id)

            query = "SELECT content FROM message_log WHERE user_id = $1 and nsfw <= $2 AND content LIKE '% %';"
            coro = ctx.db.fetch(query, user.id, is_nsfw)
            model = await self.get_model(args, coro, order=2)
        await self.send_markov(ctx, model, 2, callable=make_code)

    @commands.command(aliases=['sgm'])
    async def seeded_guild_markov(self, ctx, *, seed: str):
        """Generate a markov chain based off messages in the server which starts with a given seed."""
        async with ctx.typing():
            is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
            args = (is_nsfw, 3, ctx.guild.id)
            query = "SELECT content FROM message_log WHERE guild_id = $1 AND nsfw <= $2 AND content LIKE '% %'"
            coro = ctx.db.fetch(query, ctx.guild.id, is_nsfw)
            model = await self.get_model(args, coro, order=3)
        await self.send_markov(ctx, model, 3, seed=seed.lower())

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)


def setup(bot):
    bot.add_cog(Markov(bot))
