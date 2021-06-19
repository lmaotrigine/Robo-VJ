import aiohttp
import discord
from discord.ext import commands


class Upload(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != 818510032349691914:
            return
        if message.author.id != 411166117084528640:
            return
        if not message.attachments:
            return
        if not message.attachments[0].filename.endswith(('.pdf', '.mp4', '.png', '.jpg', '.jpeg', '.webp', '.gif')):
            return
        bytes_ = await message.attachments[0].read()
        headers = {'Authorization': self.bot.config.cdn_upload_token}
        data = aiohttp.FormData()
        data.add_field('fileupload', bytes_, filename=message.attachments[0].filename)
        async with self.bot.session.post('https://cdn.varunj.me/upload', data=data, headers=headers,
                                         params={'randomise': 'true'}) as resp:
            stat = resp.status
        await message.channel.send(f'Upload returned `{stat}`.\n<{await resp.read()}>\n{await resp.read()}')


def setup(bot):
    bot.add_cog(Upload(bot))
