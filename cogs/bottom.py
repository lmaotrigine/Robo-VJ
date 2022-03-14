from typing import Union

import bottom
import discord
from discord.ext import commands


class Bottom(commands.Cog, command_attrs=dict(hidden=True)):
    """Random memery."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='bottom')
    async def bottom(self, ctx):
        """Bottom translation commands."""
        ...

    @bottom.command(name='encode')
    async def bottom_encode(self, ctx, *, message: Union[discord.Message, str] = None):
        """Encodes a message."""
        ref = ctx.message.reference
        if message is None:
            if isinstance(getattr(ref, 'resolved', None), discord.Message):
                message = ref.resolved.content
            else:
                return await ctx.send('No message to encode.')

        if isinstance(message, discord.Message):
            message = message.content

        await ctx.send(bottom.encode(message))

    @bottom.command(name='decode')
    async def bottom_decode(self, ctx, *, message: Union[discord.Message, str] = None):
        """Decodes a message."""
        ref = ctx.message.reference
        if message is None:
            if isinstance(getattr(ref, 'resolved', None), discord.Message):
                message = ref.resolved.content
            else:
                return await ctx.send('No message to decode.')

        if isinstance(message, discord.Message):
            message = message.content

        try:
            await ctx.send(bottom.decode(message))
        except ValueError:
            await ctx.send('Failed to decode message.')


async def setup(bot):
    await bot.add_cog(Bottom(bot))
