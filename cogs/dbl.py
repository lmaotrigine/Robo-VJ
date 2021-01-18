import discord
from discord.ext import commands
import json
import logging
import dbl
import datetime

log = logging.getLogger(__name__)


DISCORD_BOTS_API = 'https://discord.bots.gg/api/v1'
TOP_GG_API = 'https://top.gg/api'


class DBL(commands.Cog):
    """Cog tp update discord.bots.gg bot information."""

    def __init__(self, bot):
        self.bot = bot
        self.dbl_client = dbl.DBLClient(self.bot, self.bot.config.dbl_token, autopost=False,
                                        webhook_port=5000, webhook_auth=self.bot.config.dbl_auth)
        self.webhook = discord.Webhook.partial(*self.bot.config.dbl_webhook,
                                               adapter=discord.AsyncWebhookAdapter(session=self.bot.session))

    async def update(self):
        guild_count = len(self.bot.guilds)

        payload = json.dumps({
            'guildCount': guild_count,
            'shardCount': len(self.bot.shards)
        })

        headers = {
            'authorization': self.bot.bots_key,
            'content-type': 'application/json'
        }

        url = f'{DISCORD_BOTS_API}/bots/{self.bot.user.id}/stats'
        async with self.bot.session.post(url, data=payload, headers=headers) as resp:
            log.info(f'DBots statistics returned {resp.status} for {payload}')

        headers = {
            'Authorization': self.bot.config.dbl_token,
            'Content-Type': 'application/json'
        }
        payload = json.dumps({
            'server_count': guild_count,
            'shard_count': len(self.bot.shards)
        })
        url = f'{TOP_GG_API}/bots/{self.bot.user.id}/stats'
        async with self.bot.session.post(url, data=payload, headers=headers) as resp:
            log.info(f'Top.gg statistics returned {resp.status} for {payload}.')

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.update()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        await self.update()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.update()

    @commands.Cog.listener()
    async def on_dbl_vote(self, data):
        user_id = data.get('user')
        user = self.bot.get_user(user_id)
        if user is None:
            user = await self.bot.fetch_user(user_id)
        embed = discord.Embed(title='New upvote', colour=discord.Colour.blurple())
        embed.set_author(name=str(user), icon_url=user.avatar_url)
        embed.add_field(name='Total Votes', value=(await self.dbl_client.get_bot_info())['points'])
        embed.timestamp = datetime.datetime.utcnow()
        await self.webhook.send(embed=embed, avatar_url='https://top.gg/images/dblnew.png', username='Top.gg')

    @commands.Cog.listener()
    async def on_dbl_test(self, data):
        await self.webhook.send(str(data))


def setup(bot):
    bot.add_cog(DBL(bot))
