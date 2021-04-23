import asyncio
import asyncpg
import discord
import datetime
import aiohttp
import bisect
from discord.ext import commands
from .utils import tokens


class API(commands.Cog, command_attrs=dict(hidden=True)):
    """Cog to wrap around my personal API."""
    BASE = 'https://api.varunj.tk/'

    def __init__(self, bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx):
        if not hasattr(self, 'token_handler'):
            pool = await asyncpg.create_pool(ctx.bot.config.api_db)
            self.token_handler = tokens.TokenUtils(pool)

    def cog_unload(self):
        self.bot.loop.create_task(self.close_db())

    async def close_db(self):
        await self.token_handler.pool.close()

    async def cog_command_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            return await ctx.send_help(ctx.command)

    @commands.group(name='api_token')
    @commands.is_owner()
    async def api_token(self, ctx):
        """Manages tokens used for authorisation on the API."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @api_token.command(name='new')
    async def api_token_new(self, ctx, user: discord.User, *, app_name=None):
        """Creates a new API token for a user.

        Supports multiple apps per user using the optional app_name parameter.
        """
        app_name = app_name or f'{user}\'s application'
        token = await self.token_handler.new_token(user.id, app_name)
        try:
            await user.send(f'Your token for `{app_name}` is `{token}`. Do not share this with anyone.')
        except discord.Forbidden:
            await ctx.author.send(f'{user}\'s token for `{app_name}`:\n`{token}`')

    @api_token.command(name='regenerate', aliases=['regen'])
    async def api_token_regenerate(self, ctx, user: discord.User, app_id: int):
        """Regenerate a token for a specific app."""
        token = await self.token_handler.regenerate_token(user.id, app_id)
        try:
            await user.send(f'Your new token is `{token}`. Do not share this with anyone.')
        except discord.Forbidden:
            await ctx.author.send(f'{user}\'s new token for app ID {app_id}:\n`{token}`')

    @api_token.group(name='delete')
    @commands.is_owner()
    async def api_token_delete(self, ctx):
        """Delete tokens for an app, or an entire user account."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @api_token_delete.command(name='user')
    async def api_token_delete_user(self, ctx, user: discord.User):
        """Deletes all tokens associated with this user account."""
        await self.token_handler.delete_user_account(user.id)
        await ctx.send(ctx.tick(True))

    @api_token_delete.command(name='app', aliases=['application'])
    async def api_token_delete_app(self, ctx, user: discord.User, app_id: int):
        """Delete the token for a particular app."""
        await self.token_handler.delete_app(user.id, app_id)
        await ctx.send(ctx.tick(True))

    @commands.command(name='antidepressant-or-tolkien', aliases=['antidepressant-tolkien',
        'drug-or-tolkien', 'drug-tolkien', 'tolkien-or-antidepressant', 'tolkien-or-drug',
        'tolkien-antidepressant', 'tolkien-drug', 't-or-a', 'a-or-t'])
    async def antidepressant_or_tolkien(self, ctx):
        """Guess if a word belongs to the Tolkien universe, or is the name of a drug.

        Inspired by [@checarina](https://twitter.com/checarina/status/977387234226855936)'s tweet.
        """
        drug_responses = ['drug', 'antidepressant', 'anti-depressant', 'd', 'a', 'ad']
        tolkien_responses = ['tolkien', 't']
        allowed_responses = drug_responses + tolkien_responses
        answers = {'tolkien': 'a Tolkien character', 'drug': 'an antidepressant'}
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in allowed_responses

        async with ctx.session.get(self.BASE + 'antidepressant-or-tolkien/random') as resp:
            js = await resp.json()

        await ctx.reply(f'**You have 15 seconds. Is this an antidepressant or a Tolkien character?**\n{js["name"]}')
        try:
            message = await ctx.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            return await ctx.send(f'Time\'s up! It was **{answers[js["type"]]}**\n\n_{js["text"]}_')
        if (message.content.lower() in drug_responses and js['type'] == 'drug') or \
                (message.content.lower() in tolkien_responses and js["type"] == 'tolkien'):
            await message.reply(f'Correct! it was **{answers[js["type"]]}**\n\n_{js["text"]}_')
        else:
            await message.reply(f'Oh no! It was **{answers[js["type"]]}**\n\n_{js["text"]}_')


def setup(bot):
    bot.add_cog(API(bot))
