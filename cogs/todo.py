import datetime
import discord
from discord.ext import commands, menus

from .utils.paginator import SimplePages
from .utils import checks, db, time


class TodoTable(db.Table, table_name='todo'):
    id = db.PrimaryKeyColumn()
    entity_id = db.Column(db.Integer(big=True))
    content = db.Column(db.String)
    created_at = db.Column(db.Datetime, default="now() at time zone 'utc'")


class TodoEntry:
    __slots__ = ('id', 'content', 'created')

    def __init__(self, entry):
        self.id = entry['id']
        self.content = entry['content']
        self.created = entry['created_at']

    def __str__(self):
        return f'{self.id}: {self.content} [{time.human_timedelta(self.created)}]'


class TodoPages(SimplePages):
    def __init__(self, entries, *, per_page=12):
        converted = [TodoEntry(entry) for entry in entries]
        super().__init__(converted, per_page=per_page)


class Todo(commands.Cog):
    """To-do lists."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            await ctx.send(error)

    @commands.group(name='todo', invoke_without_command=True)
    async def _todo(self, ctx):
        """Manage your personal to-do list."""
        await self.do_list(ctx, ctx.author)

    async def do_list(self, ctx, entity):
        records = await ctx.db.fetch("SELECT content, created_at FROM todo WHERE entity_id = $1;", entity.id)
        if not records:
            return await ctx.send(f'{entity} has no todo items pending.')
        items = [(record['content'], record['created_at']) for record in records]
        to_paginate = [{'id': i, 'content': content, 'created': created}
                       for i, (content, created) in enumerate(items, 1)]
        try:
            p = TodoPages(to_paginate)
            if isinstance(entity, (discord.User, discord.Member)):
                p.embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
            else:
                if not isinstance(entity, discord.Guild):
                    name = f'#{entity.name}'
                    entity = entity.guild
                else:
                    name = entity.name
                p.embed.set_author(name=name, icon_url=entity.icon_url)
            await p.start(ctx)
        except menus.MenuError as e:
            await ctx.send(e)

    async def do_remove(self, ctx, entity, index):
        query = "SELECT id FROM todo WHERE entity_id = $1 order by id;"
        records = await self.bot.pool.fetch(query, entity.id)
        items = [record['id'] for record in records]
        try:
            _id = items.pop(index - 1)
        except IndexError:
            raise commands.BadArgument('Invalid todo index provided.')
        async with self.bot.pool.acquire() as con:
            await con.execute("DELETE FROM todo WHERE id = $1;", _id)
        await ctx.send(f'Removed todo item at position `{index}`')

    async def do_add(self, ctx, entity, content, created=None):
        created = created or datetime.datetime.utcnow()
        query = "INSERT INTO todo (entity_id, content, created_at) VALUES ($1, $2, $3);"
        async with self.bot.pool.acquire() as con:
            await con.execute(query, entity.id, content, created)
        await ctx.send('\N{OK HAND SIGN}')

    @_todo.command(name='remove')
    async def todo_remove(self, ctx, index: int):
        """Remove an item from your to-do list."""
        await self.do_remove(ctx, ctx.author, index)

    @_todo.command(name='add')
    async def todo_add(self, ctx, *, content):
        """Add an item to your to-do list."""
        await self.do_add(ctx, ctx.author, content, created=ctx.message.created_at)

    @_todo.command(name='clear')
    async def todo_clear(self, ctx):
        """Clear all your to-do items."""
        query = "DELETE FROM todo WHERE entity_id = $1;"
        confirm = await ctx.prompt('This will clear all your personal todos across all servers.\nAre you sure?')
        if not confirm:
            return
        res = await ctx.db.execute(query, ctx.author.id)
        if res == 'DELETE 0':
            await ctx.send('You don\'t have any personal todo items, hence nothing was deleted.')
        else:
            await ctx.send('Deleted all your personal todo items.')

    @_todo.group(name='server', invoke_without_command=True)
    @commands.guild_only()
    async def todo_server(self, ctx):
        """Manages this server's to-do list.

        Requires you to have Manage Server permissions to modify.
        """
        await self.do_list(ctx, ctx.guild)

    @todo_server.command(name='add')
    @checks.is_mod()
    async def server_add(self, ctx, *, content):
        """Add an item to this server's to-do list."""
        await self.do_add(ctx, ctx.guild, content, created=ctx.message.created_at)

    @todo_server.command(name='remove')
    @checks.is_mod()
    async def server_remove(self, ctx, index: int):
        """Remove an item from this server's to-do list."""
        await self.do_remove(ctx, ctx.guild, index)

    @todo_server.command(name='clear')
    @checks.is_mod()
    async def server_clear(self, ctx):
        """Clears this server's to-do list."""
        query = "DELETE FROM todo WHERE entity_id = $1;"
        confirm = await ctx.prompt('This will clear all of this server\'s todos.\nAre you sure?')
        if not confirm:
            return
        res = await ctx.db.execute(query, ctx.guild.id)
        if res == 'DELETE 0':
            await ctx.send('There are no pending todo items for this server, hence nothing was deleted.')
        else:
            await ctx.send('Deleted all todo items for this server.')

    @_todo.group(name='channel', invoke_without_command=True)
    @commands.guild_only()
    async def todo_channel(self, ctx):
        """Manages this channel's to-do list.

        Requires you to have Manage Channels permissions to modify.
        """
        await self.do_list(ctx, ctx.channel)

    @todo_channel.command(name='add')
    @checks.has_guild_permissions(manage_channels=True)
    async def channel_add(self, ctx, *, content):
        """Adds an item to this channel's to-do list."""
        await self.do_add(ctx, ctx.channel, content, created=ctx.message.created_at)

    @todo_channel.command(name='remove')
    @checks.has_guild_permissions(manage_channels=True)
    async def channel_remove(self, ctx, index: int):
        """Removes an item from this channel's to-do list."""
        await self.do_remove(ctx, ctx.channel, index)

    @todo_channel.command(name='clear')
    @checks.has_guild_permissions(manage_channels=True)
    async def channel_clear(self, ctx):
        """Clears this channel's to-do list."""
        query = "DELETE FROM todo WHERE entity_id = $1;"
        confirm = await ctx.prompt('This will clear all of this channel\'s todos.\nAre you sure?')
        if not confirm:
            return
        res = await ctx.db.execute(query, ctx.channel.id)
        if res == 'DELETE 0':
            await ctx.send('There are no pending todo items for this channel, hence nothing was deleted.')
        else:
            await ctx.send('Deleted all todo items for this channel.')


def setup(bot):
    bot.add_cog(Todo(bot))
