import discord
from discord.ext import commands
import inspect
import itertools
import pkg_resources
import time as pytime
import unicodedata
from typing import Union
from .utils import formats, time
import os, datetime
from collections import Counter
import asyncio
from functools import partial
import codecs
import pathlib
import random
from .utils.help import PaginatedHelpCommand
from .utils import checks
import psutil
import pygit2

try:
    from assets.hello import Greeter
except ImportError:
    Greeter = None


class Prefix(commands.Converter):
    async def convert(self, ctx, argument):
        user_id = ctx.bot.user.id
        if argument.startswith((f'<@{user_id}>', f'<@!{user_id}>')):
            raise commands.BadArgument('That is a reserved prefix already in use.')
        return argument


class Meta(commands.Cog):
    """Commands for utilities related to Discord or the Bot itself."""

    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = self.bot.help_command
        bot.help_command = PaginatedHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)

    @commands.command()
    async def charinfo(self, ctx, *, characters: str):
        """Shows you information about a number of characters.
        Only up to 25 characters at a time.
        """

        def to_string(c):
            digit = f'{ord(c):x}'
            name = unicodedata.name(c, 'Name not found.')
            return f'`\\U{digit:>08}`: {name} - {c} \N{EM DASH} <http://www.fileformat.info/info/unicode/char/{digit}>'

        msg = '\n'.join(map(to_string, characters))
        if len(msg) > 2000:
            return await ctx.send('Output too long to display.')
        await ctx.send(msg)

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

    @commands.command(aliases=['size'])
    async def cloc(self, ctx, *, extras=None):
        """Get the line and file count of the source.

        Use the flag `--include-submodules` to count git submodules and site packages.
        """
        if extras and extras.lower().strip() not in ('--include-submodules',):
            return await ctx.send('Invalid flag/subcommand.')
        async with ctx.typing():
            func = partial(self.do_cloc, extras)
            msg = await self.bot.loop.run_in_executor(None, func)
            await ctx.send(f'{msg}\nYou can check out the core source using `{ctx.prefix}source`.')

    def do_cloc(self, extras=None):
        total = 0
        file_amount = 0
        for path, subdirs, files in os.walk('.'):
            if extras is None:
                if path.startswith('./venv/'):
                    continue
            for name in files:
                if name.endswith('.py'):
                    file_amount += 1
                    with codecs.open('./' + str(pathlib.PurePath(path, name)), 'r', 'utf-8') as f:
                        for i, l in enumerate(f):
                            if l.strip().startswith('#') or len(l.strip()) is 0:  # skip commented lines.
                                pass
                            else:
                                total += 1
        msg = f'I am made of {total:,} lines of Python, spread across {file_amount:,} files!'
        if extras and extras.lower().strip() in ('--include-submodules',):
            msg += ' (including all subpackages)'
        return msg

    @commands.command()
    #@commands.is_owner()  # now OSS, not needed
    async def source(self, ctx, *, command: str = None):
        """Displays my full source code or for a specific command on GitHub.
        To display the source code of a subcommand you can separate it by
        periods, e.g. modlog.assign for the assign subcommand of the modlog group,
        or by spaces.
        """
        source_url = 'https://github.com/darthshittious/Robo-VJ'
        branch = 'main'
        if command is None:
            return await ctx.send(source_url)

        if command == 'help':
            src = type(self.bot.help_command)
            module = src.__module__
            filename = inspect.getsourcefile(src)
        else:
            obj = self.bot.get_command(command.replace('.', ' '))
            if obj is None:
                return await ctx.send('Could not find command.')

            # since we found the command we're looking for, presumably anyway, let's
            # try to access the code itself
            src = obj.callback.__code__
            module = obj.callback.__module__
            filename = src.co_filename

        lines, firstlineno = inspect.getsourcelines(src)
        if module.startswith('jishaku'):
            # in the utils cog
            location = module.replace('.', '/') + '.py'
            source_url = 'https://github.com/darthshittious/jishaku'
            branch = 'master'
        elif not module.startswith('discord'):
            # not a built-in command
            location = os.path.relpath(filename).replace('\\', '/')
        else:
            location = module.replace('.', '/') + '.py'
            source_url = 'https://github.com/Rapptz/discord.py'
            branch = 'master'

        final_url = f'<{source_url}/blob/{branch}/{location}#L{firstlineno}-L{firstlineno + len(lines) - 1}>'
        await ctx.send(final_url)

    @commands.command()
    async def avatar(self, ctx, *, user: Union[discord.Member, discord.User] = None):
        """Shows a user's enlarged avatar (if possible)."""
        embed = discord.Embed()
        user = user or ctx.author
        avatar = user.avatar_url_as(static_format='png')
        embed.set_author(name=str(user), url=avatar)
        embed.set_image(url=avatar)
        await ctx.send(embed=embed)

    @commands.command()
    async def info(self, ctx, *, user: Union[discord.Member, discord.User] = None):
        """Shows info about a user."""

        user = user or ctx.author
        e = discord.Embed()
        roles = [role.name.replace('@', '@\u200b') for role in getattr(user, 'roles', [])]
        # shared = sum(g.get_member(user.id) is not None for g in self.bot.guilds)
        e.set_author(name=str(user))

        def format_date(dt):
            if dt is None:
                return 'N/A'
            return f'{dt:%Y-%m-%d %H:%M} ({time.human_timedelta(dt, accuracy=3)})'

        e.add_field(name='ID', value=user.id, inline=False)
        # e.add_field(name='Servers', value=f'{shared} shared', inline=False)
        e.add_field(name='Joined', value=format_date(getattr(user, 'joined_at', None)), inline=False)
        e.add_field(name='Created', value=format_date(user.created_at), inline=False)

        voice = getattr(user, 'voice', None)
        if voice is not None:
            vc = voice.channel
            other_people = len(vc.members) - 1
            voice = f'{vc.name} with {other_people} others' if other_people else f'{vc.name} by themselves'
            e.add_field(name='Voice', value=voice, inline=False)

        if roles:
            e.add_field(name='Roles', value=', '.join(roles) if len(roles) < 10 else f'{len(roles)} roles',
                        inline=False)

        colour = user.colour
        if colour.value:
            e.colour = colour

        if user.avatar:
            e.set_thumbnail(url=user.avatar_url)

        if isinstance(user, discord.User):
            e.set_footer(text='This member is not in this server.')

        await ctx.send(embed=e)

    @commands.command(aliases=['guildinfo'], usage='')
    @commands.guild_only()
    async def serverinfo(self, ctx, *, guild_id: int = None):
        """Shows info about the current server."""

        if guild_id is not None and await self.bot.is_owner(ctx.author):
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                return await ctx.send(f'Invalid Guild ID given.')
        else:
            guild = ctx.guild

        roles = [role.name.replace('@', '@\u200b') for role in guild.roles]

        # figure out what channels are 'secret'
        everyone = guild.default_role
        everyone_perms = everyone.permissions.value
        secret = Counter()
        totals = Counter()
        for channel in guild.channels:
            allow, deny = channel.overwrites_for(everyone).pair()
            perms = discord.Permissions((everyone_perms & ~deny.value) | allow.value)
            channel_type = type(channel)
            totals[channel_type] += 1
            if not perms.read_messages:
                secret[channel_type] += 1
            elif isinstance(channel, discord.VoiceChannel) and (not perms.connect or not perms.speak):
                secret[channel_type] += 1

        member_by_status = Counter(str(m.status) for m in guild.members)

        e = discord.Embed()
        e.title = guild.name
        e.description = f'**ID**: {guild.id}\n**Owner**: {guild.owner}'
        if guild.icon:
            e.set_thumbnail(url=guild.icon_url)

        channel_info = []
        key_to_emoji = {
            discord.TextChannel: '<:text_channel:766623209487335441>',
            discord.VoiceChannel: '<:voice_channel:766623209092153378>',
        }
        for key, total in totals.items():
            secrets = secret[key]
            try:
                emoji = key_to_emoji[key]
            except KeyError:
                continue

            if secrets:
                channel_info.append(f'{emoji} {total} ({secrets} locked)')
            else:
                channel_info.append(f'{emoji} {total}')

        info = []
        features = set(guild.features)
        all_features = {
            'PARTNERED': 'Partnered',
            'VERIFIED': 'Verified',
            'DISCOVERABLE': 'Server Discovery',
            'COMMUNITY': 'Community Server',
            'FEATURABLE': 'Featured',
            'WELCOME_SCREEN_ENABLED': 'Welcome Screen',
            'INVITE_SPLASH': 'Invite Splash',
            'VIP_REGIONS': 'VIP Voice Servers',
            'VANITY_URL': 'Vanity Invite',
            'COMMERCE': 'Commerce',
            'LURKABLE': 'Lurkable',
            'NEWS': 'News Channels',
            'ANIMATED_ICON': 'Animated Icon',
            'BANNER': 'Banner'
        }

        for feature, label in all_features.items():
            if feature in features:
                info.append(f'{ctx.tick(True)}: {label}')

        if info:
            e.add_field(name='Features', value='\n'.join(info))

        e.add_field(name='Channels', value='\n'.join(channel_info))

        if guild.premium_tier != 0:
            boosts = f'Level {guild.premium_tier}\n{guild.premium_subscription_count} boosts'
            last_boost = max(guild.members, key=lambda m: m.premium_since or guild.created_at)
            if last_boost.premium_since is not None:
                boosts = f'{boosts}\nLast Boost: {last_boost} ({time.human_timedelta(last_boost.premium_since, accuracy=2)})'
            e.add_field(name='Boosts', value=boosts, inline=False)

        bots = sum(m.bot for m in guild.members)
        fmt = f'<:online:766623209687613466> {member_by_status["online"]} ' \
              f'<:idle:766623209931407361> {member_by_status["idle"]} ' \
              f'<:dnd:766623209721692161> {member_by_status["dnd"]} ' \
              f'<:offline:766623210379673652>  {member_by_status["offline"]}\n' \
              f'Total: {guild.member_count} ({formats.plural(bots):bot})'

        e.add_field(name='Members', value=fmt, inline=False)
        e.add_field(name='Roles', value=', '.join(roles) if len(roles) < 10 else f'{len(roles)} roles')

        emoji_stats = Counter()
        for emoji in guild.emojis:
            if emoji.animated:
                emoji_stats['animated'] += 1
                emoji_stats['animated_disabled'] += not emoji.available
            else:
                emoji_stats['regular'] += 1
                emoji_stats['disabled'] += not emoji.available

        fmt = f'Regular: {emoji_stats["regular"]}/{guild.emoji_limit}\n' \
              f'Animated: {emoji_stats["animated"]}/{guild.emoji_limit}\n' \

        if emoji_stats['disabled'] or emoji_stats['animated_disabled']:
            fmt = f'{fmt}Disabled: {emoji_stats["disabled"]} regular, {emoji_stats["animated_disabled"]} animated\n'

        fmt = f'{fmt}Total Emoji: {len(guild.emojis)}/{guild.emoji_limit * 2}'
        e.add_field(name='Emoji', value=fmt, inline=False)
        e.set_footer(text='Created').timestamp = guild.created_at
        await ctx.send(embed=e)

    async def say_permissions(self, ctx, member, channel):
        permissions = channel.permissions_for(member)
        e = discord.Embed(colour=member.colour)
        avatar = member.avatar_url_as(static_format='png')
        e.set_author(name=str(member), url=avatar)
        allowed, denied = [], []
        for name, value in permissions:
            name = name.replace('_', ' ').replace('guild', 'server').title()
            if value:
                allowed.append(name)
            else:
                denied.append(name)

        e.add_field(name='Allowed', value='\n'.join(allowed))
        e.add_field(name='Denied', value='\n'.join(denied))
        await ctx.send(embed=e)

    @commands.command()
    @commands.guild_only()
    async def permissions(self, ctx, member: discord.Member = None, channel: discord.TextChannel = None):
        """Shows a member's permissions in a specific channel.
        If no channel is given then it uses the current one.
        You cannot use this in private messages. If no member is given then
        the info returned will be yours.
        """
        channel = channel or ctx.channel
        if member is None:
            member = ctx.author

        await self.say_permissions(ctx, member, channel)

    @commands.command()
    @commands.is_owner()
    async def debugpermissions(self, ctx, guild_id: int, channel_id: int, author_id: int = None):
        """Shows permission resolution for a channel and an optional author."""

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return await ctx.send('Guild not found?')

        channel = guild.get_channel(channel_id)
        if channel is None:
            return await ctx.send('Channel not found?')

        if author_id is None:
            member = guild.me
        else:
            member = await self.bot.get_or_fetch_member(guild, author_id)

        if member is None:
            return await ctx.send('Member not found?')

        await self.say_permissions(ctx, member, channel)

    # General commands
    @commands.command(aliases=["hi"], hidden=True)
    async def hello(self, ctx):
        """Go ahead, say hi!"""
        if Greeter:
            coro = Greeter.greet(ctx)
            if coro:
                return await eval(coro)
        greeting = random.choice(["Hello!", "Hallo!", "Hi!", "Nice to meet you", "Hey there!", "Beep boop!"])
        owner = self.bot.get_user(self.bot.owner_id)
        await ctx.send(f"{greeting} I'm a robot! {str(owner)} made me.")

    @commands.group(aliases=['invite'], invoke_without_command=True)
    async def join(self, ctx, bot: discord.User = None):
        """Get the invite link to add the bot (or any bot) to your server.

        Only works for bot accounts created post 2018 ish, when user IDs and client IDs match.
        """

        if bot is not None:
            if not bot.bot:
                return await ctx.send('That was not a bot.')
            return await ctx.send(f'<{discord.utils.oauth_url(bot.id)}>')
        embed = discord.Embed(colour=discord.Colour.blurple())
        embed.description = f'To add me to your server, please ensure it meets the following requirements:\n' \
                            f'```\n- Has at least 10 human members.\n' \
                            f'  - Servers smaller than this won\'t find me too useful.\n' \
                            f'- Has more humans than bots.\n' \
                            f'  - Bot collection servers are frowned upon.\n```\n' \
                            f'If you want to add me to a server that does not meet these requirements, make your ' \
                            f'case in the [support server](https://discord.gg/rqgRyF8) and you __*might*__ be ' \
                            f'whitelisted.\n\nThe link below lazily asks for admin perms. You can edit this to your ' \
                            f'liking. The bot needs no additional permissions to perform actions than what Discord ' \
                            f'requires it to have. No commands require the bot to have more permissions than ' \
                            f'necessary. The link will be updated once the exact permissions requirements has been ' \
                            f'identified and stabilised.'
        embed.add_field(name='Invite link', value=discord.utils.oauth_url(self.bot.client_id,
                                                                          discord.Permissions(administrator=True)))
        embed.set_author(name=self.bot.user.display_name if ctx.guild is None else ctx.guild.me.display_name,
                         icon_url=self.bot.user.avatar_url)
        await ctx.send(embed=embed)

    @join.error
    async def join_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send('That was not a valid client ID.')

    # leave a guild
    @commands.command(hidden=True)
    @commands.is_owner()
    async def leave(self, ctx, guild_id=None):
        if not await self.bot.is_owner(ctx.author):
            return
        if not guild_id:
            guild = ctx.guild
        elif not guild_id.isnumeric():
            return await ctx.send("Enter a valid guild ID", delete_after=30.0)

        if guild_id:
            guild = self.bot.get_guild(guild_id)
        if not guild:
            guild = await self.bot.fetch_guild(guild_id)
        if not guild:
            return await ctx.send('Guild not found.')
        name = guild.name
        await guild.leave()
        await self.bot.owner.send(f"Left '{name}'")

    @commands.command(hidden=True, aliases=["good bot"])
    async def goodbot(self, ctx):
        """Appreci8 that wun"""
        await ctx.send(f"Thanks {ctx.author.mention}, I try :slight_smile:")

    @commands.command(hidden=True)
    async def ping(self, ctx):
        """
        Returns bot latency
        """
        response_start = pytime.perf_counter()
        message = await ctx.send('Pinging...')
        response_end = pytime.perf_counter()
        response_fmt = f'{(response_end - response_start) * 1000:,.2f}ms'

        db_start = pytime.perf_counter()
        call = await ctx.db.fetch('SELECT 1;')
        db_end = pytime.perf_counter()
        db_fmt = f'{(db_end - db_start) * 1000:,.2f}ms'

        hb_fmt = f'{ctx.bot.latency * 1000:,.2f}ms'

        embed = discord.Embed(color=discord.Colour.blurple())
        embed.add_field(name='Websocket', value=hb_fmt)
        embed.add_field(name='Response', value=response_fmt)
        embed.add_field(name='Database', value=db_fmt)
        # again, this is due to fucked up perms in some mute roles
        if message is None:
            return
        await message.edit(content='Pong!', embed=embed)


def setup(bot):
    bot.add_cog(Meta(bot))
