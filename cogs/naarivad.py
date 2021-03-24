import aiohttp
import discord
from discord.ext import commands
import re

GUILD_ID = 0
UPLOADS_ID = 0
ADMINS_ID = 0

FILE_REGEX = re.compile(r'^(?P<id>\w+)_(?P<language>TA|UR|HI|BN|KA)\.(?P<extension>pdf|odt|doc|docx)$')


class Naarivad(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_check(self, ctx):
        return ctx.guild and ctx.guild.id == GUILD_ID

    @commands.Cog.listener('on_message')
    async def auto_upload(self, message):
        if message.guild is None or message.guild.id != GUILD_ID:
            return
        if message.channel.id != UPLOADS_ID:
            return
        if not message.attachments:
            return
        statuses = {}
        for attachment in message.attachments:
            if not FILE_REGEX.match(attachment.filename):
                await message.channel.send(f'Invalid filename `{attachment.filename}`. Skipping upload.')
            else:
                stat = await self.upload(attachment)
                statuses[attachment.filename] = stat
        await message.channel.send('\n'.join(f'`{key}`: status {val}' for key, val in statuses.items()))

    async def upload(self, attachment):
        bytes_ = await attachment.read()
        headers = {'Authorization': self.bot.config.naarivad_upload_token}
        data = aiohttp.FormData()
        data.add_field('fileupload', bytes_, filename=attachment.filename)
        async with self.bot.session.post('https://docs.naarivad.in/upload', data=data, headers=headers) as resp:
            stat = resp.status
        return stat


def setup(bot):
    bot.add_cog(Naarivad(bot))
