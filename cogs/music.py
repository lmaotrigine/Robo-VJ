import discord
import asyncpg
from discord.ext import commands, tasks

class Music(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.load_data.start()
    
    def cog_unload(self):
        self.load_data.cancel()
    
    def is_in_voice(self, state):
        return state.channel is not None and state.channel.id in self.voice_config[state.channel.guild.id].keys()

    def is_outside_voice(self, state):
        return state.channel is None or state.channel not in self.voice_config[state.channel.guild.id].keys()

    @tasks.loop(count=1)
    async def load_data(self):
        data = await client.db.fetch("SELECT * FROM voice_rooms")
        self.voice_config = {}
        for guild_id in set([record['guild_id'] for record in data]):
            self.voice_config[guild_id] = {}
        for record in data:
            self.voice_config[record['guild_id']][record['voice_channel_id']] = record['voice_room_id']
        print("Voice config loaded")

    @load_data.before_loop
    async def before_data(self):
        await self.client.wait_until_ready()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.guild not in self.voice_config.keys():
            return

        if self.is_in_voice(after) and self.is_outside_voice(before):
            # joined channel
            await member.guild.get_channel(self.voice_config[member.guild.id][after.channel.id]).set_permissions(member, read_messages=True)
        elif self.is_in_voice(before) and self.is_outside_voice(after):
            # left channel
            await member.guild.get_channel(self.voice_config[member.guild.id][before.channel.id]).set_permissions(member, read_messages=None)

def setup(client):
    client.add_cog(Music(client))
