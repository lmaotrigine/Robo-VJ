import discord
import base64
import datetime
import itertools
import random
from discord.ext import commands
from collections import namedtuple
from typing import Union
from bot import RoboVJ


class Miscellaneous(commands.Cog):
    """Miscellaneous commands I think are useful."""
    def __init__(self, bot: RoboVJ):
        self.bot = bot

    def parse_date(self, token):
        token_epoch = 1293840000
        bytes_int = base64.standard_b64decode(token + '==')
        decoded = int.from_bytes(bytes_int, 'big')
        timestamp = datetime.datetime.utcfromtimestamp(decoded)

        # sometimes works
        if timestamp.year < 2015:
            timestamp = datetime.datetime.utcfromtimestamp(decoded + token_epoch)
        return timestamp

    @commands.command(aliases=['pt', 'ptoken'], brief='Decodes the token showing user ID and the token creation date.')
    async def parse_token(self, ctx, token):
        """Decodes the token by splitting it into 3 parts.

        First part is a user ID where it was decoded from base64 into str.
        The second part is the creation of the token which is converted from base64 into int.
        The last part cannot be decoded due to Discord encryption.
        """
        token_parts = token.split('.')
        if len(token_parts) != 3:
            return await ctx.reply('Invalid token.')

        def decode_user(user):
            user_bytes = user.encode()
            user_id_decoded = base64.b64decode(user_bytes)
            return user_id_decoded.decode(encoding='ascii')
        try:
            str_id = decode_user(token_parts[0])
        except Exception:
            str_id = None
        if not str_id or not str_id.isdigit():
            return await ctx.reply('Invalid user.')
        user_id = int(str_id)
        try:
            member = ctx.guild.get_member(user_id) or self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
        except discord.NotFound:
            member = None
        if not member:
            return await ctx.reply('Invalid user.')

        try:
            timestamp = self.parse_date(token_parts[1])
        except Exception:
            timestamp = 'Invalid date.'
        timestamp = timestamp or 'Invalid date.'

        embed = discord.Embed(title=f'{member.display_name}\'s token',
                              description=f'**User:** `{member}`\n'
                                          f'**ID:** `{member.id}`\n'
                                          f'**Bot:** `{member.bot}`\n'
                                          f'**Created:** `{member.created_at}`\n'
                                          f'**Token Created:** `{timestamp}`',
                              colour=discord.Colour.blurple(),
                              timestamp=datetime.datetime.utcnow())
        embed.set_thumbnail(url=member.avatar_url)
        embed.set_footer(text=f'Requested by {ctx.author}', icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed)

    @commands.command(aliases=['gt', 'gtoken'], brief='Generates a new token given a user.')
    async def generate_token(self, ctx, member: Union[discord.Member, discord.User] = None):
        """Generate a new token for a given user (defaults to command author).

        This works by encoding the user ID into a base64 str. While the current
        datetime in UTC is converted into timestamp and gets converted into
        base64 using the standard base64 encoding.

        The final part of the token is randomly generated.
        """
        member = member or ctx.author
        byte_first = str(member.id).encode(encoding='ascii')
        first_encode = base64.b64encode(byte_first)
        first = first_encode.decode(encoding='ascii')
        current_time = datetime.datetime.utcnow()
        epoch_offset = int(current_time.timestamp())
        bytes_int = int(epoch_offset).to_bytes(10, 'big')
        bytes_clean = bytes_int.lstrip(b'\x00')
        unclean_middle = base64.standard_b64encode(bytes_clean)
        middle = unclean_middle.decode(encoding='utf-8').rstrip('==')
        Pair = namedtuple('Pair', 'min max')
        num = Pair(48, 57)  # 0 - 9
        cap_alp = Pair(65, 90)  # A - Z
        cap = Pair(97, 122)  # a - z
        select = (num, cap_alp, cap)
        last = ''
        for each in range(27):
            pair = random.choice(select)
            last += str(chr(random.randint(pair.min, pair.max)))

        complete = '.'.join((first, middle, last))
        fields = (('Token created:', f'`{current_time}`'),
                  ('Generated Token:', f'`{complete}`'))

        embed = discord.Embed(title=f'{member.display_name}\'s token',
                              description=f'**User:** `{member}`\n'
                                          f'**ID:** `{member.id}`\n'
                                          f'**Bot:** `{member.bot}`',
                              colour=discord.Colour.blurple(),
                              timestamp=datetime.datetime.utcnow())

        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
        embed.set_thumbnail(url=member.avatar_url)
        embed.set_footer(text=f'Requested by {ctx.author}', icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed)

    @commands.command(aliases=['threadcount'], brief='Finds the original message of a thread.')
    async def replycount(self, ctx, message: discord.Message):
        """Finds the original message of a thread.

        This shows the number of replies, the message itself, the message url of the thread and the author.
        """
        def count_reply(m, replies=0):
            if isinstance(m, discord.MessageReference):
                return count_reply(m.cached_message, replies)
            if isinstance(m, discord.Message):
                if not m.reference:
                    return m, replies
                replies += 1
                return count_reply(m.reference, replies)

        msg, count = count_reply(message)
        embed_dict = {
            'title': 'Reply Count',
            'description': f'**Original:** `{msg.author}`\n'
                           f'**Message:** `{message.content}`\n'
                           f'**Replies:** `{count}`\n'
                           f'**Origin:** [`jump`]({msg.jump_url})'
        }
        embed = discord.Embed.from_dict(embed_dict)
        embed.set_footer(text=f'Requested by {ctx.author}', icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed)

    @commands.command(aliases=['find_type', 'findtypes', 'idtype', 'id_type', 'idtypes'])
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def findtype(self, ctx, id: discord.Object):
        """Try to find the type of an ID."""
        bot = self.bot

        async def found_message(type_id):
            await ctx.send(embed=discord.Embed(title='Type Finder',
                                               description=f'**ID:** `{id.id}`\n'
                                                           f'**Type:** `{type_id.capitalize()}`\n'
                                                           f'**Created:** `{id.created_at}`'))

        async def find(w, t):
            try:
                method = getattr(bot, f'{w}_{t}')
                if result := await discord.utils.maybe_coroutine(method, id.id):
                    return result is not None
            except discord.Forbidden:
                return ('fetch', 'guild') != (w, t)
            except (discord.NotFound, AttributeError):
                pass

        m = await bot.http._HTTPClient__session.get(f'https://cdn.discordapp.com/emojis/{id.id}')
        if m.status == 200:
            return await found_message('emoji')

        try:
            await commands.MessageConverter().convert(ctx, str(id.id))
        except commands.MessageNotFound:
            pass
        else:
            return await found_message('message')

        for way, type_obj in itertools.product(('get', 'fetch'), ('channel', 'user', 'webhook', 'guild')):
            if await find(way, type_obj):
                return await found_message(type_obj)
        await ctx.reply('idk')


def setup(bot):
    bot.add_cog(Miscellaneous(bot))
