"""
Utitlities cog for Discord bot
"""
import json
import asyncpg
import asyncio
import re
import discord
from discord.ext import commands, tasks

def check_util_perms(ctx):
    """
    Checks if user has "Manage server" permissions
    """
    if ctx.guild is None:
        return True
    return ctx.author.guild_permissions.manage_guild

def q_channel_protection(ctx):
    """
    Prevents question channel from being wiped by anyone other than owner
    """
    if ctx.guild is None:
        return True
    if str(ctx.guild.id) not in ctx.bot.qchannels.keys():
        return True
    if ctx.channel.id == ctx.bot.qchannels[ctx.guild.id] and ctx.author == ctx.guild.owner:
        return True
    if ctx.channel.id != ctx.bot.qchannels[ctx.guild.id]:
        return True
    return False

class Utilities(commands.Cog):
    """Utilities for your server. Require manage server permissions to use"""
    def __init__(self, client):
        self.client = client
        self.guild_state= {}

    @commands.command()
    @commands.guild_only()
    @commands.check(check_util_perms)
    @commands.check(q_channel_protection)
    async def wipe(self, ctx, limit):
        """
        Wipes a number of messages from current channel.
        (Upto 200 messages in the past 14 days.)
        """
        if limit == "all":
            limit = None
        else:
            try:
                limit = int(limit) + 1
            except ValueError:
                await ctx.send("Please enter a valid number of messages to wipe (Add 2 to your originally intended number). Enter `all` to wipe the entire channel. (Upto 100 messages in the past 14 days.)")
                return
        if ctx.guild:
            if ctx.channel == self.client.get_channel(self.client.qchannels.get(ctx.guild.id)):
                msg = await ctx.send(f"Enter `{ctx.prefix}confirm` to confirm wiping question channel.\nEnter `{ctx.prefix}cancel` to cancel.")
                self.guild_state[ctx.guild.id] = ("confirm", limit, msg)
                return
        await ctx.channel.purge(limit=limit)

    @commands.command(hidden=True)
    @commands.guild_only()
    @commands.check(check_util_perms)
    @commands.check(q_channel_protection)
    async def confirm(self, ctx):
        if ctx.guild.id not in self.guild_state.keys():
            return
        if self.guild_state[ctx.guild.id][0] == "confirm":
            if ctx.author != ctx.guild.owner:
                return
            await ctx.message.delete()
            await self.guild_state[ctx.guild.id][2].delete()
            await ctx.channel.purge(limit=self.guild_state[ctx.guild.id][1])
        elif self.guild_state[ctx.guild.id][0] == "purge":
            if ctx.author != ctx.guild.owner:
                return
            for member in ctx.guild.members:
                if member.id == ctx.guild.owner_id or member.bot:
                    continue
                try:
                    await member.kick(reason=f"by {ctx.author} during server purge")
                except discord.Forbidden:
                    await ctx.send(embed=discord.Embed(description=f"Could not kick {member.mention}. This is probably because of hierarchy", colour=0xFF0000))
                else:
                    await member.send(f"You have been kicked from `{ctx.guild.name}` because the server was purged entirely.")
            await ctx.guild.system_channel.send(f"Server purged by {ctx.author.mention}.")
        self.guild_state.pop(ctx.guild.id)

    @commands.command(hidden=True)
    @commands.guild_only()
    @commands.check(check_util_perms)
    @commands.check(q_channel_protection)
    async def cancel(self, ctx):
        if ctx.guild.id not in self.guild_state.keys():
            return
        if self.guild_state[ctx.guild.id][0] == "confirm":
            if ctx.author != ctx.guild.owner:
                return
            await ctx.message.delete()
            await self.guild_state[ctx.guild.id][2].delete()
        elif self.guild_state[ctx.guild.id][0] == "purge":
            if ctx.author != ctx.guild.owner:
                return
            await ctx.message.delete()
            await self.guild_state[ctx.guild.id][1].delete()
        self.guild_state.pop(ctx.guild.id)


    @wipe.error
    async def wipe_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.message.delete()
            await ctx.send("Please enter a number of messages to wipe (Accomodate this message into your count). Enter `all` to wipe the entire channel. (Upto 100 messages in the past 14 days.)")


    @commands.command()
    @commands.guild_only()
    @commands.check(check_util_perms)
    async def prefix(self, ctx, pfx=None):
        """
        Change the prefix of the bot in this server, or return the current prefix if none specified.
        """
        #with open('readonly/prefixes.json', 'r') as file:
        #    prefixes = json.load(file)
        if pfx is None:
            await ctx.send(f"My prefix in this server is `{self.client.prefixes.get(ctx.guild.id, '!')}`")
            return
        self.client.prefixes[ctx.guild.id] = pfx
        await ctx.send(f"My prefix in this server is now `{pfx}`")
        test = await self.client.db.fetchrow(f"SELECT prefix FROM servers WHERE guild_id = {ctx.guild.id}")
        connection = await self.client.db.acquire()
        async with connection.transaction():
            if test:
                await self.client.db.execute("UPDATE servers SET prefix = $1 WHERE guild_id = $2", pfx, ctx.guild.id)
            else:
                await self.client.db.execute(f"""INSERT INTO servers (guild_id, prefix) VALUES ($1, $2)""", ctx.guild.id, pfx)
        await self.client.db.release(connection)

        #prefixes[str(ctx.guild.id)] = pfx

        #with open('readonly/prefixes.json', 'w') as file:
        #    json.dump(prefixes, file, indent=4)



    @commands.command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def purgeroles(self, ctx, *, args):
        """Clears all roles of a particular member, or all members of a particular role.


            Syntax: purgeroles @member1 @member2
                    # or
                    purgeroles @member1 @member2 @role
                    # or
                    purgeroles @role"""
        members = []
        role = None
        for arg in args.split():
            if len(id := re.findall('<@!?([0-9]+)>', arg)) == 1:
                members.append(ctx.guild.get_member(int(id[0])))
            elif len(id := re.findall('<@&([0-9]+)>', arg)) == 1:
                role = ctx.guild.get_role(int(id[0]))
                break

        if role:
            if len(members) == 0:
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

        await ctx.send('Roles removed successfully')

    @purgeroles.error
    async def purgeroles_error(self, ctx, error):
        await ctx.send(error, delete_after=30.0)
        await ctx.send("Use `!help purgeroles` to get proper invocation syntax.", delete_after=30.0)







class OwnerOnly(commands.Cog, name="Server Owner Commands"):
    """Commands only guild owner can call"""
    def __init__(self, client):
        self.client = client

    @commands.command(hidden=True)
    @commands.guild_only()
    async def approve(self, ctx, member:discord.Member):
        """Grants role Approved to the user"""
        if ctx.author == ctx.guild.owner:
            if not discord.utils.get(ctx.guild.roles, name="Approved"):
                await ctx.send("Create role named 'Approved' and try again.")
                return
            try:
                await member.add_roles(discord.utils.get(ctx.guild.roles, name="Approved"))
            except discord.Forbidden:
                await ctx.send(f"I do not have permissions to approve members in `{reaction.message.guild.name}`. Make sure I have a role higher up than `Approved`")
                return
            await ctx.message.delete()
            await ctx.guild.system_channel.send(f"{member.mention} has been approved.")

    @commands.command(hidden=True)
    @commands.guild_only()
    async def purge(self, ctx):
        """Kicks everyone except bots and owner. Only owner can call this"""
        if ctx.author == ctx.guild.owner:
            msg = await ctx.send(f"Type `{ctx.prefix}confirm` to confirm purging the server.\nEnter `{ctx.prefix}cancel` to cancel.")
            self.guild_state[ctx.guild.id] = ("purge", msg)

    @commands.command(hidden=True)
    @commands.guild_only()
    async def qchannel(self, ctx):
        if not ctx.author == ctx.guild.owner:
            return
        channel = ctx.channel
        self.client.qchannels[ctx.guild.id] = channel.id
        await ctx.send(f"{channel.mention} is marked as the questions channel and only the owner can wipe it.")

        test = await self.client.db.fetchrow(f"SELECT qchannel FROM servers WHERE guild_id = {ctx.guild.id}")
        connection = await self.client.db.acquire()
        async with connection.transaction():
            if test:
                await self.client.db.execute(f"UPDATE servers SET qchannel = {channel.id} WHERE guild_id = {ctx.guild.id}")
            else:
                await self.client.db.execute(f"""INSERT INTO servers (guild_id, qchannel) VALUES ({ctx.guild.id}, {channel.id})""")
        await self.client.db.release(connection)


    @commands.command(hidden=True)
    @commands.guild_only()
    async def pchannel(self, ctx):
        if not ctx.author == ctx.guild.owner:
            return
        channel = ctx.channel
        self.client.pchannels[ctx.guild.id] = channel.id
        await ctx.send(f"{channel.mention} is now the channel where pounces will appear.")

        test = await self.client.db.fetchrow(f"SELECT pchannel FROM servers WHERE guild_id = {ctx.guild.id}")
        connection = await self.client.db.acquire()
        async with connection.transaction():
            if test:
                await self.client.db.execute(f"UPDATE servers SET pchannel = {channel.id} WHERE guild_id = {ctx.guild.id}")
            else:
                await self.client.db.execute(f"""INSERT INTO servers (guild_id, pchannel) VALUES ({ctx.guild.id}, {channel.id})""")
        await self.client.db.release(connection)





def setup(client):
    client.add_cog(OwnerOnly(client))
    client.add_cog(Utilities(client))
