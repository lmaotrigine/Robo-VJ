import discord
from discord.ext import commands
from .utils import cache, checks, db, time

PUB_QUIZ_ID = 718378271800033318

class Feeds(db.Table):
    id = db.PrimaryKeyColumn()
    channel_id = db.Column(db.Integer(big=True))
    role_id = db.Column(db.Integer(big=True))
    name = db.Column(db.String)

class Feeds(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @cache.cache()
    async def get_feeds(self, channel_id, *, connection=None):
        con = connection or self.bot.pool
        query = 'SELECT name, role_id FROM feeds WHERE channel_id = $1;'
        feeds = await con.fetch(query, channel_id)
        return {f['name']: f['role_id'] for f in feeds}

    @commands.group(name='feeds', invoke_without_commands=True)
    @commands.guild_only()
    async def _feeds(self, ctx):
        """Shows the list of feeds that the channel has.

        A feed is something that users can opt-in to
        receive news about a certain feed by running
        the `sub` command (and opt-out by doing the `unsub` command).
        You can publish to a feed by using the `publish` command.
        """

        feeds = await self.get_feeds(ctx.channel.id)

        if len(feeds) == 0:
            await ctx.send("This channel has no feeds.")
            return

        names = '\n'.join(f'- {r}' for r in feeds)
        await ctx.send(f'Found {len(feeds)} feeds.\n{names}')

    @_feeds.command(name='create')
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def feeds_create(self, ctx, *, name: str):
        """Creates a feed with the specified name

        You need Manage Roles permissions to create a feed.
        """

        name = name.lower()
        if name in ('@everyone', '@here'):
            return await ctx.send('That is an invalid feed name.')
        
        query = "SELECT role_id FROM feeds WHERE channel_id = $1 AND name = $2;"

        exists = await ctx.db.fetchrow(query, ctx.channel.id, name)
        if exists is not None:
            await ctx.send("This feed already exists.")
            return

        # create the role
        role = await ctx.guild.create_role(name=name, permissions=discord.Permissions.none())
        query = "INSERT INTO feeds (role_id, channel_id, name) VALUES ($1, $2, $3);"
        await ctx.db.execute(query, role.id, ctx.channel.id, name)
        self.get_feeds.invalidate(self, ctx.channel.id)
        await ctx.send(f'{ctx.tick(True)} Successfully created feed.')

    @_feeds.command(name='delete', aliases=['remove'])
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def feeds_delete(self, ctx, *, feed: str):
        """Removes a feed from the channel.

        This will also delete the associated role so this
        action is irreversible.
        """

        query = "DELETE FROM feeds WHERE channel_id = $1 AND name = $2 RETURNING *;"
        records = await ctx.db.fetch(query, ctx.channel.id, feed)
        self.get_feeds.invalidate(self, ctx.channel.id)

        if len(records) == 0:
            return await ctx.send('This feed does not exist.')

        for record in records:
            role = discord.utils.find(lambda r: r.id == record['role_id'], ctx.guild.roles)
            if role is not None:
                try:
                    await role.delete()
                except discord.HTTPException:
                    continue

        await ctx.send(f'{ctx.tick(True)} Removed feed.')

    async def do_subscription(self, ctx, feed, action):
        feeds = await self.get_feeds(ctx.channel.id)
        if len(feeds) == 0:
            await ctx.send('This channel has no feeds set up.')
            return

        if feed not in feeds:
            await ctx.send(f"This feed does not exist.\nValid feeds: {', '.join(feeds)}")
            return

        role_id = feeds[feed]
        role = discord.utils.find(lambda r: r.id == role_id, ctx.guild.roles)
        if role is not None:
            await action(role)
            await ctx.message.add_reaction(ctx.tick(True).strip('<:>'))
        else:
            await ctx.message.add_reaction(ctx.tick(False).strip('<:>'))

    @commands.command()
    @commands.guild_only()
    async def sub(self, ctx, *, feed: str):
        """Subscribes to the publication of a feed.

        This will allow you to receive updates from the channel
        owner. To unsubscribe, see the `unsub` command.
        """
        await self.do_subscription(ctx, feed, ctx.author.add_roles)

    @commands.command()
    @commands.guild_only()
    async def unsub(self, ctx, *, feed: str):
        """Unsubscribe to the publication of a feed.

        This will remove you from notifications of a feed you
        are no longer interested in. You can always sub back by
        using the `sub` command.
        """
        await self.do_subscription(ctx, feed, ctx.author.remove_roles)

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def publish(self, ctx, feed: str, *, content: str):
        """Publishes content to a feed.

        Everyone who is subscribed to the feed will be notified
        with the content. Use this to notify people of important
        events or changes.
        """
        feeds = await self.get_feeds(ctx.channel.id)
        feed = feed.lower()
        if feed not in feeds:
            await ctx.send('This feed does not exist.')
            return

        role = discord.utils.get(ctx.guild.roles, id=feeds[feed])
        if role is None:
            fmt = 'Uh... a fatal error occurred here. The role associated with ' \
                  'this feed has been removed or not found. ' \
                  'Please recreate the feed.'
            await ctx.send(fmt)
            return
        
        # delete the message we have used to invoke it
        try:
            await ctx.message.delete()
        except:
            pass

        # make the role mentionable
        await role.edit(mentionable=True)

        # then send the message
        mentions = discord.AllowedMentions(roles=[role])
        await ctx.send(f'{role.mention}: {content}'[:2000], allowed_mentions=mentions)

        # then make the role unmentionable
        await role.edit(mentionable=False)

def setup(bot):
    bot.add_cog(Feeds(bot))