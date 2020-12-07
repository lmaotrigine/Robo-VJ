import discord
from discord.ext import commands, tasks, menus
import asyncio
import traceback
import sqlite3
import aiosqlite
import contextlib


__all__ = 'PokeApiCog',


class ConfirmationMenu(menus.Menu):
    async def send_initial_message(self, ctx, channel):
        return await ctx.reply('This can take up to 30 minutes. Are you sure?')

    @menus.button('\N{CROSS MARK}')
    async def abort(self, payload):
        await self.message.edit(content='Aborting.', delete_after=10)
        self.stop()

    @menus.button('\N{WHITE HEAVY CHECK MARK}')
    async def confirm(self, payload):
        await self.message.edit(content='Confirmed.', delete_after=10)
        await self.ctx.cog.do_rebuild_pokeapi(self.ctx)
        self.stop()

    async def finalize(self, timed_out):
        if timed_out:
            await self.message.edit(content='Request timed out.', delete_after=10)


class SqlResponseEmbed(menus.ListPageSource):
    async def format_page(self, menu: menus.MenuPages, page):
        return discord.Embed(
            title=menu.sql_cmd,
            description=page,
            colour=0xF47FFF
        ).set_footer(
            text=f'Page {menu.current_page + 1}/{self.get_max_pages()}'
        )


class PokeApiCog(commands.Cog, name='PokeApi', command_attrs={'hidden': True}):
    def __init__(self, bot):
        self.bot = bot
        self._lock = asyncio.Lock()

    @contextlib.asynccontextmanager
    async def disable_pokeapi(self):
        factory = self.bot._pokeapi
        self.bot.pokeapi = None
        yield
        self.bot.pokeapi = factory

    def cog_unload(self):
        assert not self._lock.locked(), 'PokeApi is locked.'

    async def do_rebuild_pokeapi(self, ctx):
        shell = await asyncio.create_subprocess_shell('../../setup_pokeapi.sh')
        embed = discord.Embed(title='Updating PokeAPI', description='Started', colour=0xF47FFF)
        msg = await ctx.send(embed=embed)

        @tasks.loop(seconds=10)
        async def update_msg():
            elapsed = (update_msg._next_iteration - msg.created_at).total_seconds()
            embed.description = f'Still running... ({elapsed:.0f}s)'
            await msg.edit(embed=embed)

        @update_msg.before_loop
        async def before_update():
            await asyncio.sleep(10)

        done, pending = await asyncio.wait({update_msg.start(), self.bot.loop.create_task(shell.wait)},
                                           return_when=asyncio.FIRST_COMPLETED)
        [task.cancel() for task in pending]
        try:
            done.pop().result()
        except Exception as e:
            embed.colour = discord.Colour.red()
            tb = ''.join(traceback.format_exception(e.__class__, e, e.__traceback__))
            if len(tb) > 2040:
                tb = '...\n' + tb[-2036:]
            embed.title = 'Update failed.'
            embed.description = f'```\n{tb}\n```'
        else:
            embed.colour = discord.Colour.green()
            embed.title = 'Update Succeeded!'
            embed.description = 'You can now use pokeapi again'
        await msg.edit(embed=embed)

    @commands.group()
    async def pokeapi(self, ctx):
        """Commands for interfacing with pokeapi"""

    @commands.max_concurrency(1)
    @commands.is_owner()
    @pokeapi.command(name='rebuild', aliases=['update'])
    async def rebuild_pokeapi(self, ctx):
        """Rebuild the pokeapi database."""
        async with self._lock, self.disable_pokeapi():
            menu = ConfirmationMenu(timeout=60.0, clear_reactions_after=True)
            await menu.start(ctx, wait=True)

    @pokeapi.command(name='sql')
    @commands.is_owner()
    async def execute_sql(self, ctx: commands.Context, *, query):
        """Run arbitrary SQL command"""

        async with ctx.typing():
            pokeapi = self.bot.pokeapi
            async with pokeapi.execute(query) as cur:  # type: aiosqlite.Cursor
                header = '|'.join(col[0] for col in cur.description)
                pag = commands.Paginator(f'```\n{header}\n{"-" * len(header)}', max_size=2048)
                for i, row in enumerate(await cur.fetchall(), 1):  # type: [int, tuple]
                    pag.add_line('|'.join(map(str, row)))
                    if i % 20 == 0:
                        pag.close_page()

        if pag.pages:
            menu = menus.MenuPages(SqlResponseEmbed(pag.pages, per_page=1), delete_message_after=True,
                                   clear_reactions_after=True)
            menu.sql_cmd = query if len(query) < 256 else '...' + query[-253:]
            await menu.start(ctx)
        else:
            await ctx.send('Operation completed. No rows returned.')
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

    @execute_sql.error
    async def pokeapi_sql_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            error = error.original
        if isinstance(error, sqlite3.Error):
            query = ctx.kwargs['query']
            query = query if len(query) < 256 else '...' + query[-253:]
            await ctx.message.add_reaction('\N{CROSS MARK}')
            embed = discord.Embed(
                title=query,
                description=f'**ERROR**: {error}',
                colour=discord.Colour.red()
            )
            await ctx.send(embed=embed)
