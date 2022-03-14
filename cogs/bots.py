import asyncio
import discord
from discord.ext import commands


INFO = {
    718378271800033318 : {
        'channel': 792480023641980969,
        'testing': (
            782350873728647178,
        ),
        'terms': 'By requesting to add your bot, you must agree to the guidelines presented in the <#792473361233870869>.'
    },
    780811792015687721: {
        'channel': 0,
        'testing': None,
        'terms': '',
    }
}


def in_testing(info=INFO):
    def pred(ctx):
        try:
            if info[ctx.guild.id]['testing'] is None:
                return True
            return ctx.channel.id in info[ctx.guild.id]['testing']
        except (AttributeError, KeyError):
            return False
    return commands.check(pred)


class BotUser(commands.Converter):
    async def convert(self, ctx, argument):
        if not argument.isdigit():
            raise commands.BadArgument('Not a valid bot user ID.')
        try:
            user = await ctx.bot.fetch_user(int(argument))
        except discord.NotFound:
            raise commands.BadArgument('Bot user not found (404).')
        except discord.HTTPException as e:
            raise commands.BadArgument(f'Error fetching bot user: {e}')
        else:
            if not user.bot:
                raise commands.BadArgument('This is not a bot.')
            return user


class Bots(commands.Cog):
    """Easy bot adding framework."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.guild_only()
    @in_testing()
    async def addbot(self, ctx, user: BotUser, *, reason: str):
        """Requests a bot to be added to the server.

        To request a bot you must pass its user ID and a reason.

        You will get a DM regarding the status of the bot, so make sure you
        have them on.
        """
        info = INFO[ctx.guild.id]

        confirm = None
        def terms_acceptance(msg):
            nonlocal confirm
            if msg.author.id != ctx.author.id:
                return False
            if msg.channel.id != ctx.channel.id:
                return False
            if msg.content in ('**I agree**', 'I agree'):
                confirm = True
                return True
            elif msg.content in ('**Abort**', 'Abort'):
                confirm = False
                return True
            return False

        msg = f'{info["terms"]} Moderators reserve the right to kick or reject your bot for any reason.\n\n' \
              f'If you agree, reply to this message with **I agree** within one minute. ' \
              f'If you do not, reply with **Abort**.'
        prompt = await ctx.send(msg)

        try:
            await self.bot.wait_for('message', check=terms_acceptance, timeout=60.0)
        except asyncio.TimeoutError:
            return await ctx.send('Took too long. Aborting.')
        finally:
            await prompt.delete()

        if not confirm:
            return await ctx.send('Aborting.')

        url = f'https://discord.com/oauth2/authorize?client_id={user.id}&scope=bot&guild_id={ctx.guild.id}'
        description = f'{reason}\n\n[Invite URL]({url})'
        embed = discord.Embed(title='Bot Request', colour=discord.Colour.blurple(), description=description)
        embed.add_field(name='Author', value=f'{ctx.author} (ID: {ctx.author.id})', inline=False)
        embed.add_field(name='Bot', value=f'{user} (ID: {user.id})', inline=False)
        embed.timestamp = ctx.message.created_at

        # data for the bot to retrieve later
        embed.set_footer(text=ctx.author.id)
        embed.set_author(name=user.id, icon_url=user.avatar.url)

        channel = ctx.guild.get_channel(info['channel'])
        if channel is None:
            return await ctx.send('A verification channel was not found. Tell VJ.')

        try:
            msg = await channel.send(embed=embed)
            await msg.add_reaction('\N{WHITE HEAVY CHECK MARK}')
            await msg.add_reaction('\N{CROSS MARK}')
            await msg.add_reaction('\N{NO ENTRY SIGN}')
        except discord.HTTPException as e:
            return await ctx.send(f'Failed to request your bot somehow. Tell VJ, {str(e)!r}')

        await ctx.send('Your bot has been requested to the moderators. I will DM you the status of your request.')

    @addbot.error
    async def on_addbot_error(self, ctx, error):
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            return await ctx.send(error)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.guild_id not in INFO.keys():
            return

        emoji = str(payload.emoji)
        if emoji not in ('\N{WHITE HEAVY CHECK MARK}', '\N{CROSS MARK}', '\N{NO ENTRY SIGN}'):
            return

        channel_id = INFO[payload.guild_id]['channel']
        if payload.channel_id != channel_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel(payload.channel_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except (AttributeError, discord.HTTPException):
            return

        if len(message.embeds) != 1:
            return

        embed = message.embeds[0]
        # Already been handled
        if embed.colour != discord.Colour.blurple():
            return

        user = await self.bot.get_or_fetch_member(guild, payload.user_id)
        if user is None or user.bot:
            return

        author_id = int(embed.footer.text)
        bot_id = embed.author.name
        if emoji == '\N{WHITE HEAVY CHECK MARK}':
            to_send = f'Your bot, <@{bot_id}>, has been added to {channel.guild.name}.'
            colour = discord.Colour.dark_green()
        elif emoji == '\N{NO ENTRY SIGN}':
            to_send = f'Your bot, <@{bot_id}>, could not be added to {channel.guild.name}.\n' \
                      f'This could be because it was private or required code grant. ' \
                      f'Please make your bot public and resubmit your application.'
            colour = discord.Colour.orange()
        else:
            to_send = f'Your bot, <@{bot_id}>, has been rejected from {channel.guild.name}.'
            colour = discord.Colour.dark_magenta()

        member = await self.bot.get_or_fetch_member(guild, author_id)
        try:
            await member.send(to_send)
        except (AttributeError, discord.HTTPException):
            colour = discord.Colour.gold()

        embed.add_field(name='Responsible Moderator', value=f'{user} (ID: {user.id})', inline=False)
        embed.colour = colour
        await self.bot.http.edit_message(payload.channel_id, payload.message_id, embed=embed.to_dict())  # I'm lazy ok

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.guild == 718378271800033318 and member.bot:
            await member.add_roles(discord.Object(id=792679027626344459))  # Bot role ID

async def setup(bot):
    await bot.add_cog(Bots(bot))
