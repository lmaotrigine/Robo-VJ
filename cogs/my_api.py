import asyncio
import discord
import datetime
import aiohttp
import bisect
from discord.ext import commands


class API(commands.Cog, command_attrs=dict(hidden=True)):
    """Cog to wrap around my personal API."""
    BASE = 'https://api.varunj.tk/'

    async def cog_command_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            return await ctx.send_help(ctx.command)
    
    @commands.command(aliases=['gest'])
    async def gestation(self, ctx, *, lmp):
        """/gestation?lmp=<lmp>"""
        colours = [discord.Colour.green(), discord.Colour.orange(), discord.Colour.dark_orange(), discord.Colour.red()]
        async with ctx.session.get(self.BASE + 'gestation', params=dict(lmp=lmp)) as resp:
            if resp.status >= 500:
                return await ctx.send('Server is down.')
            if resp.status == 400:
                try:
                    js = await resp.json()
                except aiohttp.ContentTypeError:
                    return await ctx.send('Server responded with 400: Bad Request')
                else:
                    return await ctx.send(f'{js["message"]}: `{js["parsed_date"]}`')
            js = await resp.json()
        
        embed = discord.Embed(
                colour=colours[bisect.bisect([15, 28, 40], int(js['gestation_age']))],
               # timestamp=datetime.datetime.strptime(js['edd'], '%d %b %Y')
            )
        embed.add_field(name='Date of last menstrual period', value=js['lmp'], inline=False)
        embed.add_field(name='Gestation age', value='{0[0]} weeks {0[1]} days'.format(str(js['gestation_age']).split('.')))
       # embed.set_footer(text='Expected date of delivery')
        embed.add_field(name='Expected date of delivery', value=js['edd'])
        await ctx.send(embed=embed)

    @commands.command(name='antidepressant-or-tolkien', aliases=['antidepressant-tolkien',
        'drug-or-tolkien', 'drug-tolkien', 'tolkien-or-antidepressant', 'tolkien-or-drug',
        'tolkien-antidepressant', 'tolkien-drug', 't-or-a', 'a-or-t'])
    async def antidepressant_or_tolkien(self, ctx):
        """Guess if a word belongs to the Tolkien universe, or is the name of a drug.

        Inspired by [@checarina](https://twitter.com/checarina/status/977387234226855936)'s tweet.
        """
        drug_responses = ['drug', 'antidepressant', 'anti-depressant', 'd', 'a', 'ad']
        tolkien_responses = ['tolkien', 't']
        allowed_responses = drug_responses + tolkien_responses
        answers = {'tolkien': 'a Tolkien character', 'drug': 'an antidepressant'}
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in allowed_responses

        async with ctx.session.get(self.BASE + 'antidepressant-or-tolkien/random') as resp:
            js = await resp.json()

        await ctx.reply(f'**You have 15 seconds. Is this an antidepressant or a Tolkien character?**\n{js["name"]}')
        try:
            message = await ctx.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            return await ctx.send(f'Time\'s up! It was **{answers[js["type"]]}**\n\n_{js["text"]}_')
        if (message.content.lower() in drug_responses and js['type'] == 'drug') or \
                (message.content.lower() in tolkien_responses and js["type"] == 'tolkien'):
            await message.reply(f'Correct! it was **{answers[js["type"]]}**\n\n_{js["text"]}_')
        else:
            await message.reply(f'Oh no! It was **{answers[js["type"]]}**\n\n_{js["text"]}_')


def setup(bot):
    bot.add_cog(API())

