"""
Moderation cog for Discord bot
"""

import discord
from discord.ext import commands, tasks
import datetime
import asyncpg

# This prevents staff members from being punished
class Sinner(commands.Converter):
    async def convert(self, ctx, argument):
        argument = await commands.MemberConverter().convert(ctx, argument) # gets a member object
        permission = argument.guild_permissions.administrator # can change into any permission
        if not permission: # checks if user has the permission
            return argument # returns user object
        else:
            raise commands.BadArgument("You cannot punish other staff members") # tells user that target is a staff member

# Checks if you have a muted role
class Redeemed(commands.Converter):
    async def convert(self, ctx, argument):
        argument = await commands.MemberConverter().convert(ctx, argument) # gets member object
        muted = discord.utils.get(ctx.guild.roles, name="Muted") # gets role object
        if muted in argument.roles: # checks if user has muted role
            return argument # returns member object if there is muted role
        else:
            raise commands.BadArgument("The user was not muted.") # self-explainatory

# Checks if there is a muted role on the server and creates one if there isn't
async def mute(ctx, user, reason):
    role = discord.utils.get(ctx.guild.roles, name="Muted") # retrieves muted role returns none if there isn't
    hell = discord.utils.get(ctx.guild.text_channels, name="hell") # retrieves channel named hell returns none if there isn't
    if not role: # checks if there is muted role
        try: # creates muted role
            muted = await ctx.guild.create_role(name="Muted", reason="To use for muting")
            for channel in ctx.guild.channels: # removes permission to view and send in the channels
                await channel.set_permissions(muted, send_messages=False,
                                              read_message_history=False,
                                              read_messages=False)
        except discord.Forbidden:
            return await ctx.send("I have no permissions to make a muted role") # self-explainatory
        await user.add_roles(muted) # adds newly created muted role
        #await ctx.send(f"{user.mention} has been sent to hell for {reason}")
    else:
        await user.add_roles(role) # adds already existing muted role
        #await ctx.send(f"{user.mention} has been sent to hell for {reason}")

    #if not hell: # checks if there is a channel named hell
    #    overwrites = {ctx.guild.default_role: discord.PermissionOverwrite(read_message_history=False),
    #                  ctx.guild.me: discord.PermissionOverwrite(send_messages=True),
    #                  muted: discord.PermissionOverwrite(read_message_history=True)} # permissions for the channel
    #    try: # creates the channel and sends a message
    #        channel = await ctx.create_channel('hell', overwrites=overwrites)
    #        await channel.send("Welcome to hell.. You will spend your time here until you get unmuted. Enjoy the silence.")
    #    except discord.Forbidden:
    #        return await ctx.send("I have no permissions to make #hell")

def get_time(amount, unit):
    if unit =='d':
        return datetime.datetime.utcnow() + datetime.timedelta(days=amount)
    if unit == 's':
        return datetime.datetime.utcnow() + datetime.timedelta(seconds=amount)
    if unit == 'm':
        return datetime.datetime.utcnow() + datetime.timedelta(minutes=amount)
    if unit == 'h':
        return datetime.datetime.utcnow() + datetime.timedelta(hours=amount)

def check_mod_perms(ctx):
    """
    Checks if user has "Administrator" permissions
    """
    return ctx.author.guild_permissions.administrator


class Moderation(commands.Cog):
    """Commands used to moderate your guild. Requires administrator permissions"""

    def __init__(self, client):
        self.client = client
        self.check_mute_and_block.start()

    def cog_unload(self):
        self.check_mute_and_block.cancel()

    @commands.command(aliases=["banish"])
    @commands.check(check_mod_perms)
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, user: Sinner=None,*, reason=None):
        """Casts users out of server."""

        if not user: # checks if there is a user
            return await ctx.send("You must specify a user")

        try: # Tries to ban user
            await user.ban(reason=reason)
            await ctx.send(f"{user.mention} was cast out of the server for {reason}.")
        except discord.Forbidden:
            return await ctx.send("Are you trying to ban someone higher than the bot?")

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def softban(self, ctx, user: Sinner=None,*, reason=None):
        """Temporarily restricts access to server."""

        if not user: # checks if there is a user
            return await ctx.send("You must specify a user")

        try: # Tries to soft-ban user
            await user.ban(reason=reason)
            await user.unban(reason="Temporarily banned")
        except discord.Forbidden:
            return await ctx.send("Are you trying to soft-ban someone higher than the bot?")

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def mute(self, ctx, user: Sinner,*, reason=None):
        """Mutes a user until unmuted."""
        await mute(ctx, user, reason=(reason or "misbehaviour")) # uses the mute function
        await ctx.send(f"{user.mention} has been muted indefinitely.")

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def tempmute(self, ctx, time=None, user: Sinner=None,*, reason=None):
        """Mutes a user temporarily"""
        if not time or not user: # Missing arguments (lazy error handling)
            return await ctx.send(f"Incorrect usage of command. Use `{ctx.prefix}help tempmute` for more information", delete_after=30.0)
        if time[-1].lower() not in ['h', 'm', 's', 'd']:
            return await ctx.send("Invalid time format", delete_after=30.0)
        try:
            amount = float(time[:-1])
        except ValueError:
            return await ctx.send("Invalid time.", delete_after=30.0)
        until = get_time(float(time[:-1]), time[-1])
        async with self.client.db.acquire() as conn:
            test = await self.client.db.fetchrow("SELECT mute_until FROM mutes WHERE user_id = $1 AND guild_id = $2", user.id, ctx.guild.id)
            if not test:
                await self.client.db.execute("INSERT INTO mutes (user_id, mute_until, guild_id) VALUES ($1, $2, $3)", user.id, until, ctx.guild.id)
            else:
                await self.client.db.execute("UPDATE mutes SET mute_until = $1 WHERE user_id = $2 AND guild_id = $3", until, user.id, ctx.guild.id)
        await mute(ctx, user, reason=reason)
        await ctx.send(f"Muted {user.mention} until {until}.")

    @tasks.loop(seconds=60)
    async def check_mute_and_block(self):
        data = await self.client.db.fetch("SELECT * FROM mutes")
        for record in data:
            if datetime.datetime.utcnow() >= record['mute_until']:
                guild = self.client.get_guild(record['guild_id'])
                member = guild.get_member(record['user_id'])
                await member.remove_roles(discord.utils.get(guild.roles, name='Muted'))

        block_data = await self.client.db.fetch("SELECT * FROM blocks")
        for record in block_data:
            if datetime.datetime.utcnow() >= record['block_until']:
                guild = self.client.get_guild(record['guild_id'])
                channel = guild.get_channel(record['channel_id'])
                member = guild.get_member(record['user_id'])
                await channel.set_permissions(member, send_messages=None)

    @check_mute_and_block.before_loop
    async def before_checking_stuff(self):
        await self.client.wait_until_ready()

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def kick(self, ctx, user: Sinner=None,*, reason=None):
        """Kicks a user from the server."""
        if not user: # checks if there is a user
            return await ctx.send("You must specify a user")

        try: # tries to kick user
            await user.kick(reason=reason)
        except discord.Forbidden:
            return await ctx.send("Are you trying to kick someone higher than the bot?")

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def unmute(self, ctx, user: Redeemed):
        """Unmutes a muted user."""
        await user.remove_roles(discord.utils.get(ctx.guild.roles, name="Muted")) # removes muted role
        await ctx.send(f"{user.mention} has been unmuted")

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def block(self, ctx, user: Sinner=None):
        """
        Blocks a user from chatting in current channel.

        Similar to mute but instead of restricting access
        to all channels it restricts in current channel.
        """

        if not user: # checks if there is user
            return await ctx.send("You must specify a user")

        await ctx.channel.set_permissions(user, send_messages=False) # sets permissions for current channel
        await ctx.send(f"Blocked {user.mention} from this channel indefinitely")

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def tempblock(self, ctx, user: Sinner=None):
        if not time or not user: # Missing arguments (lazy error handling)
            return await ctx.send(f"Incorrect usage of command. Use `{ctx.prefix}help tempmute` for more information", delete_after=30.0)
        if time[-1].lower() not in ['h', 'm', 's', 'd']:
            return await ctx.send("Invalid time format", delete_after=30.0)
        try:
            amount = float(time[:-1])
        except ValueError:
            return await ctx.send("Invalid time.", delete_after=30.0)
        until = get_time(float(time[:-1]), time[-1])
        async with self.client.db.acquire() as conn:
            test = await self.client.db.fetchrow("SELECT block_until FROM blocks WHERE user_id = $1 AND guild_id = $2 AND channel_id = $3", user.id, ctx.guild.id, ctx.channel.id)
            if not test:
                await self.client.db.execute("INSERT INTO mutes (user_id, mute_until, guild_id, channel_id) VALUES ($1, $2, $3, $4)", user.id, until, ctx.guild.id, ctx.channel.id)
            else:
                await self.client.db.execute("UPDATE mutes SET mute_until = $1 WHERE user_id = $2 AND guild_id = $3 AND channel_id = $4", until, user.id, ctx.guild.id, ctx.channel.id)
        await ctx.channel.set_permissions(user, send_messages=False)
        await ctx.send(f"Blocked {user.mention} from this channel until {until}.")

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def unblock(self, ctx, user: Sinner=None):
        """Unblocks a user from current channel."""

        if not user: # checks if there is user
            return await ctx.send("You must specify a user")

        await ctx.set_permissions(user, send_messages=None) # gives back send messages permissions
        await ctx.send(f"{user.mention} has been unblocked.")

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def warn(self, ctx, user: Sinner=None,*, reason=None):
        if not user:
            return await ctx.send("You must specify a user")
        current = await self.client.db.fetchrow("SELECT num FROM warns WHERE user_id = $1 and guild_id = $2", user.id, ctx.guild.id)
        async with self.client.db.acquire() as conn:
            if not current:
                current = 1
                await self.client.db.execute("INSERT INTO warns (guild_id, user_id, num) VALUES ($1, $2, $3)", ctx.guild.id, user.id, current)
            else:
                current += 1
                await self.client.db.execute("UPDATE warns SET num = $1 WHERE guild_id = $2 and user_id = $3", current, ctx.guild.id, user.id)
                if current >=5:
                    await user.ban(reason="Autoban: 5 warns.")
                    await self.client.db.execute("DELETE FROM warns WHERE user_id = $1 and guild_id = $2", user.id, ctx.guild.id)
                    return await ctx.send(f"{user.mention} has been autobanned because they have 5 or more warns.")
        await ctx.send(f"{user.mention} has been warned. Total warns: {current}")

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def unwarn(self, ctx, user: Sinner=None):
        """Removes one warn from a user"""
        if not user:
            return await ctx.send("You must specify a user")
        current = await self.client.db.fetchrow("SELECT num FROM warns WHERE user_id = $1 and guild_id = $2", user.id, ctx.guild.id)
        async with self.client.db.acquire() as conn:
            if not current:
                return await ctx.send(f"{member.mention} has no outstanding warnings")
            else:
                current -= 1
                await self.client.db.execute("UPDATE warns SET num = $1 WHERE guild_id = $2 and user_id = $3", current, ctx.guild.id, user.id)
                if current == 0:
                    await self.client.db.execute("DELETE FROM warns WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, user.id)
        await ctx.send(f"{user.mention} has been pardoned for one warning. Total warns: {current}")

    @commands.command(aliases=['cleanslate'])
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def clearwarns(self, ctx, user: discord.Member=None):
        """Resets warns for the user"""
        if not user:
            return await ctx.send("You must specify a member")
        current = await self.client.db.fetchrow("SELECT num FROM warns WHERE user_id = $1 and guild_id = $2", user.id, ctx.guild.id)
        if not current:
            return await ctx.send(f"{member.mention} has no outstanding warnings")
        async with self.client.db.acquire() as conn:
            await self.client.db.execute("DELETE FROM warns WHERE user_id = $1 and guild_id = $2", user.id, ctx.guild.id)
        await ctx.send(f"Cleared all warns for {user.mention}")


def setup(client):
    client.add_cog(Moderation(client))
