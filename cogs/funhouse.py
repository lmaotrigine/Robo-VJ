import enum
import discord
from discord.ext import commands
import googletrans
import io
import random

class RPS(enum.Enum):
    ROCK = 0
    PAPER = 1
    SCISSORS = 2

class RPSLS(enum.Enum):
    ROCK = 0
    SPOCK = 1
    PAPER = 2
    LIZARD = 3
    SCISSORS = 4

RULE_DICT = {
    'rock': {
        'lizard': 'crushes',
        'scissors': 'crushes'
    },
    'paper': {
        'rock': 'covers',
        'spock': 'disproves',
    },
    'scissors': {
        'paper': 'cuts',
        'lizard': 'decapitaties'
    },
    'lizard': {
        'spock': 'poisons',
        'paper': 'eats'
    },
    'spock': {
        'scissors': 'smashes',
        'rock': 'vapourises'
    }
}


class Funhouse(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.trans = googletrans.Translator()
        
    @commands.command(hidden=True)
    async def translate(self, ctx, *, message: commands.clean_content):
        """Translates a message to English using Google translate."""

        loop = self.bot.loop
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
        async with self.bot.session.get('https://api.thecatapi.com/v1/images/search') as resp:
            if resp.status != 200:
                return await ctx.send('No cat found :(')
            js = await resp.json()
            await ctx.send(embed=discord.Embed(title='Random Cat').set_image(url=js[0]['url']))

    @commands.command(hidden=True)
    async def dog(self, ctx):
        """Gives you a random dog"""
        async with self.bot.session.get('https://random.dog/woof') as resp:
            if resp.status != 200:
                return await ctx.send('No dog found :(')

            filename = await resp.text()
            url = f'https://random.dog/{filename}'
            filesize = ctx.guild.filesize_limit if ctx.guild else 8388608
            if filename.endswith(('.mp4', '.webm')):
                async with ctx.typing():
                    async with self.bot.session.get(url) as other:
                        if other.status != 200:
                            return await ctx.send('Could not download dog video :(')

                        if int(other.headers['Content-Length']) >= filesize:
                            return await ctx.send(f'Video was too big to upload... See it here: {url} instead.')

                        fp = io.BytesIO(await other.read())
                        await ctx.send(file=discord.File(fp, filename=filename))
            else:
                await ctx.send(embed=discord.Embed(title='Random Dog').set_image(url=url))

    @commands.command()
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def rpsls(self, ctx, choice=None):
        """It's very simple:
        Scissors cuts Paper
        Paper covers Rock
        Rock cruches Lizard
        Lizard poisons Spock
        Spock smashes Scissors
        Scissors decapitates Lizard
        Lizard eats Paper
        Paper disproves Spock
        Spock vapourises Rock
        And, as it always has,
        Rock crushes Scissors
        """
        if choice is None:
            await ctx.send_help('rpsls')
        try:
            choice = RPSLS[choice.upper()]
        except KeyError:
            return await ctx.send(f"Invalid choice. Choose one of {', '.join(name.capitalize() for name, _ in RPSLS.__members__.items())}.")

        bot_choice = RPSLS(random.randrange(5))
        
        res = (bot_choice.value - choice.value) % 5
        text = f"You chose _**{choice.name.capitalize()}**_."
        text += f"\nI choose _**{bot_choice.name.capitalize()}**_."
        if res == 0:
            text += "\nIt's a tie!"
        elif res < 3:
            text += f'\n{bot_choice.name.capitalize()} {RULE_DICT[bot_choice.name.lower()][choice.name.lower()]} {choice.name.capitalize()}!\nI win!'
        else:
            text += f'\n{choice.name.capitalize()} {RULE_DICT[choice.name.lower()][bot_choice.name.lower()]} {bot_choice.name.capitalize()}!\nYou win!'
        await ctx.send(text)

    @commands.command()
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def rps(self, ctx, choice=None):
        """Straightforward Rock paper scissors"""
        if choice is None:
            await ctx.send_help('rps')
        try:
            choice = RPS[choice.upper()]
        except KeyError:
            return await ctx.send(f"Invalid choice. Choose one of {', '.join(name.capitalize() for name, _ in RPS.__members__.items())}.")

        bot_choice = RPS(random.randrange(3))
   
        res = (bot_choice.value - choice.value) % 3
        text = f"You chose _**{choice.name.capitalize()}**_."
        text += f"\nI choose _**{bot_choice.name.capitalize()}**_."
        if res == 0:
            text += "\nIt's a tie!"
        elif res == 1:
            text += f'\n{bot_choice.name.capitalize()} {RULE_DICT[bot_choice.name.lower()][choice.name.lower()]} {choice.name.capitalize()}!\nI win!'
        else:
            text += f'\n{choice.name.capitalize()} {RULE_DICT[choice.name.lower()][bot_choice.name.lower()]} {bot_choice.name.capitalize()}!\nYou win!'
        await ctx.send(text)


def setup(bot):
    bot.add_cog(Funhouse(bot))
