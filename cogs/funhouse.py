import enum
import discord
from discord.ext import commands
import googletrans
import io
import random
import re
import d20
from .utils.dice import PersistentRollContext, VerboseMDStringifier


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

    @commands.command(hidden=True)
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
            return await ctx.send_help('rpsls')
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
            text += f'\n_**{bot_choice.name.capitalize()}**_ {RULE_DICT[bot_choice.name.lower()][choice.name.lower()]} _**{choice.name.capitalize()}**_!\nI win!'
        else:
            text += f'\n_**{choice.name.capitalize()}**_ {RULE_DICT[choice.name.lower()][bot_choice.name.lower()]} _**{bot_choice.name.capitalize()}**_!\nYou win!'
        await ctx.send(text)

    @commands.command(hidden=True)
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def rps(self, ctx, choice=None):
        """Straightforward Rock paper scissors"""
        if choice is None:
            return await ctx.send_help('rps')
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
            text += f'\n_**{bot_choice.name.capitalize()}**_ {RULE_DICT[bot_choice.name.lower()][choice.name.lower()]} _**{choice.name.capitalize()}**_!\nI win!'
        else:
            text += f'\n_**{choice.name.capitalize()}**_ {RULE_DICT[choice.name.lower()][bot_choice.name.lower()]} _**{bot_choice.name.capitalize()}**_!\nYou win!'
        await ctx.send(text)

    ## DICE

    @commands.command(name='2', hidden=True)
    async def quick_roll(self, ctx, *, mod: str='0'):
        """Quickly rolls a d20."""
        rollstr = '1d20+' + mod
        await self.roll_cmd(ctx, rollstr=rollstr)

    @commands.command(name='roll', aliases=['r'])
    async def roll_cmd(self, ctx, *, rollstr: str='1d20'):
        """Roll is used to roll any combination of dice in the `XdY` format. (`1d6`, `2d8`, etc)
        
        Multiple rolls can be added together as an equation. Standard Math operators and Parentheses can be used: `() + - / *`
        
        Roll also accepts `adv` and `dis` for Advantage and Disadvantage. Rolls can also be tagged with `[text]` for informational purposes. Any text after the roll will assign the name of the roll.
        
        ___Examples___
        `!r` or `!r 1d20` - Roll a single d20, just like at the table
        `!r 1d20+4` - A skill check or attack roll
        `!r 1d8+2+1d6` - Longbow damage with Hunter’s Mark
        
        `!r 1d20+1 adv` - A skill check or attack roll with Advantage
        `!r 1d20-3 dis` - A skill check or attack roll with Disadvantage
        
        `!r (1d8+4)*2` - Warhammer damage against bludgeoning vulnerability
        
        `!r 1d10[cold]+2d6[piercing] Ice Knife` - The Ice Knife Spell does cold and piercing damage
        
        **Advanced Options**
        __Operators__
        Operators are always followed by a selector, and operate on the items in the set that match the selector.
        A set can be made of a single or multiple entries i.e. `1d20` or `(1d6,1d8,1d10)`
        
        These operations work on dice and sets of numbers
        `k` - keep - Keeps all matched values.
        `p` - drop - Drops all matched values.
        
        These operators only work on dice rolls.
        `rr` - reroll - Rerolls all matched die values until none match.
        `ro` - reroll - once - Rerolls all matched die values once. 
        `ra` - reroll and add - Rerolls up to one matched die value once, add to the roll.
        `mi` - minimum - Sets the minimum value of each die.
        `ma` - maximum - Sets the maximum value of each die.
        `e` - explode on - Rolls an additional die for each matched die value. Exploded dice can explode.
        
        __Selectors__
        Selectors select from the remaining kept values in a set.
        `X`  | literal X
        `lX` | lowest X
        `hX` | highest X
        `>X` | greater than X
        `<X` | less than X
        
        __Examples__
        `!r 2d20kh1+4` - Advantage roll, using Keep Highest format
        `!r 2d20kl1-2` - Disadvantage roll, using Keep Lowest format
        `!r 4d6mi2[fire]` - Elemental Adept, Fire
        `!r 10d6ra6` - Wild Magic Sorcerer Spell Bombardment
        `!r 4d6ro<3` - Great Weapon Master
        `!r 2d6e6` - Explode on 6
        `!r (1d6,1d8,1d10)kh2` - Keep 2 highest rolls of a set of dice
        
        **Additional Information can be found at:**
        https://d20.readthedocs.io/en/latest/start.html#dice-syntax
        """
        if rollstr == '0/0':  # easter eggs
            return await ctx.send("What do you expect me to do, destroy the universe?")
        
        rollstr, adv = self._string_search_adv(rollstr)

        res = d20.roll(rollstr, advantage=adv, allow_comments=True, stringifier=VerboseMDStringifier())
        out = str(res)
        if len(out) > 2047:
            out = f'{str(res)[:100]}...\n**Total**: {res.total}'
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await ctx.send(embed=discord.Embed(title=':game_die:', description=out, colour=discord.Colour.blurple()).set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url))

    @commands.command(name='multiroll', aliases=['rr'])
    async def rr(self, ctx, iterations: int, *, rollstr):
        """Rolls dice in xdy format a given number of times.
        Usage: !rr <iterations> <dice>
        """
        rollstr, adv = self._string_search_adv(rollstr)
        await self._roll_many(ctx, iterations, rollstr, adv=adv)

    @commands.command(name='iterroll', aliases=['rrr'])
    async def rrr(self, ctx, iterations: int, rollstr, dc: int=None, *, args=''):
        """Rolls dice in xdy format, given a set dc.
        Usage: !rrr <iterations> <xdy> <DC> [args]
        """
        _, adv = self._string_search_adv(rollstr)
        await self._roll_many(ctx, iterations, rollstr, dc, adv)

    async def _roll_many(self, ctx, iterations, roll_str, dc=None, adv=None):
        if iterations < 1 or iterations > 100:
            return await ctx.send("Too many or too few iterations.")
        if adv is None:
            adv = d20.AdvType.NONE
        results = []
        successes = 0
        ast = d20.parse(roll_str, allow_comments=True)
        roller = d20.Roller(context=PersistentRollContext())

        for _ in range(iterations):
            res = roller.roll(ast, advantage=adv)
            if dc is not None and res.total >= dc:
                successes += 1
            results.append(res)
        
        if dc is None:
            header = f'Rolling {iterations} iterations...'
            footer = f'{sum(o.total for o in results)} total.'
        else:
            header = f'Rolling {iterations} iterations, DC {dc}...'
            footer = f'{successes} successes, {sum(o.total for o in results)} total.'
        
        if ast.comment:
            header = f'{ast.comment}: {header}'

        result_strs = '\n'.join([str(o) for o in results])
        if len(result_strs) > 1500:
            result_strs = str(results[0])[:100]
            result_strs= f'{result_strs}...' if len(result_strs) > 100 else result_strs
        
        embed = discord.Embed(title=header, description=result_strs, colour=discord.Colour.blurple())
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
        embed.set_footer(text=footer)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await ctx.send(embed=embed)

    @staticmethod
    def _string_search_adv(rollstr):
        adv = d20.AdvType.NONE
        if re.search(r'(^|\s+)(adv|dis)(\s+|$)', rollstr) is not None:
            adv = d20.AdvType.ADV if re.search(r'(^|\s+)adv(\s+|$)', rollstr) is not None else d20.AdvType.DIS
            rollstr = re.sub(r'(adv|dis)(\s+|$)', '', rollstr)
        return rollstr, adv
        
def setup(bot):
    bot.add_cog(Funhouse(bot))
