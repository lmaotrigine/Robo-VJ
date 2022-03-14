import discord
from discord.ext import commands
from typing import Union, Optional


_LOOKUP = {
    'unspecified': 'Unspecified',
    'hh': 'he/him',
    'hi': 'he/it',
    'hs': 'he/she',
    'ht': 'he/they',
    'ih': 'it/him',
    'ii': 'it/its',
    'is': 'it/she',
    'it': 'it/they',
    'shh': 'she/he',
    'sh': 'she/her',
    'si': 'she/it',
    'st': 'she/they',
    'th': 'they/he',
    'ti': 'they/it',
    'ts': 'they/she',
    'tt': 'they/them',
    'any': 'Any Pronouns',
    'other': 'Other Pronouns',
    'ask': 'Ask me for my pronouns',
    'avoid': 'Avoid pronouns, use my name'
}


class Pronouns(commands.Cog, command_attrs=dict(hidden=True)):
    @commands.command(aliases=['whatpronouns'])
    async def pronouns(self, ctx, *, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        embed = discord.Embed(colour=discord.Colour.random()).set_footer(text='Powered by PronounDB.org') \
            .set_author(name=f'{user.display_name}\'s pronouns', icon_url=user.avatar.url)
        if user.bot:
            embed.description = '`beep/boop`'
            return await ctx.send(embed=embed)
        params = {'platform': 'discord', 'id': user.id}
        async with ctx.session.get('https://pronoundb.org/api/v1/lookup', params=params) as resp:
            if resp.status == 404:
                if user == ctx.author:
                    embed.description = 'You have not linked your Discord account with ' \
                                        '[PronounDB](https://pronoundb.org).'
                else:
                    embed.description = 'This user has not linked their Discord account with ' \
                                        '[PronounDB](https://pronoundb.org). Your best bet is asking for their' \
                                        'pronouns.'
            else:
                js = await resp.json()
                embed.description = f'`{_LOOKUP[js["pronouns"]]}`'
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Pronouns())
