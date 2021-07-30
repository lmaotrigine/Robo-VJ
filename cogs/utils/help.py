import discord
from discord.ext import commands, menus
import asyncio
from .paginator import RoboPages

class EmbedHelpCommand(commands.DefaultHelpCommand):
    """This is an example of a HelpCommand that utilizes embeds.
    It's pretty basic but it lacks some nuances that people might expect.
    1. It breaks if you have more than 25 cogs or more than 25 subcommands. (Most people don't reach this)
    2. It doesn't DM users. To do this, you have to override `get_destination`. It's simple.
    Other than those two things this is a basic skeleton to get you started. It should
    be simple to modify if you desire some other behaviour.

    To use this, pass it to the bot constructor e.g.:

    bot = commands.Bot(help_command=EmbedHelpCommand())
    """
    # Set the embed colour here
    COLOUR = discord.Colour.blurple()

    def __init__(self, **kwargs):
        super().__init__(command_attrs={'aliases' : ['h', '?']}, **kwargs)

    def get_ending_note(self):
        return f'''Use {self.context.clean_prefix}{self.invoked_with} [command] for more info on a command.
        Use {self.context.clean_prefix}{self.invoked_with} [category] for more info on a category.'''

    def get_command_signature(self, command):
        parent = command.full_parent_name
        if len(command.aliases) > 0:
            aliases = ' | '.join(command.aliases)
            fmt = '[%s | %s]' % (command.name, aliases)
            if parent:
                fmt = parent + ' ' + fmt
            alias = fmt
        else:
            alias = command.name if not parent else parent + ' ' + command.name

        return '%s %s' % (alias, command.signature)

    def get_destination(self, embed):
        ctx = self.context
        if self.dm_help is True:
            return ctx.author
        elif self.dm_help is None and len(embed.fields) > self.dm_help_threshold:
            return ctx.author
        else:
            return ctx.channel

    async def send_bot_help(self, mapping):
        embed = discord.Embed(title='Bot Commands', colour=self.COLOUR)
        description = self.context.bot.description
        if description:
            embed.description = description

        for cog, commands in mapping.items():
            name = 'General' if cog is None else cog.qualified_name
            if name == 'Jishaku': continue
            filtered = await self.filter_commands(commands, sort=True)
            if filtered:
                for c in filtered:
                    if filtered.count(c) > 1:
                        filtered.remove(c)
                value = ' | '.join(f'`{c.name}`' for c in filtered)
                if cog and cog.description:
                    value = '{0}\n{1}'.format(cog.description, value)

                embed.add_field(name=name, value=value, inline=False)
        embed.set_author(name=self.context.bot.user.display_name if not self.context.guild else self.context.guild.me.display_name, icon_url=self.context.bot.user.avatar_url)
        embed.set_footer(text=self.get_ending_note())
        await self.get_destination(embed).send(embed=embed)
        if self.get_destination(embed) != self.context.channel:
            await self.context.message.add_reaction('\U0001f4dc')

    async def send_cog_help(self, cog):
        embed = discord.Embed(title='{0.qualified_name} Commands'.format(cog), colour=self.COLOUR)
        if cog.description:
            embed.description = cog.description

        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        for command in filtered:
            embed.add_field(name=self.get_command_signature(command), value=command.short_doc or '...', inline=False)
        embed.set_author(name=self.context.bot.user.display_name if not self.context.guild else self.context.guild.me.display_name, icon_url=self.context.bot.user.avatar_url)
        embed.set_footer(text=self.get_ending_note())
        await self.get_destination(embed).send(embed=embed)
        if self.get_destination(embed) != self.context.channel:
            await self.context.message.add_reaction('\U0001f4dc')

    async def send_group_help(self, group):
        embed = discord.Embed(title=group.qualified_name, colour=self.COLOUR)
        if group.help:
            embed.description = group.help

        if isinstance(group, commands.Group):
            filtered = await self.filter_commands(group.commands, sort=True)
            for command in filtered:
                embed.add_field(name=self.get_command_signature(command), value=command.short_doc or '...', inline=False)
        embed.set_author(name=self.context.bot.user.display_name if not self.context.guild else self.context.guild.me.display_name, icon_url=self.context.bot.user.avatar_url)
        embed.set_footer(text=self.get_ending_note())
        await self.get_destination(embed).send(embed=embed)
        if self.get_destination(embed) != self.context.channel:
            await self.context.message.add_reaction('\U0001f4dc')


    async def send_command_help(self, command):
        embed = discord.Embed(title=f'{command.qualified_name} {command.signature}', colour=self.COLOUR)
        if command.help:
            embed.description = command.help
        if command.aliases:
            embed.add_field(name='Aliases', value=' | '.join(command.aliases))
        embed.set_author(name=self.context.bot.user.display_name if not self.context.guild else self.context.guild.me.display_name, icon_url=self.context.bot.user.avatar_url)
        embed.set_footer(text=self.get_ending_note())
        await self.get_destination(embed).send(embed=embed)
        if self.get_destination(embed) != self.context.channel:
            await self.context.message.add_reaction('\U0001f4dc')


class BotHelpPageSource(menus.ListPageSource):
    def __init__(self, help_command, commands):
        # entries = [(cog, len(sub)) for cog, sub in commands.items()]
        # entries.sort(key=lambda t: (t[0].qualified_name, t[1]), reverse=True)
        super().__init__(entries=sorted(commands.keys(), key=lambda c: c.qualified_name), per_page=6)
        self.commands = commands
        self.help_command = help_command
        self.prefix = help_command.context.clean_prefix

    def format_commands(self, cog, commands):
        # A field can only have 1024 characters so we need to paginate a bit
        # just in case it doesn't fit perfectly
        # However, we have 6 per page so I'll try cutting it off at around 800 instead
        # Since there's a 6000 character limit overall in the embed
        if cog.description:
            short_doc = cog.description.split('\n', 1)[0] + '\n'
        else:
            short_doc = 'No help found...\n'

        current_count = len(short_doc)
        ending_note = '+%d not shown'
        ending_length = len(ending_note)

        page = []
        for command in commands:
            value = f'`{command.name}`'
            count = len(value) + 1 # The space
            if count + current_count < 800:
                current_count += count
                page.append(value)
            else:
                # If we're maxed out then see if we can add the ending note
                if current_count + ending_length + 1 > 800:
                    # If we are, pop out the last element to make room
                    page.pop()

                # Done paginating so just exit
                break

        if len(page) == len(commands):
            # We're not hiding anything so just return it as-is
            return short_doc + ' '.join(page)

        hidden = len(commands) - len(page)
        return short_doc + ' '.join(page) + '\n' + (ending_note % hidden)

    async def format_page(self, menu, cogs):
        prefix = menu.ctx.prefix
        description = f'Use "{prefix}help command" for more info on a command.\n' \
                      f'Use "{prefix}help category" for more info on a category.\n' \
                       'For more help, join the official bot support server: https://discord.gg/rqgRyF8'

        embed = discord.Embed(title='Categories', description=description, colour=discord.Colour.blurple())

        for cog in cogs:
            commands = self.commands.get(cog)
            if commands:
                value = self.format_commands(cog, commands)
                embed.add_field(name=cog.qualified_name, value=value, inline=True)

        maximum = self.get_max_pages()
        embed.set_footer(text=f'Page {menu.current_page + 1}/{maximum}')
        return embed

class GroupHelpPageSource(menus.ListPageSource):
    def __init__(self, group, commands, *, prefix):
        super().__init__(entries=commands, per_page=6)
        self.group = group
        self.prefix = prefix
        self.title = f'{self.group.qualified_name} Commands'
        self.description = self.group.description

    async def format_page(self, menu, commands):
        embed = discord.Embed(title=self.title, description=self.description, colour=discord.Colour.blurple())

        for command in commands:
            signature = f'{command.qualified_name} {command.signature}'
            embed.add_field(name=signature, value=command.short_doc or 'No help given...', inline=False)

        maximum = self.get_max_pages()
        if maximum > 1:
            embed.set_author(name=f'Page {menu.current_page + 1}/{maximum} ({len(self.entries)} commands)')

        embed.set_footer(text=f'Use "{self.prefix}help command" for more info on a command.')
        return embed

class HelpMenu(RoboPages):
    def __init__(self, source):
        super().__init__(source)

    @menus.button('\N{WHITE QUESTION MARK ORNAMENT}', position=menus.Last(5))
    async def show_bot_help(self, payload):
        """shows how to use the bot"""

        embed = discord.Embed(title='Using the bot', colour=discord.Colour.blurple())
        embed.title = 'Using the bot'
        embed.description = 'Hello! Welcome to the help page.'

        entries = (
            ('<argument>', 'This means the argument is __**required**__.'),
            ('[argument]', 'This means the argument is __**optional**__.'),
            ('[A|B]', 'This means that it can be __**either A or B**__.'),
            ('[argument...]', 'This means you can have multiple arguments.\n' \
                              'Now that you know the basics, it should be noted that...\n' \
                              '__**You do not type in the brackets!**__')
        )

        embed.add_field(name='How do I use this bot?', value='Reading the bot signature is pretty simple.')

        for name, value in entries:
            embed.add_field(name=name, value=value, inline=False)

        embed.set_footer(text=f'We were on page {self.current_page + 1} before this message.')
        await self.message.edit(embed=embed)

        async def go_back_to_current_page():
            await asyncio.sleep(30.0)
            await self.show_page(self.current_page)

        self.bot.loop.create_task(go_back_to_current_page())

class PaginatedHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            'cooldown': commands.CooldownMapping.from_cooldown(1, 3.0, commands.BucketType.member),
            'help': 'Shows help about the bot, a command, or a category'
        })

    async def on_help_command_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            await ctx.send(str(error.original))

    def get_command_signature(self, command):
        parent = command.full_parent_name
        if len(command.aliases) > 0:
            aliases = '|'.join(command.aliases)
            fmt = f'[{command.name}|{aliases}]'
            if parent:
                fmt = f'{parent} {fmt}'
            alias = fmt
        else:
            alias = command.name if not parent else f'{parent} {command.name}'
        return f'{alias} {command.signature}'

    async def send_bot_help(self, mapping):
        async with self.context.typing():
            bot = self.context.bot
            entries = await self.filter_commands(bot.commands, sort=True)

            all_commands = {}
            for command in entries:
                if command.cog is None:
                    continue
                try:
                    all_commands[command.cog].append(command)
                except KeyError:
                    all_commands[command.cog] = [command]


            menu = HelpMenu(BotHelpPageSource(self, all_commands))
            await self.context.release()
        await menu.start(self.context)

    async def send_cog_help(self, cog):
        async with self.context.typing():
            entries = await self.filter_commands(cog.get_commands(), sort=True)
            menu = HelpMenu(GroupHelpPageSource(cog, entries, prefix=self.context.clean_prefix))
            await self.context.release()
        await menu.start(self.context)

    def common_command_formatting(self, embed_like, command):
        embed_like.title = self.get_command_signature(command)
        if command.description:
            desc = f'{command.description}\n\n{command.help}'
        else:
            desc = command.help or 'No help found...'
        if len(desc) > 2048:
            paginator = commands.Paginator(prefix='', suffix='', max_size=1024)
            for line in desc.split('\n'):
                paginator.add_line(line)
            embed_like.description = '\n'.join(paginator.pages[:2])
            if not isinstance(embed_like, discord.Embed):
                embed_like.description = f'{embed_like.description[:-3]}...'
            else:
                for page in paginator.pages[2:]:
                    embed_like.add_field(name='\u200b', value=page, inline=False)
        else:
            embed_like.description = desc
            
    async def send_command_help(self, command):
        # No pagination necessary for a single command.
        embed = discord.Embed(colour=discord.Colour.blurple())
        self.common_command_formatting(embed, command)
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        subcommands = group.commands
        if len(subcommands) == 0:
            return await self.send_command_help(group)

        entries = await self.filter_commands(subcommands, sort=True)
        if len(entries) == 0:
            return await self.send_command_help(group)

        source = GroupHelpPageSource(group, entries, prefix=self.context.clean_prefix)
        self.common_command_formatting(source, group)
        menu = HelpMenu(source)
        await self.context.release()
        await menu.start(self.context)
