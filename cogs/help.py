import discord
from discord.ext import commands
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
    def get_ending_note(self):
        return f'''Use {self.clean_prefix}{self.invoked_with} [command] for more info on a command.
Use {self.clean_prefix}{self.invoked_with} [category] for more info on a category.'''
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

    # This makes it so it uses the function above
    # Less work for us to do since they're both similar.
    # If you want to make regular command help look different then override it
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

class Help(commands.Cog, name="Help"):
    def __init__(self, client):
        self.client = client
        self._original_help_command = self.client.help_command
        client.help_command = EmbedHelpCommand(dm_help=None, dm_help_threshold=10)
        client.help_command.cog = self
        
    def cog_unload(self):
        self.client.help_command = self._original_help_command

def setup(client):
    client.add_cog(Help(client))
