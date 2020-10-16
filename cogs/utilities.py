"""
Utitlities cog for Discord bot
"""
import json
import datetime
import asyncpg
import asyncio
import re
import discord
from discord.ext import commands, tasks
from typing import Optional, Tuple
from .utils import checks

def q_channel_protection(ctx):
    """
    Prevents question channel from being wiped by anyone other than owner
    """
    if ctx.guild is None:
        return True
    if ctx.guild.id not in ctx.bot.qchannels.keys():
        return True
    if ctx.channel.id == ctx.bot.qchannels[ctx.guild.id] and ctx.author == ctx.guild.owner:
        return True
    if ctx.channel.id != ctx.bot.qchannels[ctx.guild.id]:
        return True
    return False

class Prefix(commands.Converter):
    async def convert(self, ctx, argument):
        user_id = ctx.bot.user.id
        if argument.startswith((f'<@{user_id}>', f'<@!{user_id}>')):
            raise commands.BadArgument('That is a reserved prefix already in use.')
        return argument

class Utilities(commands.Cog):
    """Utilities for your server. Require manage server permissions to use"""
    def __init__(self, bot):
        self.bot = bot
        self.guild_state= {}

    @commands.command()
    @commands.guild_only()
    @checks.is_mod()
    @commands.check(q_channel_protection)
    async def wipe(self, ctx, limit):
        """
        Wipes a number of messages from current channel.
        (Upto 200 messages in the past 14 days.)
        """
        if limit.lower() == "all":
            limit = None
        else:
            try:
                limit = int(limit)
            except ValueError:
                await ctx.send("Please enter a valid number of messages to wipe (Add 2 to your originally intended number). Enter `all` to wipe the entire channel. (Upto 100 messages in the past 14 days.)")
                return
        if ctx.channel == self.bot.get_channel(self.bot.qchannels.get(ctx.guild.id)):
            msg = await ctx.send(f"React with \U00002705 to confirm wiping question channel.\nReact with \U0000274c to cancel.")
            await msg.add_reaction('\U00002705')
            await msg.add_reaction('\U0000274c')
            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ['\U00002705', '\U0000274c'] and reaction.message == msg
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            except asyncio.TimeoutError:
                await ctx.send("Timeout! Cancelling operation...", delete_after=20.0)
                await msg.delete()
                await ctx.message.delete()
            else:
                if str(reaction.emoji) == '\U0000274c':
                    await ctx.send("Cancelling...", delete_after=20.0)
                    await msg.delete()
                    await ctx.message.delete()
                elif str(reaction.emoji) == '\U00002705':
                    await msg.delete()
                    await ctx.message.delete()
                    await ctx.channel.purge(limit=limit)
        else:
            await ctx.message.delete()
            await ctx.channel.purge(limit=limit)


    @wipe.error
    async def wipe_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.message.delete()
            await ctx.send("Please enter a number of messages to wipe (Accomodate this message into your count). Enter `all` to wipe the entire channel. (Upto 100 messages in the past 14 days.)")

    @commands.group(name='prefix', invoke_without_command=True)
    async def prefix(self, ctx):
        """Manages the server's custom prefixes.
        If called without a subcommand, this will list the currently set
        prefixes.
        """
                
        prefixes = self.bot.get_guild_prefixes(ctx.guild)
        
        # we want to remove prefix #2, because it's the second form of the mention
        # and to the end user, this would end up making them confused why the
        # mention is there twice
        del prefixes[1]

        embed = discord.Embed(title='Prefixes', colour=discord.Colour.blurple())
        embed.set_footer(text=f'{len(prefixes)} prefixes')
        embed.description = '\n'.join(f'{index}. {elem}' for index, elem in enumerate(prefixes, 1))
        await ctx.send(embed=embed)

    @prefix.command(name='add', ignore_extra=False)
    async def prefix_add(self, ctx, prefix: Prefix):
        """Appends a prefix to the list of custom prefixes.
        
        Previously set prefixes are not overridden.
        
        To have a word prefix, you should quote it and end it with
        a space, e.g. "hello " to set the prefix to "hello ". This
        is because Discord removes spaces when sending messages so
        the spaces are not preserved.
        
        Multi-word prefixes must be quoted also.
        
        You must have Manage Server permission to use this command.
        """
        current_prefixes = self.bot.get_raw_guild_prefixes(ctx.guild.id)
        current_prefixes.append(prefix)
        try:
            await self.bot.set_guild_prefixes(ctx.guild, current_prefixes)
        except Exception as e:
            await ctx.send(f'{ctx.tick(False)} {e}')
        else:
            await ctx.send(ctx.tick(True))

    @prefix_add.error
    async def prefix_add_error(self, ctx, error):
        if isinstance(error, commands.TooManyArguments):
            await ctx.send("You've given too many prefixes. Either quote it or only do it one by one.")

    @prefix.command(name='remove', aliases=['delete'], ignore_extra=False)
    async def prefix_remove(self, ctx, prefix: Prefix):
        """Removes a prefix from the list of custom prefixes.
        
        This is the inverse of the 'prefix add' command. You can
        use this to remove prefixes from the default set as well.
        
        You must have Manage Server permission to use this command.
        """
        current_prefixes = self.bot.get_raw_guild_prefixes(ctx.guild.id)

        try:
            current_prefixes.remove(prefix)
        except ValueError:
            return await ctx.send('I do not have this prefix registered.')

        try:
            await self.bot.set_guild_prefixes(ctx.guild, current_prefixes)
        except Exception as e:
            await ctx.send(f'{ctx.tick(False)} {e}')
        else:
            await ctx.send(ctx.tick(True))

    @prefix.command(name='clear')
    @checks.is_mod()
    async def prefix_clear(self, ctx):
        """Removes all custom prefixes.
        After this, the bot will listen to only mention prefixes.
        You must have Manage Server permission to use this command.
        """

        await self.bot.set_guild_prefixes(ctx.guild, [])
        await ctx.send(ctx.tick(True))


    @commands.command()
    @commands.guild_only()
    @checks.is_mod()
    async def purgeroles(self, ctx, *, args):
        """Clears all roles of a particular member, or all members of a particular role.


            Syntax: purgeroles @member1 @member2
                    # or
                    purgeroles @member1 @member2 @role
                    # or
                    purgeroles @role
                    
            You must have Manage Server permissions to use this command."""
        members = []
        role = None
        for arg in args.split():
            if len(id := re.findall('<@!?([0-9]+)>', arg)) == 1:
                members.append(ctx.guild.get_member(int(id[0])))
            elif len(id := re.findall('<@&([0-9]+)>', arg)) == 1:
                role = ctx.guild.get_role(int(id[0]))
                break
        
        if role:
            flag = False
            if len(members) == 0:
                flag - True
                members = role.members
            for member in members:
                if role in member.roles:
                    try:
                        await member.remove_roles(role)
                    except discord.Forbidden:
                        await ctx.send(content=f"Cannot remove role {role.mention}. It is a higher or equal role to the bot.", delete_after=30.0)
                        return

                else:
                    await ctx.send(content=f"{member.mention} does not have the role {role.mention}. Ignoring...", delete_after=30.0)
                await asyncio.sleep(1)
            if flag:
                return await ctx.send(f"Purged {role.mention}")
        else:
            for member in members:
                await asyncio.sleep(1)
                if len(member.roles) > 3:
                    try:
                        await member.edit(roles=[])
                    except discord.Forbidden:
                        await ctx.send(f"{member.mention} has one or more roles higher than the bot. Please specify which roles to remove.", delete_after=30.0)
                else:
                    for role in member.roles[1:]:
                        await asyncio.sleep(1)
                        try:
                            await member.remove_roles(role)
                        except discord.Forbidden:
                            await ctx.send(content=f"Cannot remove role {role.mention}. Attempting to remove other roles...", delete_after=30.0)
                            continue
        
        # Pub quiz specific.
        if approved := discord.utils.get(ctx.guild.roles, name="Approved"):
            for member in members:
                await member.add_roles(approved)
                await asyncio.sleep(1)
        await ctx.send('Roles removed successfully')

    @purgeroles.error
    async def purgeroles_error(self, ctx, error):
        await ctx.send(error, delete_after=30.0)
        await ctx.send("Use `!help purgeroles` to get proper invocation syntax.", delete_after=30.0)

class OwnerOnly(commands.Cog, name="Server Owner Commands"):
    """Commands only guild owner can call"""
    def __init__(self, bot):
        self.bot = bot

    

    @commands.command()
    @commands.guild_only()
    async def prune(self, ctx, days:int, *roles):
        """
        Kick all members who haven't logged on in a certain nember of days, with optional roles.
        If a member has any roles that are not provided, they won't be kicked.
        The estimate provided does not take these roles into consideration.
        """
        if not ctx.author == ctx.guild.owner and not ctx.bot.is_owner(ctx.author):
            return
        if roles:
            rolelist = []
            for arg in roles:
                try:
                    role = await commands.RoleConverter().convert(ctx, arg)
                except commands.BadArgument:
                    return await ctx.send(f"Invalid role: {arg}")
                else:
                    rolelist.append(role)
            roles = rolelist
        estimate = await ctx.guild.estimate_pruned_members(days=days)
        msg = await ctx.send(f"After this operation, approximately {estimate} members will be pruned.\nReact with \U00002705 to confirm wiping question channel.\nReact with \U0000274c to cancel.")
        await msg.add_reaction('\U00002705')
        await msg.add_reaction('\U0000274c')
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ['\U00002705', '\U0000274c'] and reaction.message == msg
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("Timeout! Cancelling operation...", delete_after=20.0)
            await msg.delete()
            await ctx.message.delete()
        else:
            if str(reaction.emoji) == '\U0000274c':
                await ctx.send("Cancelling...", delete_after=20.0)
                await msg.delete()
                await ctx.message.delete()
            elif str(reaction.emoji) == '\U00002705':
                await msg.delete()
                await ctx.message.delete()
                count = await ctx.guild.prune_members(days=days, roles=roles)
                await ctx.send(f"Operation complete. {count} members were pruned.")

    @commands.command()
    @commands.guild_only()
    async def qchannel(self, ctx, channel: discord.TextChannel=None):
        if not ctx.author == ctx.guild.owner and not await ctx.bot.is_owner(ctx.author):
            return
        channel = channel or ctx.channel
        self.bot.qchannels[ctx.guild.id] = channel.id
        await ctx.send(f"{channel.mention} is marked as the questions channel and only the server owner can wipe it.")

        test = await self.bot.db.fetchrow(f"SELECT qchannel FROM servers WHERE guild_id = $1", ctx.guild.id)
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            if test:
                await self.bot.db.execute(f"UPDATE servers SET qchannel = $1 WHERE guild_id = $2", channel.id, ctx.guild.id)
            else:
                await self.bot.db.execute(f"INSERT INTO servers (guild_id, qchannel) VALUES ($1, $2)", ctx.guild.id, channel.id)
        await self.bot.db.release(connection)

    @commands.command()
    @commands.guild_only()
    async def pchannel(self, ctx, channel: discord.TextChannel=None):
        if not ctx.author == ctx.guild.owner and not await ctx.bot.is_owner(ctx.author):
            return
        channel = channel or ctx.channel
        self.bot.pchannels[ctx.guild.id] = channel.id
        await ctx.send(f"{channel.mention} is now the channel where pounces will appear.")

        test = await self.bot.db.fetchrow(f"SELECT pchannel FROM servers WHERE guild_id = $1", ctx.guild.id)
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            if test:
                await self.bot.db.execute(f"UPDATE servers SET pchannel = $1 WHERE guild_id = $2", channel.id, ctx.guild.id)
            else:
                await self.bot.db.execute("INSERT INTO servers (guild_id, pchannel) VALUES ($1, $2)", ctx.guild.id, channel.id)
        await self.bot.db.release(connection)

def setup(bot):
    bot.add_cog(OwnerOnly(bot))
    bot.add_cog(Utilities(bot))
