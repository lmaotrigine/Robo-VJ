# Cog to shange presence of the bot to show number of guiils.
# Also serves to check that all cogs have loaded successfully.
import discord
from discord.ext import commands, tasks

class ChangeState(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.change.start()

    def cog_unload(self):
        self.change.cancel()

    @tasks.loop(count=1)
    async def change(self):
        num_guilds = len(self.bot.guilds)
        await self.bot.change_presence(status=discord.Status.online, activity=discord.Activity(name=f"!help in {num_guilds} {'server' if num_guilds == 1 else 'servers'}",
        type=discord.ActivityType.listening))

    @change.before_loop
    async def before_change(self):
        print("Waiting...")
        await self.bot.wait_until_ready()

    @change.after_loop
    async def after_change(self):
        print("Presence changed\n================")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        num_guilds = len(self.bot.guilds)
        await self.bot.change_presence(status=discord.Status.dnd, activity=discord.Activity(name=f"!help in {num_guilds} {'server' if num_guilds == 1 else 'servers'}",
        type=discord.ActivityType.listening))

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        num_guilds = len(self.bot.guilds)
        await self.bot.change_presence(status=discord.Status.dnd, activity=discord.Activity(name=f"!help in {num_guilds} {'server' if num_guilds == 1 else 'servers'}",
        type=discord.ActivityType.listening))

def setup(bot):
    bot.add_cog(ChangeState(bot))
