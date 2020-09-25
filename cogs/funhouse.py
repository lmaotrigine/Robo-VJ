import discord
from discord.ext import commands
import googletrans
import io
import asyncio

GUILD_ID = 718378271800033318
NO_MIC_BOUNCE_ID = 758217695748554802
BOUNCE_VOICE_ID = 718378272337166396
INTRO_ID = 744131093568946229

class Funhouse(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.trans = googletrans.Translator()

    def is_in_bounce(self, state):
        return state.channel is not None and state.channel.id == BOUNCE_VOICE_ID

    def is_out_of_bounce(self, state):
        return state.channel is None or state.channel.id != BOUNCE_VOICE_ID

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild and message.guild.id == GUILD_ID:
            if message.channel == message.guild.get_channel(INTRO_ID):
                if not message.author.guild_permissions.manage_guild:
                    await asyncio.sleep(5)
                    await message.channel.set_permissions(ctx.author, send_messages=False)

    @commands.command(hidden=True)
    @commands.guild_only()
    async def resetintro(self, ctx, member: discord.Member):
        if not ctx.author == ctx.guild.owner:
            return
        await ctx.guild.get_channel(INTRO_ID).set_permissions(ctx.author, send_messages=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.guild.id != GUILD_ID:
            return

        no_mic_bounce_channel = member.guild.get_channel(NO_MIC_BOUNCE_ID)
        if self.is_out_of_bounce(before) and self.is_in_bounce(after):
            # joined bounce
            await no_mic_bounce_channel.set_permissions(member, read_messages=True)
        elif self.is_in_bounce(before) and self.is_out_of_bounce(after):
            # left bounce
            await no_mic_bounce_channel.set_permissions(member, read_messages=None)

    @commands.command(hidden=True)
    async def translate(self, ctx, *, message: commands.clean_content):
        """Translates a message to English using Google translate."""

        loop = self.client.loop
        try:
            ret = await loop.run_in_executor(None, self.trans.translate, message)
        except Exception as e:
            return await ctx.send(f'An error occurred: {e.__class__.__name__}: {e}')

        embed=discord.Embed(title='Translated', colour=0x4284F3)
        src = googletrans.LANGUAGES.get(ret.src, '(auto-detected)').title()
        dest = googletrans.LANGUAGES.get(ret.dest, 'Unknown').title()
        embed.add_field(name=f'From {src}', value=ret.origin, inline=False)
        embed.add_field(name=f'To {dest}', value=ret.text, inline=False)
        await ctx.send(embed=embed)

    @commands.command(hidden=True)
    async def cat(self, ctx):
        """Gives you a random cat."""
        async with self.client.session.get('https://api.thecatapi.com/v1/images/search') as resp:
            if resp.status != 200:
                return await ctx.send('No cat found :(')
            js = await resp.json()
            await ctx.send(embed=discord.Embed(title='Random Cat').set_image(url=js[0]['url']))

    @commands.command(hidden=True)
    async def dog(self, ctx):
        """Gives you a random dog"""
        async with self.client.session.get('https://random.dog/woof') as resp:
            if resp.status != 200:
                return await ctx.send('No dog found :(')

            filename = await resp.text()
            url = f'https://random.dog/{filename}'
            filesize = ctx.guild.filesize_limit if ctx.guild else 8388608
            if filename.endswith(('.mp4', '.webm')):
                async with ctx.typing():
                    async with self.client.session.get(url) as other:
                        if other.status != 200:
                            return await ctx.send('Could not download dog video :(')

                        if int(other.headers['Content-Length']) >= filesize:
                            return await ctx.send(f'Video was too big to upload... See it here: {url} instead.')

                        fp = io.BytesIO(await other.read())
                        await ctx.send(file=discord.File(fp, filename=filename))
            else:
                await ctx.send(embed=discord.Embed(title='Random Dog').set_image(url=url))

def setup(client):
    client.add_cog(Funhouse(client))
