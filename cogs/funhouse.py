import asyncio
from argparse import ArgumentParser
import enum
from http import HTTPStatus
import discord
from discord.ext import commands
import googletrans
import io
from typing import Optional, List
import random
import re
import d20
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import shlex
import textwrap
import time
import json
from typing import Union
from .utils.dice import PersistentRollContext, VerboseMDStringifier
from .utils import checks, languages, formats
from .utils.config import Config
from functools import partial


class Arguments(ArgumentParser):
    def error(self, message):
        raise RuntimeError(message)


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


class HTTPCode(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            HTTPStatus(int(argument))
        except ValueError:
            raise commands.BadArgument(f'Status code `{argument}` does not exist.')
        return int(argument)


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
        self.noreact = Config('noreact.json')

    async def do_translate(self, ctx, message, *, from_='auto', to='en'):
        ref = ctx.message.reference
        if message is None:
            if isinstance(getattr(ref, 'resolved', None), discord.Message):
                message = ref.resolved.clean_content
            else:
                return await ctx.send('No message to translate.')

        if isinstance(message, discord.Message):
            message = message.clean_content
        loop = self.bot.loop
        try:
            ret = await loop.run_in_executor(None, self.trans.translate, message, to, from_)
        except Exception as e:
            return await ctx.send(f'An error occurred: {e.__class__.__name__}: {e}')

        embed = discord.Embed(title='Translated', colour=0x4284F3)
        src = googletrans.LANGUAGES.get(ret.src, '(auto-detected)').title()
        dest = googletrans.LANGUAGES.get(ret.dest, 'Unknown').title()
        embed.add_field(name=f'From {languages.LANG_TO_FLAG.get(ret.src, "")} {src}', value=ret.origin, inline=False)
        embed.add_field(name=f'To {languages.LANG_TO_FLAG.get(ret.dest, "")} {dest}', value=ret.text, inline=False)
        if ret.pronunciation and ret.pronunciation != ret.text:
            embed.add_field(name='Pronunciation', value=ret.pronunciation)

        await ctx.send(embed=embed)
        
    @commands.command(hidden=True, invoke_without_command=True)
    async def translate(self, ctx, *, message: Union[discord.Message, commands.clean_content] = None):
        """Translates a message using Google translate.

        The following optional flags are allowed:

        `--source` or `-s`: The language to translate from, defaults to auto-detect.
        `--dest`  or `-d`: The language to translate to, defaults to English.
        """
        parser = Arguments(add_help=False, allow_abbrev=False)
        parser.add_argument('text', nargs='*', default=None)
        parser.add_argument('--dest', '-d', default='en')
        parser.add_argument('--source', '-s', '-src', default='auto')
        src = 'auto'
        dest = 'en'
        if not isinstance(message, discord.Message) and message is not None:
            args = parser.parse_args(shlex.split(message))
            message = ' '.join(args.text)
            src = args.source
            dest = args.dest
            if src.lower() not in googletrans.LANGUAGES and src.lower() not in googletrans.LANGCODES and src.lower() != 'auto':
                return await ctx.send('Invalid source language: {}'.format(src))
            if dest.lower() not in googletrans.LANGUAGES and dest.lower() not in googletrans.LANGCODES:
                return await ctx.send('Invalid destination language: {}'.format(dest))
            if message is not None:
                try:
                    message = await commands.MessageConverter().convert(ctx, message)
                except commands.BadArgument:
                    pass
                else:
                    message = message.clean_content

        await self.do_translate(ctx, message, from_=src.lower(), to=dest.lower())


    @commands.command(hidden=True)
    async def cat(self, ctx, code: HTTPCode = None):
        """Gives you a random cat.
        
        You may also provide an optional HTTP Status code to get the appropriate status cat
        from [here](https://http.cat)
        """
        if code is not None:
            await ctx.send(embed=discord.Embed(title=f'Status: {code}').set_image(url=f'https://http.cat/{code}.jpg'))
            return
        async with self.bot.session.get('https://api.thecatapi.com/v1/images/search') as resp:
            if resp.status != 200:
                return await ctx.send('No cat found :(')
            js = await resp.json()
            await ctx.send(embed=discord.Embed(title='Random Cat').set_image(url=js[0]['url']))

    @cat.error
    async def cat_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)

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
    async def quick_roll(self, ctx, *, mod: str = '0'):
        """Quickly rolls a d20."""
        rollstr = '1d20+' + mod
        await self.roll_cmd(ctx, rollstr=rollstr)

    @commands.command(name='roll', aliases=['r'], hidden=True)
    async def roll_cmd(self, ctx, *, rollstr: str = '1d20'):
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
        await ctx.send(embed=discord.Embed(title=':game_die:', description=out, colour=discord.Colour.blurple()).set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url))

    @commands.command(name='multiroll', aliases=['rr'], hidden=True)
    async def rr(self, ctx, iterations: int, *, rollstr):
        """Rolls dice in xdy format a given number of times.
        Usage: !rr <iterations> <dice>
        """
        rollstr, adv = self._string_search_adv(rollstr)
        await self._roll_many(ctx, iterations, rollstr, adv=adv)

    @commands.command(name='iterroll', aliases=['rrr'], hidden=True)
    async def rrr(self, ctx, iterations: int, rollstr, dc: int = None, *, args=''):
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
            result_strs = f'{result_strs}...' if len(result_strs) > 100 else result_strs
        
        embed = discord.Embed(title=header, description=result_strs, colour=discord.Colour.blurple())
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url)
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

    @commands.command(hidden=True)
    async def gay(self, ctx, *, user: discord.User = None):
        """Returns your avatar with a rainbow overlay."""
        url = f"https://some-random-api.ml/canvas/gay"
        user = user or ctx.author
        params = {'avatar': str(user.avatar.url)}
        async with self.bot.session.get(url, params=params) as resp:
            if resp.status != 200:
                return await ctx.send("Could not complete request. Try again later.")
            url = resp.url
        embed = discord.Embed(colour=user.colour)
        embed.set_image(url=url)
        embed.set_author(name=str(user), icon_url=user.avatar.url)
        await ctx.send(embed=embed)

    @commands.command(hidden=True)
    async def panda(self, ctx):
        """Gives you a random panda."""
        async with ctx.session.get("https://some-random-api.ml/animal/panda") as resp:
            if resp.status != 200:
                return await ctx.send("Could not find panda :(")
            js = await resp.json()

        await ctx.send(embed=discord.Embed(title="Random panda").set_image(url=js["image"]))

    async def do_ocr(self, url: str) -> Optional[str]:
        headers = {'Authorization': self.bot.config.tsu_token}
        async with self.bot.session.get('https://api.tsu.sh/google/ocr', headers=headers, params={'q': url}) as resp:
            if resp.status >= 400:
                error = await resp.text()
                raise OCRError(f'An error occurred: {error}')
            data = await resp.json()
        ocr_text = data.get('text')
        ocr_text = ocr_text if len(ocr_text) < 4000 else str(await self.bot.mb_client.post(ocr_text))
        return ocr_text

    @commands.command(hidden=True)
    async def ocr(self, ctx, *, image_url: str = None):
        if not image_url and not ctx.message.attachments:
            return await ctx.send('URL or attachment required.')
        image_url = image_url or ctx.message.attachments[0].url
        data = await self.do_ocr(image_url) or 'No text returned.'
        await ctx.send(embed=discord.Embed(title='OCR result', description=data, colour=discord.Colour.blurple()))

    @commands.command(hidden=True)
    async def ocrt(self, ctx, *, image=None):
        parser = Arguments(add_help=False, allow_abbrev=False)
        parser.add_argument('url', nargs='?', default=None)
        parser.add_argument('--source','-s', '--src', default='auto')
        parser.add_argument('--dest', '-d', default='en')
        args = parser.parse_args(shlex.split(image))
        image_url = args.url
        src = args.source
        dest = args.dest
        if not image_url and not ctx.message.attachments:
            return await ctx.send('URL or attachment required.')
        image_url = image_url or ctx.message.attachments[0].url
        data = await self.do_ocr(image_url)
        if data:
            if src.lower() not in googletrans.LANGUAGES and src.lower() not in googletrans.LANGCODES and src.lower() != 'auto':
                return await ctx.send('Invalid source language: {}'.format(src))
            if dest.lower() not in googletrans.LANGUAGES and dest.lower() not in googletrans.LANGCODES:
                return await ctx.send('Invalid destination language: {}'.format(dest))
            return await self.do_translate(ctx, message=data, from_=src.lower(), to=dest.lower())
        return await ctx.send('No text returned.')

    @ocr.error
    @ocrt.error
    async def ocr_error(self, ctx, error):
        if isinstance(error, OCRError):
            await ctx.send(error)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id in self.bot.blocklist or payload.user_id in self.bot.blocklist:
            return
        if payload.channel_id in self.noreact:
            return
        if payload.member is not None and payload.member.bot:
            return
        flag = str(payload.emoji)
        if flag not in languages.FLAG_TO_LANG:
            return
        message = discord.utils.find(lambda m: m.channel.id == payload.channel_id and m.id == payload.message_id,
                                     self.bot.cached_messages)
        if message is None:
            channel = self.bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)

        for reaction in message.reactions:
            if str(reaction.emoji) == flag:
                if reaction.count > 1:
                    return

        dest = languages.FLAG_TO_LANG[flag]
        loop = self.bot.loop
        try:
            ret = await loop.run_in_executor(None, self.trans.translate, message.clean_content, dest, 'auto')
        except Exception as e:
            return

        embed = discord.Embed(colour=0x4284F3)
        src = googletrans.LANGUAGES.get(ret.src, '(auto-detected)').title()
        dest = googletrans.LANGUAGES.get(ret.dest, 'Unknown').title()
        embed.title = f'Translation from {languages.LANG_TO_FLAG.get(ret.src, "")} `{src}` ' \
                      f'to {languages.LANG_TO_FLAG.get(ret.dest, "")} `{dest}`'
        embed.description = ret.text
        embed.set_author(name=f'{message.author} said:', icon_url=message.author.avatar.url)
        #if ret.pronunciation and ret.pronunciation != ret.text:
        #    embed.add_field(name='Pronunciation', value=ret.pronunciation)
        if payload.member is not None:
            embed.set_footer(text=f'Requested by {payload.member} | {payload.message_id}',
                             icon_url=payload.member.avatar.url)
        if message.guild is not None and message.channel.permissions_for(message.guild.me).send_messages:
            await message.channel.send(embed=embed)

    @commands.command()
    @checks.is_mod()
    @commands.guild_only()
    async def noreact(self, ctx, channel: discord.TextChannel = None):
        """Disable auto-translate on reaction add for this channel.

        Alternatively, you can revoke `Send Messages` permissions for the bot in this channel.
        """
        channel = channel or ctx.channel
        await self.noreact.put(channel.id, True)
        await ctx.send(ctx.tick(True))

    @commands.command()
    @checks.is_mod()
    @commands.guild_only()
    async def react(self, ctx, channel: discord.TextChannel = None):
        """Re enable auto-translate on reaction add for this channel."""
        channel = channel or ctx.channel
        try:
            await self.noreact.remove(channel.id)
        except KeyError:
            return await ctx.send('React to translate is not disabled for this channel.', delete_after=15.0)
        await ctx.send(ctx.tick(True))


    # Typeracer
    def _draw_words(self, text: str):
        """."""
        text = textwrap.fill(text, 25)
        font = ImageFont.truetype('data/fonts/W6.ttc', 60)
        padding = 50

        images = [Image.new('RGBA', (1, 1), color=0) for _ in range(2)]
        for index, (image, colour) in enumerate(zip(images, ((47, 49, 54), 'white'))):
            draw = ImageDraw.Draw(image)
            w, h  = draw.multiline_textsize(text, font=font)
            images[index] = image = image.resize((w + padding, h + padding))
            draw = ImageDraw.Draw(image)
            draw.multiline_text((padding / 2, padding / 2), text=text, fill=colour, font=font)
        background, foreground = images
        background = background.filter(ImageFilter.GaussianBlur(radius=7))
        background.paste(foreground, (0, 0), foreground)
        buf = io.BytesIO()
        background.save(buf, 'png')
        buf.seek(0)
        return buf

    def random_words(self, amount: int) -> List[str]:
        with open('data/words.txt', 'r') as fp:
            words = fp.readlines()

        return random.sample(words, amount)

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.channel)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=False)
    async def typeracer(self, ctx, amount: int = 5):
        """Type racing.

        This command will send an image of words of [amount] length.
        Please type and send this in the same channel to qualify.
        """

        amount = max(min(amount, 50), 1)

        await ctx.send('Type-racing begins in 5 seconds.')
        await asyncio.sleep(5)

        words = self.random_words(amount)
        randomised_words = (' '.join(words)).replace('\n', '').strip().lower()

        func = partial(self._draw_words, randomised_words)
        image = await ctx.bot.loop.run_in_executor(None, func)
        file = discord.File(fp=image, filename='typerace.png')
        await ctx.send(file=file)

        winners = dict()
        is_ended = asyncio.Event()

        start = time.time()

        def check(message: discord.Message):
            if (
                    message.channel == ctx.channel
                    and not message.author.bot
                    and message.content.lower() == randomised_words
                    and message.author not in winners
            ):
                winners[message.author] = time.time() - start
                is_ended.set()
                ctx.bot.loop.create_task(message.add_reaction(ctx.tick(True)))

        task = ctx.bot.loop.create_task(ctx.bot.wait_for('message', check=check))

        try:
            await asyncio.wait_for(is_ended.wait(), timeout=60)
        except asyncio.TimeoutError:
            await ctx.send('No participants matched the output.')
        else:
            await ctx.send('Input accepted... Other players have 10 seconds left.')
            await asyncio.sleep(10)
            embed = discord.Embed(title=f'{formats.plural(len(winners)):Winner}', colour=discord.Colour.random())
            embed.description = '\n'.join(
                f'{idx}: {person.mention} - {time:.4f} seconds for {amount / time * 60:.2f}WPM'
                for idx, (person, time) in enumerate(winners.items(), start=1)
            )
            await ctx.send(embed=embed)
        finally:
            task.cancel()


# Probably should've defined this earlier but I have exams now yeet
class OCRError(commands.CommandError):
    pass


def setup(bot):
    bot.add_cog(Funhouse(bot))
