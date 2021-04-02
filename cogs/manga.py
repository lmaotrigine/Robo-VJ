from __future__ import annotations

import datetime
import traceback
from collections import defaultdict
from dataclasses import dataclass
from time import struct_time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from bot import RoboVJ

import aiohttp
import discord
import feedparser
from discord.ext import commands, tasks

MANGADEX_RSS_BASE = 'https://mangadex.org/rss/follows/{}'
MANGADEX_API_BASE = 'https://mangadex.org/api/'
MANGADEX_BASE = 'https://mangadex.org'


@dataclass
class _MangadexManga:
    alt_names: List[str]
    artist: str
    author: str
    comments: int
    cover_url: str
    covers: List[str]
    demographic: int
    description: str
    follows: int
    genres: List[int]
    hentai: bool
    lang_flag: str
    lang_name: str
    last_chapter: str
    last_updated: int
    last_volume: int
    links: Dict[str, str]
    rating: Dict[str, str]
    related: List
    status: int
    title: str
    views: int
    status: str
    
    @property
    def updated(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.last_updated)


class MangadexAPIResponse:
    def __init__(self, payload: Dict):
        """Data response from the Mangadex API."""
        # private because not gonna use... yet
        self._chapters: Optional[Dict[str, Dict[str, Any]]] = payload.get('chapter')
        self.group: Optional[Dict[str, Dict[str, str]]] = payload.get('group')
        self.manga = _MangadexManga(**payload['manga'])
        self.status: Optional[str] = payload.get('status')

    @property
    def name(self) -> str:
        return self.manga.title

    @property
    def artist(self) -> str:
        return self.manga.artist

    @property
    def author(self) -> str:
        return self.manga.author

    @property
    def cover(self) -> str:
        return f'{MANGADEX_BASE}{self.manga.cover_url}'
    
    @property
    def alt_covers(self) -> List[str]:
        return [f'{MANGADEX_BASE}{alt_cover}' for alt_cover in self.manga.covers]

    @property
    def alt_names(self) -> List[str]:
        return self.manga.alt_names

    @property
    def hentai(self) -> bool:
        return bool(self.manga.hentai)

    @property
    def lang_name(self) -> str:
        return self.manga.lang_name

    @property
    def last_updated(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.manga.last_updated)


@dataclass
class MangadexRSSEntry:
    guidislink: bool
    id: str
    link: str
    links: List[Dict[str, str]]
    mangalink: str
    published: str
    published_parsed: struct_time
    summary: str
    summary_detail: Dict[str, Optional[str]]
    title: str
    title_detail: Dict[str, str]

    @property
    def manga_id(self) -> int:
        return int(self.id.rsplit('/', 1)[1])

    @property
    def published_at(self) -> datetime.datetime:
        return datetime.datetime.strptime(self.published, '%a, %d %b %Y %H:%M:%S %z')


class MangadexEmbed(discord.Embed):
    @classmethod
    def from_rss(cls, entry: MangadexRSSEntry) -> MangadexEmbed:
        """Return a custom Embed based on a Mangadex RSS entry."""
        embed = cls(colour=discord.Colour.blurple())
        embed.title = entry.title
        embed.description = entry.summary
        embed.url = entry.link
        embed.add_field(name='Manga URL', value=f'[Here]({entry.mangalink}/)')
        embed.timestamp = entry.published_at
        embed.set_footer(text=entry.manga_id)

        return embed

    @classmethod
    def from_api(cls, manga: str, entry: MangadexAPIResponse) -> MangadexEmbed:
        """Returns a custom Embed based on a Mangadex API entry."""

        alt_covers = ' | '.join([f'[{index}]({url})' for index, url in enumerate(entry.alt_covers, start=1)])
        embed = cls(colour=discord.Colour.blurple())
        embed.title = entry.name
        embed.url = f'https://mangadex.org/title/{manga}/'
        embed.set_author(name=entry.author)
        embed.set_image(url=entry.cover)
        embed.set_footer(text='Last Updated:')
        embed.timestamp = entry.last_updated
        embed.add_field(name='Artist', value=entry.artist or 'Not listed.')
        embed.add_field(name='Hentai', value=('Yes' if entry.hentai else 'No'))
        embed.add_field(name='Language of Origin', value=entry.lang_name.capitalize())
        embed.add_field(name='Alternate Names', value='\n'.join(entry.alt_names))
        embed.add_field(name='Alternate cover URLs', value=alt_covers or 'N/A')

        return embed


class Manga(commands.Cog):
    """."""

    def __init__(self, bot: RoboVJ):
        self.bot = bot
        self.rss_url = MANGADEX_RSS_BASE.format(bot.config.mangadex_key)
        self.rss_webhook = discord.Webhook.from_url(bot.config.mangadex_webhook,
                                                    adapter=discord.AsyncWebhookAdapter(bot.session))
        self._cache = defaultdict(set)
        self.rss_parser.start()

    @commands.command()
    async def mangadex(self, ctx: commands.Context, *, mangadex_id: int):
        """Return details, images, and links to a Mangadex entry."""
        try:
            response = await self.bot.session.get(f'{MANGADEX_API_BASE}manga/{mangadex_id}')
            data = await response.json()
        except Exception as exc:  # TODO: get real exc
            raise commands.BadArgument('Provided Mangadex ID is invalid.') from exc

        if response.status != 200:
            raise commands.BadArgument('Provided Mangadex ID is invalid.')

        mangadex_entry = MangadexAPIResponse(data)
        embed = MangadexEmbed.from_api(mangadex_id, mangadex_entry)
        await ctx.send(embed=embed)

    @tasks.loop(minutes=30)
    async def rss_parser(self):
        """."""
        async with self.bot.session.get(self.rss_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            text = await resp.text()

        rss_data: Dict[str, List] = feedparser.parse(text)
        entries_data: List[Dict] = rss_data['entries']

        for entry in entries_data:
            mangadex_entry = MangadexRSSEntry(**entry)
            manga_td = datetime.datetime.now().replace(tzinfo=datetime.timezone.utc) - mangadex_entry.published_at

            if manga_td.total_seconds() < 2700:
                if mangadex_entry.manga_id in self._cache[mangadex_entry.title]:
                    return
                embed = MangadexEmbed.from_rss(mangadex_entry)
                await self.rss_webhook.send(embed=embed)
                self._cache[mangadex_entry.title].add(mangadex_entry.manga_id)

    @rss_parser.before_loop
    async def before_rss_parser(self):
        """."""
        await self.bot.wait_until_ready()

    @rss_parser.error
    async def rss_parser_error(self, error):
        tb_str = ''.join(traceback.format_exception(type(error), error, error.__traceback__, 4))
        stats = self.bot.get_cog('Stats')
        if stats:
            await stats.webhook.send(f'```py\n{tb_str}\n```')

    def cog_unload(self):
        self.rss_parser.cancel()


def setup(bot: RoboVJ):
    bot.add_cog(Manga(bot))
