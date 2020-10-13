"""
Moderation cog for Discord bot
"""
from typing import Optional
import re
import sys
import traceback
import discord
from discord.ext import commands, tasks
import datetime
import asyncpg
from datetime import timezone

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
    channel = ctx.bot.get_channel(ctx.bot.modlogs.get(ctx.guild.id))
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
    else:
        await user.add_roles(role) # adds already existing muted role

    #if not hell: # checks if there is a channel named hell
    #    overwrites = {ctx.guild.default_role: discord.PermissionOverwrite(read_message_history=False),
    #                  ctx.guild.me: discord.PermissionOverwrite(send_messages=True),
    #                  muted: discord.PermissionOverwrite(read_message_history=True)} # permissions for the channel
    #    try: # creates the channel and sends a message
    #        channel = await ctx.create_channel('hell', overwrites=overwrites)
    #        await channel.send("Welcome to hell.. You will spend your time here until you get unmuted. Enjoy the silence.")
    #    except discord.Forbidden:
    #        return await ctx.send("I have no permissions to make #hell")

class TimeConverter(commands.Converter):
    time_regex = re.compile("(?:(\d{1,5})(h|s|m|d))+?")
    time_dict = {"h":3600, "s":1, "m":60, "d":86400}

    async def convert(self, ctx, argument):
        args = argument.lower()
        matches = re.findall(self.time_regex, args)
        seconds = 0
        for v, k in matches:
            try:
                seconds += self.time_dict[k] * float(v)
            except KeyError:
                raise commands.BadArgument(f"{k} is an invalid time-key! h/s/m/d are valid.")
            except ValueError:
                raise commands.BadArgument(f"{v} is not a number!")

        return datetime.timedelta(seconds=seconds)

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

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            pass
        if isinstance(error, commands.BadArgument) or isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(error)
        else:
            error = getattr(error, 'original', error)
            print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.check(check_mod_perms)
    async def modlog(self, ctx):
        """Used to assign a channel where moderation events are logged"""
        if self.client.modlogs.get(ctx.guild.id):
            await ctx.send(f"Mod logs for this server are sent to {self.client.get_channel(self.client.modlogs[ctx.guild.id]).mention}")
        else:
            await ctx.send(f"No channel has been configured for mod logs on this server. Use `{ctx.prefix}modlog assign` to assign one.")

    @modlog.command()
    @commands.guild_only()
    @commands.check(check_mod_perms)
    async def assign(self, ctx, channel:discord.TextChannel=None):
        """Assigns a specific channel to receive moderation event logs"""
        if not channel:
            channel = ctx.channel
        self.client.modlogs[ctx.guild.id] = channel.id
        async with self.client.db.acquire() as conn:
            if await self.client.db.fetchval("SELECT modlog FROM servers WHERE guild_id = $1", ctx.guild.id):
                await self.client.db.execute("UPDATE servers SET modlog = $1 WHERE guild_id = $2", channel.id, ctx.guild.id)
            else:
                await self.client.db.execute("INSERT INTO servers (modlog) VALUES ($1) WHERE guild_id = $2", channel.id, ctx.guild.id)

        await ctx.send(f"{channel.mention} has been configured for mod logs on this server")

    @commands.command(aliases=["banish"])
    @commands.check(check_mod_perms)
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, user: Sinner,*, reason=None):
        """Casts users out of server."""
        channel = self.client.get_channel(self.client.modlogs.get(ctx.guild.id))

        try: # Tries to ban user
            await user.ban(reason=reason)
        except discord.Forbidden:
            return await ctx.send("Are you trying to ban someone higher than the bot?")
        if channel:
            embed = discord.Embed(title="BAN", colour=0xFF0000, timestamp=datetime.datetime.utcnow())
            embed.add_field(name='User', value=f"{user} ({user.id}) ({user.mention})", inline=False)
            embed.add_field(name='Reason', value=f"{reason if reason else 'None specified'}", inline=False)
            embed.add_field(name='Responsible Moderator', value=str(ctx.author), inline=False)
            await channel.send(embed=embed)

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def softban(self, ctx, user: Sinner,*, reason:str=None):
        """Temporarily restricts access to server."""
        channel = self.client.get_channel(self.client.modlogs.get(ctx.guild.id))
        try: # Tries to soft-ban user
            await user.ban(reason=reason)
            await user.unban(reason="Temporarily banned")
        except discord.Forbidden:
            return await ctx.send("Are you trying to soft-ban someone higher than the bot?")
        if channel:
            embed = discord.Embed(title="SOFTBAN", colour=discord.Colour.red(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name='User', value=f"{user} ({user.id}) ({user.mention})", inline=False)
            embed.add_field(name='Reason', value=f"{reason if reason else'None specified.'}", inline=False)
            embed.add_field(name='Responsible Moderator', value=str(ctx.author), inline=False)
            await channel.send(embed=embed)

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def mute(self, ctx, time:Optional[TimeConverter], user: Sinner,*, reason:str=None):
        """Mutes a user until unmuted."""
        time = time or 0
        await mute(ctx, user, reason=reason) # uses the mute function
        if time != 0:
            until = datetime.datetime.now(timezone.utc) + time
            async with self.client.db.acquire() as conn:
                test = await self.client.db.fetchrow("SELECT mute_until FROM mutes WHERE user_id = $1 AND guild_id = $2", user.id, ctx.guild.id)
                if not test:
                    await self.client.db.execute("INSERT INTO mutes (user_id, mute_until, guild_id) VALUES ($1, $2, $3)", user.id, until, ctx.guild.id)
                else:
                    await self.client.db.execute("UPDATE mutes SET mute_until = $1 WHERE user_id = $2 AND guild_id = $3", until, user.id, ctx.guild.id)
            await ctx.send(f"Muted {user.mention} for {str(time)} (until {str(until).split('.')[0][:-3]} UTC).")
        else:
            await ctx.send(f"Muted {user.mention} indefinitely.")

        channel = self.client.get_channel(self.client.modlogs.get(ctx.guild.id))
        if channel:
            embed = discord.Embed(title="MUTE", colour=discord.Colour.orange(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name='User', value=f"{user} ({user.id}) ({user.mention})", inline=False)
            embed.add_field(name='Duration', value=str(time) if time else '∞', inline=False)
            embed.add_field(name='Reason', value=f"{reason if reason else'None specified.'}", inline=False)
            embed.add_field(name='Responsible Moderator', value=str(ctx.author), inline=False)
            await channel.send(embed=embed)

    @tasks.loop(seconds=1)
    async def check_mute_and_block(self):
        data = await self.client.db.fetch("SELECT * FROM mutes")
        for record in data:
            if datetime.datetime.now(timezone.utc) >= record['mute_until']:
                guild = self.client.get_guild(record['guild_id'])
                member = guild.get_member(record['user_id'])
                await member.remove_roles(discord.utils.get(guild.roles, name='Muted'))
                async with self.client.db.acquire() as conn:
                    await self.client.db.execute("DELETE FROM mutes WHERE guild_id = $1 AND user_id = $2", guild.id, member.id)

        block_data = await self.client.db.fetch("SELECT * FROM blocks")
        for record in block_data:
            if datetime.datetime.now(timezone.utc) >= record['block_until']:
                guild = self.client.get_guild(record['guild_id'])
                channel = guild.get_channel(record['channel_id'])
                member = guild.get_member(record['user_id'])
                await channel.set_permissions(member, send_messages=None)
                async with self.client.db.acquire() as conn:
                    await self.client.db.execute("DELETE FROM blocks WHERE guild_id = $1 AND user_id = $2 AND channel_id = $3", guild.id, member.id, channel.id)

    @check_mute_and_block.before_loop
    async def before_checking_stuff(self):
        await self.client.wait_until_ready()

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def kick(self, ctx, user: Sinner,*, reason=None):
        """Kicks a user from the server."""

        try: # tries to kick user
            await user.kick(reason=reason)
        except discord.Forbidden:
            return await ctx.send("Are you trying to kick someone higher than the bot?")
        channel = self.client.get_channel(self.client.modlogs.get(ctx.guild.id))
        if channel:
            embed = discord.Embed(title="KICK", colour=discord.Colour.dark_orange(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name='User', value=f"{user} ({user.id}) ({user.mention})", inline=False)
            embed.add_field(name='Reason', value=f"{reason if reason else'None specified.'}", inline=False)
            embed.add_field(name='Responsible Moderator', value=str(ctx.author), inline=False)
            await channel.send(embed=embed)

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def unmute(self, ctx, user: Redeemed):
        """Unmutes a muted user."""
        await user.remove_roles(discord.utils.get(ctx.guild.roles, name="Muted")) # removes muted role
        await ctx.send(f"{user.mention} has been unmuted.")
        channel = self.client.get_channel(self.client.modlogs.get(ctx.guild.id))
        if channel:
            embed = discord.Embed(title="UNMUTE", colour=discord.Colour.green(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name='User', value=f"{user} ({user.id}) ({user.mention})", inline=False)
            embed.add_field(name='Responsible Moderator', value=str(ctx.author), inline=False)
            await channel.send(embed=embed)

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def block(self, ctx, time: Optional[TimeConverter], user: Sinner, *, reason=None):
        """
        Blocks a user from chatting in current channel.

        Similar to mute but instead of restricting access
        to all channels it restricts in current channel.
        """
        time = time or 0
        await ctx.channel.set_permissions(user, send_messages=False) # sets permissions for current channel
        if time != 0:
            until = datetime.datetime.now(timezone.utc) + time
            async with self.client.db.acquire() as conn:
                test = await self.client.db.fetchrow("SELECT block_until FROM blocks WHERE user_id = $1 AND guild_id = $2 AND channel_id = $3", user.id, ctx.guild.id, ctx.channel.id)
                if not test:
                    await self.client.db.execute("INSERT INTO blocks (user_id, mute_until, guild_id, channel_id) VALUES ($1, $2, $3, $4)", user.id, until, ctx.guild.id, ctx.channel.id)
                else:
                    await self.client.db.execute("UPDATE blocks SET block_until = $1 WHERE user_id = $2 AND guild_id = $3 AND channel_id = $4", until, user.id, ctx.guild.id, ctx.channel.id)
            await ctx.send(f"Blocked {user.mention} from this channel for {time} (until {str(until).split('.')[0][:-3]}).")
        else:
            await ctx.send(f"Blocked {user.mention} from this channel indefinitely")
        channel = self.client.get_channel(self.client.modlogs.get(ctx.guild.id))
        if channel:
            embed = discord.Embed(title="BLOCK", colour=discord.Colour.orange(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name='User', value=f"{user} ({user.id}) ({user.mention})", inline=False)
            embed.add_field(name='Channel', value=ctx.channel.mention, inline=False)
            embed.add_field(name='Duration', value=str(time) if time else '∞', inline=False)
            embed.add_field(name='Reason', value=f"{reason if reason else'None specified.'}", inline=False)
            embed.add_field(name='Responsible Moderator', value=str(ctx.author), inline=False)
            await channel.send(embed=embed)

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def unblock(self, ctx, user: Sinner=None):
        """Unblocks a user from current channel."""

        if not user: # checks if there is user
            return await ctx.send("You must specify a user")

        await ctx.set_permissions(user, send_messages=None) # gives back send messages permissions
        await ctx.send(f"{user.mention} has been unblocked.")
        channel = self.client.get_channel(self.client.modlogs.get(ctx.guild.id))
        if channel:
            embed = discord.Embed(title="UNBLOCK", colour=discord.Colour.green(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name='User', value=f"{user} ({user.id}) ({user.mention})", inline=False)
            embed.add_field(name='Channel', value=ctx.channel.mention, inline=False)
            embed.add_field(name='Reason', value=f"{reason if reason else'None specified.'}", inline=False)
            embed.add_field(name='Responsible Moderator', value=str(ctx.author), inline=False)
            await channel.send(embed=embed)

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def warn(self, ctx, user: Sinner=None,*, reason=None):
        """Issues a warning to a user. Current status can be accessed by warnstats"""
        if not user:
            return await ctx.send("You must specify a user")
        current = await self.client.db.fetchval("SELECT num FROM warns WHERE user_id = $1 and guild_id = $2", user.id, ctx.guild.id)
        async with self.client.db.acquire() as conn:
            if not current:
                current = 1
                await self.client.db.execute("INSERT INTO warns (guild_id, user_id, num) VALUES ($1, $2, $3)", ctx.guild.id, user.id, current)
            else:
                current += 1
                await self.client.db.execute("UPDATE warns SET num = $1 WHERE guild_id = $2 and user_id = $3", current, ctx.guild.id, user.id)
                if current >=5:
                    await user.ban(reason="Autoban: 5 warns.")
                    channel = self.client.get_channel(self.client.modlogs.get(ctx.guild.id))
                    if channel:
                        warn_embed = discord.Embed(title="WARN", colour=discord.Colour.dark_orange(), timestamp=datetime.datetime.utcnow())
                        warn_embed.add_field(name='User', value=f"{user} ({user.id}) ({user.mention})", inline=False)
                        warn_embed.add_field(name='Reason', value=f"{reason if reason else'None specified.'}", inline=False)
                        warn_embed.add_field(name='Responsible Moderator', value=str(ctx.author), inline=False)
                        await channel.send(embed=warn_embed)
                        embed = discord.Embed(title="AUTOBAN", colour=discord.Colour.red(), timestamp=datetime.datetime.utcnow())
                        embed.add_field(name='User', value=f"{user} ({user.id}) ({user.mention})", inline=False)
                        embed.add_field(name='Reason', value="Accumulated 5 warns", inline=False)
                        embed.add_field(name='Responsible Moderator', value=str(ctx.guild.me), inline=False)
                        await channel.send(embed=embed)
                    await self.client.db.execute("DELETE FROM warns WHERE user_id = $1 and guild_id = $2", user.id, ctx.guild.id)
                    return await ctx.send(f"{user.mention} has been autobanned because they have 5 or more warns.")
        await ctx.send(f"{user.mention} has been warned. Total warns: {current}")
        channel = self.client.get_channel(self.client.modlogs.get(ctx.guild.id))
        if channel:
            embed = discord.Embed(title="WARN", colour=discord.Colour.dark_orange(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name='User', value=f"{user} ({user.id}) ({user.mention})", inline=False)
            embed.add_field(name='Reason', value=f"{reason if reason else'None specified.'}", inline=False)
            embed.add_field(name='Current warns', value=current, inline=False)
            embed.add_field(name='Responsible Moderator', value=str(ctx.author), inline=False)
            await channel.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    async def warnstats(self, ctx, user: discord.Member=None):
        """To check how many warns you have. If you are an admin, you can specify a user."""
        if not ctx.author.guild_permissions.administrator or not user:
            user = ctx.author
        current = await self.client.db.fetchval("SELECT num FROM warns WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, user.id)
        if current is None:
            current = 0
        await ctx.send(f"Currently, {user.mention} has {current} {'warn' if current == 1 else 'warns'}.")

    @commands.command()
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def unwarn(self, ctx, user: Sinner=None):
        """Removes one warn from a user"""
        if not user:
            return await ctx.send("You must specify a user")
        current = await self.client.db.fetchval("SELECT num FROM warns WHERE user_id = $1 and guild_id = $2", user.id, ctx.guild.id)
        async with self.client.db.acquire() as conn:
            if not current:
                return await ctx.send(f"{member.mention} has no outstanding warnings")
            else:
                current -= 1
                await self.client.db.execute("UPDATE warns SET num = $1 WHERE guild_id = $2 and user_id = $3", current, ctx.guild.id, user.id)
                if current == 0:
                    await self.client.db.execute("DELETE FROM warns WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, user.id)
        await ctx.send(f"{user.mention} has been pardoned for one warning. Total warns: {current}")
        channel = self.client.get_channel(self.client.modlogs.get(ctx.guild.id))
        if channel:
            embed = discord.Embed(title="UNWARN", colour=discord.Colour.green(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name='User', value=f"{user} ({user.id}) ({user.mention})", inline=False)
            embed.add_field(name='Current warns', value=current, inline=False)
            embed.add_field(name='Responsible Moderator', value=str(ctx.author), inline=False)
            await channel.send(embed=embed)

    @commands.command(aliases=['cleanslate'])
    @commands.check(check_mod_perms)
    @commands.guild_only()
    async def clearwarns(self, ctx, user: discord.Member=None):
        """Resets warns for the user"""
        if not user:
            return await ctx.send("You must specify a member")
        current = await self.client.db.fetchrow("SELECT num FROM warns WHERE user_id = $1 and guild_id = $2", user.id, ctx.guild.id)
        if not current:
            return await ctx.send(f"{user.mention} has no outstanding warnings")
        async with self.client.db.acquire() as conn:
            await self.client.db.execute("DELETE FROM warns WHERE user_id = $1 and guild_id = $2", user.id, ctx.guild.id)
        await ctx.send(f"Cleared all warns for {user.mention}")
        channel = self.client.get_channel(self.client.modlogs.get(ctx.guild.id))
        if channel:
            embed = discord.Embed(title="CLEAR WARNS", colour=discord.Colour.green(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name='User', value=f"{user} ({user.id}) ({user.mention})", inline=False)
            embed.add_field(name='Responsible Moderator', value=str(ctx.author), inline=False)
            await channel.send(embed=embed)


def setup(client):
    client.add_cog(Moderation(client))
