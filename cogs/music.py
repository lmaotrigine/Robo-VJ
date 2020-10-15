from discord.ext import commands, tasks
import discord
import asyncpg
from typing import Union

class Music(commands.Cog):
    """For maintaining dedicated channels for music commands, or for general voice rooms"""
    def __init__(self, bot):
        self.bot = bot
        self.startup.start()

    def is_in_voice(self, state, records):
        return state.channel is not None and state.channel.id in [record['voice_id'] for record in records]

    def is_outside_voice(self, state, records):
        return state.channel is None or state.channel.id not in [record['voice_id'] for record in records]

    @tasks.loop(count=1)
    async def startup(self):
        await self.bot.db.execute("CREATE TABLE IF NOT EXISTS music (id SERIAL PRIMARY KEY, guild_id BIGINT, voice_id BIGINT, text_id BIGINT)")
        records = await self.bot.db.fetch("SELECT * FROM music")
        self.guilds = set([record['guild_id'] for record in records])

    @startup.before_loop
    async def before_start(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.guild.id not in self.guilds:
            return
        records = await self.bot.db.fetch("SELECT voice_id, text_id FROM music WHERE guild_id = $1", member.guild.id)
        mapping = dict((record['voice_id'], record['text_id']) for record in records)

        if self.is_in_voice(before, records) and self.is_outside_voice(after, records):
            # left channel
            text_channel = member.guild.get_channel(mapping[before.channel.id])
            await text_channel.set_permissions(member, read_messages=None)
            if DJ := discord.utils.get(member.roles, name='DJ'):
                await member.remove_roles(DJ)
        elif self.is_in_voice(after, records) and self.is_outside_voice(before, records):
            # joined voice
            text_channel = member.guild.get_channel(mapping[after.channel.id])
            await text_channel.set_permissions(member, read_messages=True)
            if DJ := discord.utils.get(member.guild.roles, name='DJ'):
                await member.add_roles(DJ)

        elif after.channel != before.channel and self.is_in_voice(after, records) and self.is_in_voice(before, records):
            # exceptional case where member moves between music channels directly
            before_channel = member.guild.get_channel(mapping[before.channel.id])
            after_channel = member.guild.get_channel(mapping[after.channel.id])
            await before_channel.set_permissions(member, read_messages=None)
            await after_channel.set_permissions(member, read_messages=True)

    @commands.command()
    @commands.guild_only()
    @commands.check(lambda x: x.author == x.guild.owner)
    async def add_mapping(self, ctx, voice: discord.VoiceChannel, text: discord.TextChannel):
        """Map a voice and text channel in your server. You need to be the owner to use this command. Use the channel IDs for best results."""
        if not (ctx.guild.get_channel(voice.id) and ctx.guild.get_channel(text.id)):
            return await ctx.send("Please enter channels belonging to this guild.")
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            if await self.bot.db.fetchrow("SELECT * FROM music WHERE guild_id = $1 and voice_id = $2", ctx.guild.id, voice.id):
                await self.bot.db.execute("UPDATE music SET text_id = $1 WHERE voice_id = $2 AND guild_id = $3", text.id, voice.id, ctx.guild.id)
            elif await self.bot.db.fetchrow("SELECT * FROM music WHERE guild_id = $1 and text_id = $2", ctx.guild.id, text.id):
                await self.bot.db.execute("UPDATE music SET voice_id = $1 WHERE text_id = $2 AND guild_id = $3", voice.id, text.id, ctx.guild.id)
            else:
                await self.bot.db.execute("INSERT INTO music (guild_id, voice_id, text_id) VALUES ($1, $2, $3)", ctx.guild.id, voice.id, text.id)
                self.guilds.add(ctx.guild.id)
        await self.bot.db.release(connection)
        await ctx.send(f"Mapped {voice.mention} with {text.mention}. Make sure to set permissions for {text.mention} accordingly.")

    @commands.command()
    @commands.guild_only()
    @commands.check(lambda x: x.author == x.guild.owner)
    async def remove_mapping(self, ctx, channel: Union[discord.TextChannel, discord.VoiceChannel]):
        """Removes a mapping associated with a specific channel. Mention only one channel."""
        if not ctx.guild.get_channel(channel.id):
            return await ctx.send("Please enter channels belonging to this guild.")
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            if await self.bot.db.fetchrow("SELECT * FROM music WHERE guild_id = $1 and text_id = $2", ctx.guild.id, channel.id):
                await self.bot.db.execute("DELETE FROM music WHERE guild_id = $1 and text_id = $2", ctx.guild.id, channel.id)
                await ctx.send("Mapping deleted.")
            elif await self.bot.db.fetchrow("SELECT * FROM music WHERE guild_id = $1 and voice_id = $2", ctx.guild.id, channel.id):
                await self.bot.db.execute("DELETE FROM music WHERE guild_id = $1 and voice_id = $2", ctx.guild.id, channel.id)
                await ctx.send("Mapping deleted.")
            else:
                await ctx.send("No mapping associated with this channel found.")
            if not await self.bot.db.fetchrow("SELECT * FROM music WHERE guild_id = $1", ctx.guild.id):
                self.guilds.discard(ctx.guild.id)
        await self.bot.db.release(connection)

def setup(bot):
    bot.add_cog(Music(bot))
