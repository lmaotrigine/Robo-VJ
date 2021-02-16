import discord
from discord.ext import commands


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
    async def pronouns(self, ctx, *, user: discord.User = None):
        user = user or ctx.author
        embed = discord.Embed(title=f'{user.display_name}\'s pronouns').set_footer(text='Powered by PronounDB.org') \
            .set_thumbnail(url=user.avatar_url)
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


def setup(bot):
    bot.add_cog(Pronouns())
