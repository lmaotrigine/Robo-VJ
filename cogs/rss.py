import discord
from discord.ext import commands, tasks

import asyncio
import datetime
import functools
import html
import io
import logging
import re
import sys
import time
import textwrap
import traceback
import urllib.parse

import aiohttp
from bs4 import BeautifulSoup
import dateutil.parser
import dateutil.tz
import feedparser
import pytz

from .utils import db, checks


log = logging.getLogger(__name__)


class RSSFeeds(db.Table, table_name='rss.feeds'):
    channel_id = db.Column(db.Integer(big=True), primary_key=True)
    feed = db.Column(db.String, primary_key=True)
    last_checked = db.Column(db.Time(timezone=True))
    ttl = db.Column(db.Integer)


class RSSEntries(db.Table, table_name='rss.entries'):
    entry = db.Column(db.String, primary_key=True)
    feed = db.Column(db.String, primary_key=True)


class RSSErrors(db.Table, table_name='rss.errors'):
    timestamp = db.Column(db.Time(timezone=True), primary_key=True)
    feed = db.Column(db.String)
    type = db.Column(db.String)
    message = db.Column(db.String)


class RSS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Generate tzinfos
        self.tzinfos = {}
        for timezone_abbreviation in ('EDT', 'EST'):
            matching_timezones = list(filter(
                lambda t: datetime.datetime.now(pytz.timezone(t)).strftime('%Z') == timezone_abbreviation,
                pytz.common_timezones
            ))
            matching_utc_offsets = set(datetime.datetime.now(pytz.timezone(t)).strftime('%z') for t in matching_timezones)
            if len(matching_utc_offsets) == 1:
                self.tzinfos[timezone_abbreviation] = dateutil.tz.gettz(matching_timezones[0])

        self.new_feed = asyncio.Event()

        self.check_feeds.start().set_name('RSS')

    async def cog_unload(self):
        self.check_feeds.cancel()

    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def rss(self, ctx):
        """RSS"""
        await ctx.send_help(ctx.command)

    @rss.command()
    @checks.is_mod()
    async def add(self, ctx, url: str):
        """Add a feed to a channel."""
        query = """SELECT EXISTS (
                       SELECT FROM rss.feeds 
                       WHERE channel_id = $1 AND feed = $2
                    );
                """
        following = await ctx.db.fetchval(query, ctx.channel.id, url)
        if following:
            return await ctx.send(embed=discord.Embed(
                description=f'{ctx.tick(False)} This channel is already following that feed.')
            )
        async with ctx.bot.session.get(url) as resp:
            feed_text = await resp.text()
        # TODO: Handle issues getting the URL
        partial = functools.partial(feedparser.parse, io.BytesIO(feed_text.encode('UTF-8')),
                                    response_headers={'Content-Location': url})
        feed_info = await self.bot.loop.run_in_executor(None, partial)
        # Still necessary to run in executor?
        # TODO: Handle if feed is already being followed elsewhere
        ttl = None
        if 'ttl' in feed_info.feed:
            ttl = int(feed_info.feed.ttl)
        query = "INSERT INTO rss.entries (entry, feed) VALUES ($1, $2) ON CONFLICT (entry, feed) DO NOTHING;"
        for entry in feed_info.entries:
            await ctx.db.execute(query, entry.id, url)

        query = "INSERT INTO rss.feeds (channel_id, feed, last_checked, ttl) VALUES ($1, $2, NOW(), $3);"
        await ctx.db.execute(query, ctx.channel.id, url, ttl)
        await ctx.send(embed=discord.Embed(description=f'The feed, {url}, has been added to this channel.'))
        self.new_feed.set()

    @rss.command(aliases=['delete'])
    @checks.is_mod()
    async def remove(self, ctx, url: str):
        """Remove a feed from a channel."""
        query = "DELETE FROM rss.feeds WHERE channel_id = $1 AND feed = $2;"
        stat = await ctx.db.execute(query, ctx.channel.id, url)
        if stat == 'DELETE 0':
            return await ctx.send(embed=discord.Embed(
                description=f'{ctx.tick(False)} This channel isn\'t following that feed.'
            ))
        await ctx.send(embed=discord.Embed(description=f'The feed, {url}, has been removed from this channel.'))

    @rss.command(aliases=['feed'])
    async def feeds(self, ctx):
        """List feeds being followed in this channel."""
        records = await ctx.db.fetch('SELECT feed FROM rss.feeds WHERE channel_id = $1;', ctx.channel.id)
        await ctx.send(embed=discord.Embed(
            title='RSS feeds being followed in this channel',
            description='\n'.join(record['feed'] for record in records)
        ))

    # R/PT60S
    @tasks.loop(seconds=60)
    async def check_feeds(self):
        query = "SELECT DISTINCT ON (feed) feed, last_checked, ttl FROM rss.feeds ORDER BY feed, last_checked;"
        records = await self.bot.pool.fetch(query)

        if not records:
            self.new_feed.clear()
            await self.new_feed.wait()

        for record in records:
            feed = record['feed']

            if record['ttl'] and \
                datetime.datetime.now(datetime.timezone.utc) < (
                    record['last_checked'] + datetime.timedelta(minutes=record['ttl'])
            ):
                continue

            try:
                async with self.bot.session.get(feed) as resp:
                    feed_text = await resp.text()
                partial = functools.partial(feedparser.parse, io.BytesIO(feed_text.encode('UTF-8')),
                                            response_headers={'Content-Location': feed})
                feed_info = await self.bot.loop.run_in_executor(None, partial)
                # Still necessary to run in executor?

                ttl = None
                if 'ttl' in feed_info.feed:
                    ttl = int(feed_info.feed.ttl)
                await self.bot.pool.execute("UPDATE rss.feeds SET last_checked = NOW(), ttl = $1 WHERE feed = $2;",
                                            ttl, feed)
                for entry in feed_info.entries:
                    if 'id' not in entry:
                        continue
                    inserted = await self.bot.pool.fetchrow(
                        "INSERT INTO rss.entries (entry, feed) VALUES ($1, $2) ON CONFLICT DO NOTHING RETURNING *;",
                        entry.id, feed
                    )
                    if not inserted:
                        continue
                    # Get timestamp
                    ## if 'published_parsed in entry:
                    ##  timestamp = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    ### inaccurate
                    if 'published' in entry and entry.published:
                        timestamp = dateutil.parser.parse(entry.published, tzinfos=self.tzinfos)
                    elif 'updated' in entry:  # and entry.updated necessary? check updated first?
                        timestamp = dateutil.parser.parse(entry.updated, tzinfos=self.tzinfos)
                    else:
                        timestamp = discord.Embed.Empty

                    # Get and set description, title, url + set timestamp
                    if not (description := entry.get('summary')) and 'content' in entry:
                        description = entry['content'][0].get('value')
                    if description:
                        description = BeautifulSoup(description, 'lxml').get_text(separator='\n')
                        description = re.sub(r'\n\s*\n', '\n', description)
                        if len(description) > 2048:
                            space_index = description.rfind(' ', 0, 2048 - 3)
                            description = description[:space_index] + '...'
                    title = textwrap.shorten(entry.get('title'), width=256, placeholder='...')
                    embed = discord.Embed(title=html.unescape(title), url=entry.link, description=description,
                                          timestamp=timestamp, colour=0xFA9B39)

                    # Get and set thumbnail URL
                    thumbnail_url = (
                        (media_thumbnail := entry.get('media_thumbnail')) and media_thumbnail[0].get('url') or
                        (
                            (media_content := entry.get('media_content')) and
                            (media_image := discord.utils.find(lambda c: 'image' in c.get('medium', ''), media_content))
                            and media_image.get('url')
                        ) or
                        (
                            (links := entry.get('links')) and
                            (image_link := discord.utils.find(lambda l: 'image' in l.get('type', ''), links)) and
                            image_link.get('href')
                        ) or
                        (
                            (content := entry.get('content')) and (content_value := content[0].get('value')) and
                            (content_img := getattr(BeautifulSoup(content_value, 'lxml'), 'img')) and
                            content_img.get('src')
                        ) or
                        (
                            (media_content := entry.get('media_content')) and
                            (media_content := discord.utils.find(lambda c: 'url' in c, media_content)) and
                            media_content['url']
                        ) or
                        (
                            (description := entry.get('description')) and
                            (description_img := getattr(BeautifulSoup(description, 'lxml'), 'img')) and
                            description_img.get('src')
                        )
                    )
                    if thumbnail_url:
                        if not urllib.parse.urlparse(thumbnail_url).netloc:
                            thumbnail_url = feed_info.feed.link + thumbnail_url
                        embed.set_thumbnail(url=thumbnail_url)

                    # Get and set footer icon URL
                    footer_icon_url = (
                        feed_info.feed.get('icon') or feed_info.feed.get('logo') or
                        (feed_image := feed_info.feed.get('image')) and feed_image.get('href') or
                        (
                            (parsed_image := BeautifulSoup(feed_text, 'lxml').image) and
                            next(iter(parsed_image.attrs.values()), None) or discord.Embed.Empty
                        )
                    )
                    embed.set_footer(text=feed_info.feed.get('title', feed), icon_url=footer_icon_url)

                    # Send embed(s)
                    channel_records = await self.bot.pool.fetch("SELECT channel_id FROM rss.feeds WHERE feed = $1;",
                                                                feed)
                    for record in channel_records:
                        if text_channel := self.bot.get_channel(record['channel_id']):
                            try:
                                await text_channel.send(embed=embed)
                            except discord.Forbidden:
                                pass
                            except discord.HTTPException as e:
                                if e.status == 400 and e.code == 50035:
                                    if 'In embed.url: Not a well formed URL.' in e.text:
                                        embed.url = discord.Embed.Empty
                                    if ('In embed.thumbnail.url: Not a well formed URL.' in e.text or
                                        ('In embed.thumbnail.url: Scheme' in e.text and
                                            "is not supported. Scheme must be one of ('http', 'https')." in e.text)):
                                        embed.set_thumbnail(url='')
                                    if ('In embed.footer.icon_url: Not a well formed URL.' in e.text or
                                        ('In embed.footer.icon_url: Scheme' in e.text and
                                             "is not supported. Scheme must be one of ('http', 'https')." in e.text)):
                                        embed.set_footer(text=feed_info.feed.get('title', feed))
                                    await text_channel.send(embed=embed)
                                else:
                                    raise
                        # TODO: Remove text channel data if now non-existent
            except (aiohttp.ClientConnectionError, aiohttp.ClientPayloadError,
                    aiohttp.TooManyRedirects, asyncio.TimeoutError,
                    UnicodeDecodeError) as e:
                await self.bot.pool.execute("INSERT INTO rss.errors (feed, type, message) VALUES ($1, $2, $3);",
                                            feed, type(e).__name__, str(e))
                # Print error?
                await asyncio.sleep(10)
                # TODO: Add a variable for sleep time
                # TODO: Remove persistently erroring feed or exponentially backoff?
            except discord.DiscordServerError as e:
                log.exception(f'RSS Task Discord Server Error: {e}')
                await asyncio.sleep(60)
            #except Exception as e:
            #    print('Exception in RSS task')
            #    traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            #    log.error('Uncaught RSS task exception\n', exc_info=(type(e), e, e.__traceback__))
            #    print(f' (feed: {feed})')
            #    await asyncio.sleep(60)

    @check_feeds.before_loop
    async def before_check_feeds(self):
        await self.bot.wait_until_ready()

    @check_feeds.after_loop
    async def after_check_feeds(self):
        print('RSS task cancelled.')


async def setup(bot):
    await bot.add_cog(RSS(bot))
