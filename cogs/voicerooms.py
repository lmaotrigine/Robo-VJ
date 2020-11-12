from discord.ext import commands, tasks
import discord
import asyncpg
from typing import Union
from .utils import checks, db

class MusicTable(db.Table, table_name='music'):
    id = db.PrimaryKeyColumn()
    guild_id = db.Column(db.Integer(big=True))
    voice_id = db.Column(db.Integer(big=True))
    text_id = db.Column(db.Integer(big=True))

class VoiceRooms(commands.Cog):
    """For maintaining dedicated channels for music commands, or for general voice rooms"""
    def __init__(self, bot):
        self.bot = bot
        self.startup.start()

    def cog_unload(self):
        self.startup.cancel()

    def is_in_voice(self, state):
        return state.channel is not None and state.channel.id in self.mapping[state.channel.guild.id].keys()

    def is_outside_voice(self, state):
        return state.channel is None or state.channel.id not in self.mapping[state.channel.guild.id].keys()

    @tasks.loop(count=1)
    async def startup(self):
        records = await self.bot.pool.fetch("SELECT * FROM music")
        self.mapping = {}
        for record in records:
            current = self.mapping.get(record['guild_id'], {})
            current.update({record['voice_id']: record['text_id']})
            self.mapping[record['guild_id']] = current

    @startup.before_loop
    async def before_start(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.guild.id not in self.mapping.keys():
            return
        
        if self.is_in_voice(before) and self.is_outside_voice(after):
            # left channel
            text_channel = member.guild.get_channel(self.mapping[member.guild.id][before.channel.id])
            await text_channel.set_permissions(member, read_messages=None)
            if DJ := discord.utils.get(member.roles, name='DJ'):
                await member.remove_roles(DJ)
        elif self.is_in_voice(after) and self.is_outside_voice(before):
            # joined voice
            text_channel = member.guild.get_channel(self.mapping[member.guild.id][after.channel.id])
            await text_channel.set_permissions(member, read_messages=True)
            if DJ := discord.utils.get(member.guild.roles, name='DJ'):
                await member.add_roles(DJ)

        elif after.channel != before.channel and self.is_in_voice(after) and self.is_in_voice(before):
            # exceptional case where member moves between music channels directly
            before_channel = member.guild.get_channel(self.mapping[member.guild.id][before.channel.id])
            after_channel = member.guild.get_channel(self.mapping[member.guild.id][after.channel.id])
            await before_channel.set_permissions(member, read_messages=None)
            await after_channel.set_permissions(member, read_messages=True)

    @commands.command()
    @commands.guild_only()
    @checks.is_admin()
    async def add_mapping(self, ctx, voice: discord.VoiceChannel, text: discord.TextChannel):
        """Map a voice and text channel in your server. Use the channel IDs for best results."""
        if not (ctx.guild.get_channel(voice.id) and ctx.guild.get_channel(text.id)):
            return await ctx.send("Please enter channels belonging to this guild.")
        connection = await self.bot.pool.acquire()
        async with connection.transaction():
            if await self.bot.pool.fetchrow("SELECT * FROM music WHERE guild_id = $1 and voice_id = $2", ctx.guild.id, voice.id):
                await self.bot.pool.execute("UPDATE music SET text_id = $1 WHERE voice_id = $2 AND guild_id = $3", text.id, voice.id, ctx.guild.id)
            elif await self.bot.pool.fetchrow("SELECT * FROM music WHERE guild_id = $1 and text_id = $2", ctx.guild.id, text.id):
                await self.bot.pool.execute("UPDATE music SET voice_id = $1 WHERE text_id = $2 AND guild_id = $3", voice.id, text.id, ctx.guild.id)
            else:
                await self.bot.pool.execute("INSERT INTO music (guild_id, voice_id, text_id) VALUES ($1, $2, $3)", ctx.guild.id, voice.id, text.id)
        
        await self.bot.pool.release(connection)
        current = self.mapping.get(ctx.guild.id, {})
        current.update({voice.id: text.id})
        self.mapping[ctx.guild.id] = current
        await ctx.send(f"Mapped {voice.mention} with {text.mention}. Make sure to set permissions for {text.mention} accordingly.")

    @commands.command()
    @commands.guild_only()
    @checks.is_admin()
    async def remove_mapping(self, ctx, channel: Union[discord.TextChannel, discord.VoiceChannel]):
        """Removes a mapping associated with a specific channel. Mention only one channel."""
        if not ctx.guild.get_channel(channel.id):
            return await ctx.send("Please enter channels belonging to this guild.")
        connection = await self.bot.pool.acquire()
        async with connection.transaction():
            if await self.bot.pool.fetchrow("SELECT * FROM music WHERE guild_id = $1 and text_id = $2", ctx.guild.id, channel.id):
                await self.bot.pool.execute("DELETE FROM music WHERE guild_id = $1 and text_id = $2", ctx.guild.id, channel.id)
                await ctx.send("Mapping deleted.")
            elif await self.bot.pool.fetchrow("SELECT * FROM music WHERE guild_id = $1 and voice_id = $2", ctx.guild.id, channel.id):
                await self.bot.pool.execute("DELETE FROM music WHERE guild_id = $1 and voice_id = $2", ctx.guild.id, channel.id)
                await ctx.send("Mapping deleted.")
            else:
                await ctx.send("No mapping associated with this channel found.")
            if not await self.bot.pool.fetchrow("SELECT * FROM music WHERE guild_id = $1", ctx.guild.id):
                self.mapping.pop(ctx.guild.id)
                return
        await self.bot.pool.release(connection)
        current = self.mapping.get(ctx.guild.id, {})
        if isinstance(channel, discord.TextChannel):
            for v, t in current.items():
                if channel.id == t:
                    current.pop(v)
                    break
        else:
            current.pop(channel.id)
        self.mapping[ctx.guild.id] = current

def setup(bot):
    bot.add_cog(VoiceRooms(bot))
