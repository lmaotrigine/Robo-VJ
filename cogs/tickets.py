import datetime
from typing import Optional
import discord
from discord.ext import commands
from .utils import db

GUILD_ID = 718378271800033318
CAT_ID = 775265697827127328
MOD_ROLE_ID = 718379678569594951
CLOSED_CAT_ID = 775321909562441748

class TicketsTable(db.Table, table_name='tickets'):
    id = db.PrimaryKeyColumn()
    user_id = db.Column(db.Integer(big=True))
    channel_id = db.Column(db.Integer(big=True))
    open = db.Column(db.Boolean, default=True)

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.open = {}  # dict() of user_id to channel_id
        self.task = self.bot.loop.create_task(self._prepare_tickets())

    def cog_unload(self):
        self.task.cancel()

    async def _prepare_tickets(self):
        self.guild = self.bot.get_guild(GUILD_ID)
        self.category = self.guild.get_channel(CAT_ID)
        self.closed_cat = self.guild.get_channel(CLOSED_CAT_ID)
        async with self.bot.pool.acquire() as con:
            records = await con.fetch("SELECT user_id, channel_id FROM tickets WHERE open = $1;", True)
            for record in records:
                self.open[record['user_id']] = record['channel_id']

    def _get_member(self, channel_id) -> Optional[discord.Member]:
        for k, v in self.open.items():
            if v == channel_id:
                return self.guild.get_member(k)
        return None

    async def open_ticket(self, user: discord.Member):
        query = "INSERT INTO tickets (user_id) VALUES ($1) RETURNING id;"
        async with self.bot.pool.acquire() as con:
            _id = await con.fetchval(query, user.id)
            chnl = await self.category.create_text_channel(f'Ticket-{_id}')
            await con.execute("UPDATE tickets SET channel_id = $1 WHERE user_id = $2", chnl.id, user.id)
        await chnl.set_permissions(user, read_messages=True, send_messages=True, read_message_history=True)
        embed = discord.Embed(description=f'Thank you for opening a ticket {user.mention}, a moderator will be here momentarily.\n' \
            f'Ticket ID: {_id}\nKeep a not of this ID for 7 days, if you wish to clarify anything later.')

        await chnl.send(f'{user.mention}, <@&{MOD_ROLE_ID}>', embed=embed)
        self.open[member.id] = chnl.id
    
    async def close_ticket(self, message):
        channel = message.channel
        await channel.set_permissions(self._get_member(channel.id), read_messages=None)
        await channel.edit(category=self.closed_cat)
        reminder = self.bot.get_cog('Reminder')
        if reminder is None:
            return await channel.send('A fatal error occurred. Could not find reminder cog.')
        timer = await reminder.create_timer(datetime.datetime.utcnow() + datetime.timedelta(days=7), 'ticket_del', channel.id,
                                                                                                               self._get_member(channel.id).id,
                                                                                                               created=message.created_at)
        query = "UPDATE tickets SET open = $1 WHERE channel_id = $2;"
        async with self.bot.pool.acquire() as con:
            await con.execute(query, False, channel.id)

    async def prompt_close(self, message):
        channel = message.channel
        msg = """> If there isn't anything else we can help you with, please close the ticket with `$close`.
        >
        > If there isn't a response after 12 hours, we will close the ticket automatically."""
        reminder = self.bot.get_cog('Reminder')
        if reminder is None:
            return await channel.send('A fatal error occurred. Could not find reminder cog.')
        timer = await reminder.create_timer(datetime.datetime.utcnow() + datetime.timedelta(hours=12), 'ticket_close', channel.id,
                                                                                                               self._get_member(channel.id).id,
                                                                                                               created=message.created_at)
        await channel.send(msg)
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_ticket_close_timer_complete(self, timer):
        channel_id, member_id = timer.args
        await self.bot.wait_until_ready()
        channel = self.guild.get_channel(channel_id)
        msg = await channel.send('Ticket has been inactive for 12 hours. Closing...')
        await self.close_ticket(msg)

    @commands.Cog.listener()
    async def on_ticket_del_timer_complete(self, timer):
        channel_id, member_id = timer.args
        await self.bot.wait_until_ready()
        channel = self.guild.get_channel(channel_id)
        await channel.delete()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild is None or message.channel.category != self.category:
            return
        
        if message.content.strip() == '$close':
            user = self._get_member(message.channel.id)
            await message.add_reaction('\N{WHITE HEAVY CHECK MARK}')
            await self.close_ticket(message)
            self.open.pop(user.id)

        if message.content.strip() in ('msgclose',):
            await self.prompt_close(message)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def tickets_init(self, ctx):
        embed = discord.Embed(description='React with \U0001f39f\U0000fe0f to open a new ticket.')
        embed.colour = discord.Colour.green()
        channel = self.guild.get_channel(775330246106021939)
        msg = await channel.send(embed=embed)
        await msg.add_reaction('\U0001f39f\U0000fe0f')
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')
    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.guild_id != GUILD_ID or payload.channel_id != 775330246106021939:
            return
        if str(payload.emoji) != '\U0001f39f\U0000fe0f':
            return
        if payload.member.bot:
            return
        channel = self.guild.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        await message.remove_reaction(payload.emoji, payload.member)
        if payload.member.id in self.open.keys():
            return
        await self.open_ticket(payload.member)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if channel.guild != self.guild or channel.category != self.category:
            return
        
        query = 'DELETE FROM tickets WHERE channel_id = $1'
        async with self.bot.pool.acquire() as con:
            await con.execute(query, channel.id)
        
        try:
            self.open.pop(self._get_member(channel.id).id)
        except KeyError:
            pass
        
def setup(bot):
    bot.add_cog(Tickets(bot))