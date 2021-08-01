from __future__ import annotations

import asyncio
import csv
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from functools import partial
from io import BytesIO
from textwrap import fill
from typing import Any, IO, TYPE_CHECKING, Dict, List, Optional, Tuple, Union
from urllib.parse import quote

import aiohttp
import bs4
import discord
import pykakasi
from discord.ext import commands, menus
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from .utils.context import Context
from .utils.formats import plural, to_codeblock
from .utils.paginator import RoboPages

if TYPE_CHECKING:
    from bot import RoboVJ

BASE_URL = 'https://kanjiapi.dev/v1'
HIRAGANA = 'あいうえおかきくけこがぎぐげごさしすせそざじずぜぞたちつてとだぢづでどなにぬねのはひふへほばびぶべぼぱぴぷぺぽまみむめもやゆよらりるれろわを'
KATAKANA = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポ'
JISHO_WORDS_URL = 'https://jisho.org/api/v1/search/words'
JISHO_KANJI_URL = 'https://jisho.org/api/v1/search/{}%23kanji'
JISHO_REPLACEMENTS = {
    'english_definitions': 'Definitions',
    'parts_of_Speech': 'Type',
    'tags': 'Notes',
    'see_also': 'See Also',
}


class MemeDict(dict):
    def __getitem__(self, k: str) -> Any:
        for key in self:
            if k in key:
                return super().__getitem__(key)
        raise KeyError(k)


JLPT_N1 = list(csv.reader(open('data/jlpt_decks/n1.csv', 'r', encoding='utf-8')))
JLPT_N2 = list(csv.reader(open('data/jlpt_decks/n2.csv', 'r', encoding='utf-8')))
JLPT_N3 = list(csv.reader(open('data/jlpt_decks/n3.csv', 'r', encoding='utf-8')))
JLPT_N4 = list(csv.reader(open('data/jlpt_decks/n4.csv', 'r', encoding='utf-8')))
JLPT_N5 = list(csv.reader(open('data/jlpt_decks/n5.csv', 'r', encoding='utf-8')))
JLPT_LOOKUP = MemeDict(
    {
        ('n1', 'n 1', '1', '1 '): JLPT_N1,
        ('n2', 'n 2', '2', '2 '): JLPT_N2,
        ('n3', 'n 3', '3', '3 '): JLPT_N3,
        ('n4', 'n 4', '4', '4 '): JLPT_N4,
        ('n5', 'n 5', '5', '5 '): JLPT_N5,
    }
)


class JLPTConverter(commands.Converter):
    async def convert(self, ctx, argument) -> IO:
        try:
            return JLPT_LOOKUP[argument.lower()]
        except KeyError:
            raise commands.BadArgument('Invalid key for JLPT level.')


def _create_kaaksi() -> pykakasi.kakasi:
    kakasi = pykakasi.kakasi()
    kakasi.setMode('H', 'a')
    kakasi.setMode('K', 'a')
    kakasi.setMode('J', 'a')
    kakasi.setMode('s', True)
    return kakasi.getConverter()


@dataclass
class KanjiPayload:
    kanji: str
    grade: int
    stroke_count: int
    meanings: List[str]
    kun_readings: List[str]
    on_readings: List[str]
    name_readings: List[str]
    jlpt: int
    unicode: str
    heisig_en: str


@dataclass
class WordsPayload:
    vaiants: List[Dict[str, Union[str, List[str]]]]
    meanings: List[Dict[str, List[str]]]


@dataclass
class JishoPayload:
    attribution: Dict[str, Union[str, bool]]
    japanese: List[Dict[str, str]]
    jlpt: List[str]
    senses: List[Dict[str, List[Union[str, Dict[str, str]]]]]
    slug: str
    tags: List[str]
    is_common: bool = False


def word_to_reading(stuff: List[Dict[str, str]]) -> List[str]:
    ret = []
    for item in stuff:
        if item.get('word'):
            hmm = f'{item["word"]} 【{item["reading"]}】' if item.get('reading') else f'{item["word"]}'
            ret.append(hmm)
    return ret


def kanji_in_response(kanji: str, soup: bs4.BeautifulSoup) -> bool:
    segment = f'<h1 class="character" data-area-name="print" lang="ja">{kanji}</h1>'
    if segment in soup.find('h1', class_='character'):
        return True
    return False


def parse_response(raw_html: str) -> bs4.BeautifulSoup:
    soup = bs4.BeautifulSoup(raw_html, 'html.parser')
    return soup


class JishoKanji:
    def __init__(self, kanji: str, data: bs4.BeautifulSoup, url: str):
        self.kanji = kanji
        self.data = data
        self.url = url
        
    @property
    def taught_in(self) -> str:
        grade = self.data.find('div', class_='grade').select('strong')[0].text
        return grade.title()

    @property
    def jlpt_level(self) -> Optional[str]:
        raw = self.data.find('div', class_='jlpt')
        if raw is None:
            return None

        level = raw.select('strong')[0].text
        return level.title()

    @property
    def stroke_count(self) -> Optional[str]:
        raw = self.data.find('div', class_='kanji-details__stroke_count')
        if raw is None:
            return None
        count = raw.select('strong')[0].text
        return f'{plural(int(count)):Stroke}'
    
    @property
    def stroke_url(self) -> str:
        return f'https://raw.githubusercontent.com/mistval/kanji_images/master/gifs/{ord(self.kanji):x}.gif?v=1'
    
    @property
    def meanings(self) -> str:
        raw = self.data.find('div', class_='kanji-details__main_meanings').text
        return raw.strip()

    @property
    def newspaper_frequency(self) -> Optional[str]:
        raw = self.data.find('div', class_='frequency')
        if raw is None:
            return None
        raw = raw.select('strong')[0].text
        return f'{raw} of 2500 most used Kanji in newspapers.'

    def reading_compounds(self, key: str) -> Optional[List[str]]:
        raw = self.data.find('div', class_='row compounds')
        if raw is None:
            return None

        fmt = defaultdict(list)

        for x in raw:
            if isinstance(x, bs4.NavigableString):
                continue
            if hmm := x.select('h2'):
                if hmm[0].text == 'On reading compounds':
                    fmt['On'] = [item.text.strip() for item in x.select('ul')]
                if hmm[0].text == 'Kun reading compounds':
                    fmt['Kun'] = [item.text.strip() for item in x.select('ul')]

        return fmt[key]

    def symbols(self, key: str) -> List[Tuple[str, ...]]:
        raw = self.data.find('div', class_='kanji-details__main-readings')\
            .find('dl', class_=f'dictionary_entry {key}_yomi')\
            .select('dd', class_='kanji-details__main-readings')[0]
        fmt = []
        for item in raw:
            if isinstance(item, bs4.element.Tag):
                text = item.text
                link = f'https://{item.get("href").lstrip("//")}'
                fmt.append((text, link))

        return fmt

    @property
    def on_readings(self) -> Optional[List[str]]:
        readings = self.reading_compounds('On')
        if readings == []:
            return None
        return readings
    
    @property
    def on_symbols(self) -> List[Tuple[str, ...]]:
        return self.symbols('on')

    @property
    def kun_readings(self) -> Optional[List[str]]:
        readings = self.reading_compounds('Kun')
        if readings == []:
            return None
        return readings

    @property
    def kun_symbols(self) -> List[Tuple[str, ...]]:
        return self.symbols('kun')

    @property
    def radical(self) -> Optional[List[str]]:
        raw = self.data.find('div', class_='radicals')
        if raw is None:
            return None
        return raw.find('span').text.strip().rsplit()[:2]


class KanjiAPISource(menus.ListPageSource):
    def __init__(self, data):
        self.data = data
        super().__init__(data, per_page=1)

    async def format_page(self, menu, page):
        return page


class KanjiEmbed(discord.Embed):
    @classmethod
    def from_kanji(cls, payload: KanjiPayload) -> KanjiEmbed:
        embed = cls(title=payload.kanji, colour=0xbf51b2)
        embed.add_field(name='(School) Grade Learned:', value=f'__**{payload.grade}**__')
        embed.add_field(name='Stroke Count:', value=f'__**{payload.stroke_count}**__')
        embed.add_field(name='Kun Readings', value='\n'.join(payload.kun_readings) or 'N/A')
        embed.add_field(name='On Readings', value='\n'.join(payload.on_readings) or 'N/A')
        embed.add_field(name='Name Readings', value='\n'.join(payload.name_readings) or 'N/A')
        embed.add_field(name='Unicode', value=payload.unicode)
        embed.description = to_codeblock('\n'.join(payload.meanings) or 'N/A', language='')
        embed.set_footer(text=f'JLPT Grade: {payload.jlpt or "N/A"}')
        return embed

    @classmethod
    def from_words(cls, character: str, payload: WordsPayload) -> List[KanjiEmbed]:
        embeds = []
        variants = payload.vaiants
        meanings = payload.meanings[0]
        for variant in variants:
            embed = cls(title=character, colour=0x4AFAFC)
            embed.add_field(name='Written:', value=variant['written'])
            embed.add_field(name='Pronounced:', value=variant['pronounced'])
            priorities = to_codeblock(''.join(variant['priorities']), language='') if variant['priorities'] else 'N/A'
            embed.add_field(name='Priorities:', value=priorities)
            for _ in range(3):
                embed.add_field(name='\u200b', value='\u200b')
            meaning = '\n'.join(meanings['glosses']) or 'N/A'
            embed.add_field(name='Kanji Meaning(s):', value=meaning)
            embeds.append(embed)
        return embeds

    @classmethod
    def from_jisho(cls, query: str, payload: JishoPayload) -> KanjiEmbed:
        embed = cls(title=f'Jisho data on {query}.', colour=0x4AFAFC)

        attributions = []
        for key, value in payload.attribution.items():
            if value in (True, False):
                attributions.append(key.title())
            elif value:
                attributions.append(f'{key.title()}: {value}')

        if attributions:
            attributions_cb = to_codeblock('\n'.join(attributions), language='prolog', escape_md=False)
            embed.add_field(name='Attributions', value=attributions_cb, inline=False)

        jp = word_to_reading(payload.japanese)

        japanese = '\n\n'.join(jp)
        embed.add_field(name='Writing 【Reading】', value=to_codeblock(japanese, language='prolog', escape_md=False),
                        inline=False)

        sense: Dict[str, List[Union[str, Dict[str, str]]]] = payload.senses[0]
        senses = ''
        links = ''
        embed.description = ''
        for key, value in sense.items():
            if key == 'links':
                if value:
                    subdict = value[0]
                    links += f'[{subdict.get("text")}]({subdict.get("url")})\n'
                else:
                    continue
            else:
                if value:
                    senses += f'{JISHO_REPLACEMENTS.get(key, key).title()}: {", ".join(value)}\n'

        if senses:
            embed.description += to_codeblock(senses, language='prolog', escape_md=False)

        if links:
            embed.description += links

        embed.add_field(name='Is it common?', value='Yes' if payload.is_common else 'No', inline=False)

        if payload.jlpt:
            embed.add_field(name='JLPT Level', value=payload.jlpt[0], inline=False)

        embed.set_footer(text=f'Slug: {payload.slug}')

        return embed


class Nihongo(commands.Cog):
    """The description for Nihongo goes here."""

    def __init__(self, bot: RoboVJ):
        self.bot = bot
        self.converter = _create_kaaksi()

    @commands.command()
    async def romaji(self, ctx, *, text: commands.clean_content):
        """Sends the Romaji version of the passed Kana."""
        ret = await self.bot.loop.run_in_executor(None, self.converter.do, text)
        await ctx.send(ret)

    @commands.group(name='kanji', aliases=['かんじ', '漢字'], invoke_without_command=True)
    async def kanji(self, ctx, character: str):
        """Return data on a single Kanji from the KanjiDev API."""
        if len(character) > 1:
            raise commands.BadArgument('Only one Kanji please.')
        url = f'{BASE_URL}/kanji/{character}'

        async with self.bot.session.get(url) as resp:
            data = await resp.json()

        kanji_data = KanjiPayload(**data)
        embed = KanjiEmbed.from_kanji(kanji_data)
        menu = RoboPages(KanjiAPISource([embed]))
        await menu.start(ctx)

    @kanji.command(name='words')
    async def kanji_words(self, ctx, character: str):
        """Return the words a Kanji is used in, or in conjunction with."""
        if len(character) > 1:
            raise commands.BadArgument('Only one Kanji please.')
        url = f'{BASE_URL}/words/{character}'

        async with self.bot.session.get(url) as resp:
            data =await resp.json()

        words_data = [WordsPayload(**payload) for payload in data]
        embeds = [KanjiEmbed.from_words(character, kanji) for kanji in words_data]
        real_embeds = [embed for sublist in embeds for embed in sublist]

        fixed_embeds = [
            embed.set_footer(
                text=f'{real_embeds.index(embed) + 1}/{len(real_embeds)}' if not embed.footer.text else
                f'{embed.footer.text} :: {real_embeds.index(embed) + 1}/{len(real_embeds)}'
            )
            for embed in real_embeds
        ]

        menu = RoboPages(KanjiAPISource(fixed_embeds), delete_message_after=False, clear_reactions_after=False)
        await menu.start(ctx)

    @kanji.error
    @kanji_words.error
    async def nihongo_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, aiohttp.ContentTypeError):
            return await ctx.send('You appear ot have passed an invalid *kanji*.')

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)

    @commands.command()
    async def jisho(self, ctx, *, query: str):
        """Query the Jisho API with your kanji/word."""
        async with self.bot.session.get(JISHO_WORDS_URL, params={'keyword': query}) as resp:
            if resp.status == 200:
                data = (await resp.json())['data']
            else:
                data = []
            if not data:
                raise commands.BadArgument('Not a valid query for Jisho.')

            jisho_data = [JishoPayload(**payload) for payload in data]
            embeds = [KanjiEmbed.from_jisho(query, item) for item in jisho_data]
            fixed_embeds = [
                embed.set_footer(text=f'{embed.footer.text} :: {embeds.index(embed) + 1}/{len(embeds)}'
                                 if embed.footer.text else f'{embeds.index(embed) + 1}/{len(embeds)}')
                for embed in embeds
            ]

            menu = RoboPages(KanjiAPISource(fixed_embeds), delete_message_after=False, clear_reactions_after=False)
            await menu.start(ctx)

    def _draw_kana(self, text: str) -> BytesIO:
        """."""
        # font = ImageFont.truetype("static/Hiragino-Sans-GB.ttc", 60)
        text = fill(text, 25, replace_whitespace=False)
        font = ImageFont.truetype('data/fonts/W6.ttc', 60)
        padding = 50

        images = [Image.new('RGBA', (1, 1), color=0) for _ in range(2)]
        for index, (image, colour) in enumerate(zip(images, ((47, 49, 54), 'white'))):
            draw = ImageDraw.Draw(image)
            w, h = draw.multiline_textsize(text, font=font)
            images[index] = image = image.resize((w + padding, h + padding))
            draw = ImageDraw.Draw(image)
            draw.multiline_text((padding / 2, padding / 2), text=text, fill=colour, font=font)
        background, foreground = images

        background = background.filter(ImageFilter.GaussianBlur(radius=7))
        background.paste(foreground, (0, 0), foreground)
        buf = BytesIO()
        background.save(buf, 'png')
        buf.seek(0)
        return buf

    @commands.command()
    async def kana(self, ctx, *, text: str):
        func = partial(self._draw_kana, text)
        img = await self.bot.loop.run_in_executor(None, func)
        file = discord.File(fp=img, filename='kana.png')
        await ctx.send(file=file)

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def kanarace(self, ctx, amount: int = 10, kana: Optional[str] = 'h'):
        """Kana racing.

        This command will send an image of a string of Kana of [amount] length.
        Please type and send this Kana in the same channel to qualify.
        """

        if kana not in ('h', 'k'):
            kana = 'k'

        chars = HIRAGANA if kana == 'h' else KATAKANA

        amount = max(min(amount, 50), 5)

        await ctx.send('Kana-racing begins in 5 seconds.')
        await asyncio.sleep(5)

        randomised_kana = ''.join(random.choices(chars, k=amount))

        func = partial(self._draw_kana, randomised_kana)
        image = await self.bot.loop.run_in_executor(None, func)
        file = discord.File(fp=image, filename='kanarace.png')
        await ctx.send(file=file)

        winners = dict()
        is_ended = asyncio.Event()

        start = time.time()

        def check(message: discord.Message):
            if message.channel == ctx.channel and message.content.lower() == randomised_kana and \
                message.author not in winners:
                winners[message.author] = time.time() - start
                is_ended.set()
                self.bot.create_task(message.add_reaction(ctx.tick(True)))

        task = self.bot.loop.create_task(self.bot.wait_for('message', check=check))

        try:
            await asyncio.wait_for(is_ended.wait(), timeout=60)
        except asyncio.TimeoutError:
            await ctx.send('No participants matched the output.')
        else:
            await ctx.send('Word accepted... Other players have 10 seconds left.')
            await asyncio.sleep(10)
            embed = discord.Embed(title=f'{plural(len(winners)):Winner}', colour=discord.Colour.random())
            embed.description = '\n'.join(f'{idx}: {person.mention} - {time:.4f} seconds for {amount / time * 5:.2f}CPM'
                                          for idx, (person, time) in enumerate(winners.items(), start=1))
            await ctx.send(embed=embed)
        finally:
            task.cancel()

    @kanarace.error
    async def race_error(self, ctx, error):
        if isinstance(error, asyncio.TimeoutError):
            return await ctx.send('Kanarace has no winners!', delete_after=5.0)

    @commands.command(usage='[level=n5]')
    async def jlpt(self, ctx, level: JLPTConverter = JLPT_N5):
        word, reading, meaning, _ = random.choice(level)
        embed = discord.Embed(title=word, description=meaning, colour=discord.Colour.random())
        embed.add_field(name='Reading', value=f'『{reading}』')
        await ctx.send(embed=embed)

    def _gen_kanji_embed(self, payloads: List[JishoKanji]) -> List[discord.Embed]:
        returns = []
        for data in payloads:
            stroke = discord.Embed(title=data.kanji, url=data.url)
            stroke.set_image(url=data.stroke_url)
            strokes = data.stroke_count or 'Not a Kanji'
            stroke.add_field(name='Stroke Count', value=strokes)
            stroke.add_field(name='JLPT Level', value=data.jlpt_level)
            if data.radical:
                stroke.add_field(name='Radical', value=f'({data.radical[1]}) {data.radical[0]}')
            returns.append(stroke)

            # if data.on_symbols:
            #     on_embed = discord.Embed(title=data.kanji, url=data.url)
            #     on_sym = "\n".join(
            #         f"[{item[0]}]({item[1]})" for item in data.on_symbols
            #     )
            #     on_embed.add_field(name="On symbols", value=on_sym)
            #     if data.on_readings:
            #         on = "\n".join(data.on_readings)
            #         on_embed.add_field(
            #             name="On readings",
            #             value=to_codeblock(
            #                 f"{textwrap.dedent(on)}", language="", escape_md=False
            #             ),
            #             inline=False,
            #         )
            #     returns.append(on_embed)
            # if data.kun_symbols:
            #     kun_embed = discord.Embed(title=data.kanji, url=data.url)
            #     kun_sym = "\n".join(
            #         f"[{item[0]}]({item[1]})" for item in data.kun_symbols
            #     )
            #     kun_embed.add_field(name="Kun symbols", value=kun_sym)
            #     if data.kun_readings:
            #         kun = "\n".join(data.kun_readings)
            #         kun_embed.add_field(
            #             name="Kun readings",
            #             value=to_codeblock(
            #                 f"{textwrap.dedent(kun)}", language="", escape_md=False
            #             ),
            #             inline=False,
            #         )
            #     returns.append(kun_embed)

        return returns

    @commands.command(name='strokeorder', aliases=['so'])
    async def stroke_order(self, ctx, kanji: str):
        responses = []
        for char in kanji:
            url = quote(f'https://jisho.org/search/{char}#kanji', safe='/:?&')
            data = await self.bot.session.get(url)
            soup = bs4.BeautifulSoup(await data.content.read(), 'html.parser')
            response = JishoKanji(char, soup, url)
            responses.append(response)

        embeds = self._gen_kanji_embed(responses)
        source = KanjiAPISource(embeds)
        menu = RoboPages(source=source)
        await menu.start(ctx)


def setup(bot):
    bot.add_cog(Nihongo(bot))
