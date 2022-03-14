import datetime

import discord
from discord.ext import commands

import asyncio
import functools
import html
import logging
import sys
import traceback
import tweepy
import urllib3

from .utils import checks, db

class Twitter(db.Table):
    channel_id = db.Column(db.Integer(big=True), primary_key=True)
    handle = db.Column(db.String, primary_key=True)
    replies = db.Column(db.Boolean)
    retweets = db.Column(db.Boolean)

log = logging.getLogger(__name__)

class TwitterStreamListener(tweepy.StreamListener):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.stream = None
        self.feeds = {}
        self.unique_feeds = set()
        self.reconnect_ready = asyncio.Event()
        self.reconnect_ready.set()
        self.reconnecting = False

    def __del__(self):
        if self.stream:
            self.stream.disconnect()

    async def start_feeds(self, *, feeds=None):
        if self.reconnecting:
            return await self.reconnect_ready.wait()
        self.reconnecting = True
        await self.reconnect_ready.wait()
        self.reconnect_ready.clear()
        if feeds:
            self.feeds = feeds
            self.unique_feeds = set(id for feeds in self.feeds.values() for id in feeds)
        if self.stream:
            self.stream.disconnect()
        self.stream = tweepy.Stream(auth=self.bot.twitter_api.auth, listener=self)
        if self.feeds:
            self.stream.filter(follow=self.unique_feeds, is_async=True)
        self.bot.loop.call_later(120, self.reconnect_ready.set)
        self.reconnecting = False

    async def add_feed(self, channel, handle):
        user_id = self.bot.twitter_api.get_user(handle).id_str
        self.feeds[channel.id] = self.feeds.get(channel.id, []) + [user_id]
        if user_id not in self.unique_feeds:
            self.unique_feeds.add(user_id)
            await self.start_feeds()

    async def remove_feed(self, channel, handle):
        self.feeds[channel.id].remove(self.bot.twitter_api.get_user(handle).id_str)
        self.unique_feeds = set(id for feeds in self.feeds.values() for id in feeds)
        await self.start_feeds()

    def on_status(self, status):
        if status.in_reply_to_status_id:
            # ignore replies
            return
        if status.user.id_str in self.unique_feeds:
            # TODO: Settings for including replies, retweets, etc.
            for channel_id, channel_feeds in self.feeds.items():
                if status.user.id_str in channel_feeds:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        if hasattr(status, "extended_tweet"):
                            text = status.extended_tweet["full_text"]
                            entities = status.extended_tweet["entities"]
                            extended_entities = status.extended_tweet.get("extended_entities")
                        else:
                            text = status.text
                            entities = status.entities
                            extended_entities = getattr(status, "extended_entities", None)
                        embed = discord.Embed(title=f'@{status.user.screen_name}', url=f'https://twitter.com/{status.user.screen_name}/status/{status.id}',
                                              description=self.bot.cogs["Twitter"].process_tweet_text(text, entities), timestamp=status.created_at.replace(tzinfo=datetime.timezone.utc),
                                              colour=0x00ACED)
                        embed.set_author(name=status.user.name, icon_url=status.user.profile_image_url)
                        if extended_entities and extended_entities["media"][0]["type"] == "photo":
                            embed.set_image(url=extended_entities["media"][0]["media_url_https"])
                            embed.description = embed.description.replace(extended_entities["media"][0]["url"], "")
                        embed.set_footer(text="Twitter", icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png")
                        self.bot.loop.create_task(self.send_embed(channel, embed), name="Send Embed for Tweet")

    @staticmethod
    async def send_embed(channel, embed):
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.NotFound):
            pass

    def on_error(self, status_code):
        log.error(f"Twitter error: {status_code}")
        return False

    def on_exception(self, exception):
        if isinstance(exception, urllib3.exceptions.ReadTimeoutError):
            log.warning("Twitter stream timed out | Recreating stream..")
            self.bot.loop.create_task(self.start_feeds(), name="Restart Twitter Stream")
        elif isinstance(exception, urllib3.exceptions.ProtocolError):
            log.warning("Twitter stream Incomplete Read error | Recreating stream..")
            self.bot.loop.create_task(self.start_feeds(), name="Restart Twitter Stream")

class Twitter(commands.Cog):
    """Twitter feeds."""
    def __init__(self, bot):
        self.bot = bot
        self.blocklisted_handles = []
        try:
            twitter_account = self.bot.twitter_api.verify_credentials()
            if twitter_account.protected:
                self.blocklisted_handles.append(twitter_account.screen_name.lower())
            # TODO: Handle more than 5000 friends/following
            twitter_friends = self.bot.twitter_api.friends_ids(screen_name=twitter_account.screen_name)
            for interval in range(0, len(twitter_friends), 100):
                some_friends = self.bot.twitter_api.lookup_users(twitter_friends[interval:interval + 100])
                for friend in some_friends:
                    if friend.protected:
                        self.blocklisted_handles.append(friend.screen_name.lower())
        except tweepy.TweepError as e:
            log.exception(f"Failed to initialize Twitter cog blocklist: {e}")
        self.stream_listener = TwitterStreamListener(bot)
        self.task = self.bot.loop.create_task(self.start_twitter_feeds(), name = "Start Twitter Stream")

    async def cog_unload(self):
        if self.stream_listener.stream:
            self.stream_listener.stream.disconnect()
        self.task.cancel()

    @commands.group(invoke_without_command=True)
    async def twitter(self, ctx):
        """Twitter."""
        await ctx.send_help(ctx.command)

    @twitter.command(name="status")
    async def twitter_status(self, ctx, handle: str, replies: bool=False, retweets: bool=False):
        """Get Twitter status
        Excludes replies and retweets by default
        Limited to 200 most recent tweets.
        """
        tweet = None
        handle = handle.lower().strip('@')
        if handle in self.blocklisted_handles:
            return await ctx.send("\N{NO ENTRY} Unauthorised.")
        try:
            for status in tweepy.Cursor(self.bot.twitter_api.user_timeline, screen_name=handle, exclude_replies=not replies, include_rts=retweets, tweet_mode="extended", count=200).items():
                tweet = status
                break
        except tweepy.TweepError as e:
            if e.api_code == 34:
                return await ctx.send(f"\N{NO ENTRY} Error: @{handle} not found")
            else:
                return await ctx.send(f"\N{NO ENTRY} Error: {e}")
        if tweet is None:
            return await ctx.send(f"\N{NO ENTRY} Error: Status not found.")
        text = self.process_tweet_text(tweet.full_text, tweet.entities)
        image_url = None
        if hasattr(tweet, "extended_entities") and tweet.extended_entities["media"][0]["type"] == "photo":
            image_url = tweet.extended_entities["media"][0]["media_url_https"]
            text = text.replace(tweet.extended_entities["media"][0]["url"], "")
        embed = discord.Embed(description=text, title=f'@{tweet.user.screen_name}', colour=0x00ACED, url=f'https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}')
        if image_url is not None:
            embed.set_image(url=image_url)
        embed.set_footer(text=tweet.user.name, icon_url=tweet.user.profile_image_url)
        embed.timestamp = tweet.created_at
        await ctx.send(embed=embed)

    @twitter.command(name='add', aliases=['addhandle', 'handleadd'])
    @checks.is_guild_owner()
    @commands.guild_only()
    async def twitter_add(self, ctx, handle: str):
        """Add a Twitter handle to a text channel.
        A delay of up to 2 minutes is possible due to Twitter rate limits.
        """
        handle = handle.lower().strip('@')
        query = "SELECT EXISTS (SELECT FROM twitter WHERE channel_id = $1 AND handle = $2);"
        following = await ctx.db.fetchval(query, ctx.channel.id, handle)
        if following:
            return await ctx.send("\N{NO ENTRY} This channel is already following that Twitter handle.")
        message = await ctx.send(embed=discord.Embed(description="\N{HOURGLASS} Please wait..."))
        try:
            await self.stream_listener.add_feed(ctx.channel, handle)
        except tweepy.TweepError as e:
            return await message.edit(embed=discord.Embed(description=f"\N{NO ENTRY} Error: {e}"))
        
        query = "INSERT INTO twitter (channel_id, handle) VALUES ($1, $2);"
        await ctx.db.execute(query, ctx.channel.id, handle)
        await message.edit(embed=discord.Embed(description=f"Added the Twitter handle, [`@{handle}`](https://twitter.com/{handle}), to this text channel"))

    @twitter.command(name='remove', aliases=['delete', 'removehandle', 'handleremove', 'deletehandle', 'handledelete'])
    @checks.is_guild_owner()
    async def twitter_remove(self, ctx, handle: str):
        """Removes a Twitter handle from a text channel.
        A delay of up to 2 minutes is possible due to Twitter rate limits.
        """
        handle = handle.lower().strip('@')
        query = "DELETE FROM twitter WHERE channel_id = $1 AND handle = $2 RETURNING *;"
        deleted = await ctx.db.fetchval(query, ctx.channel.id, handle)
        if deleted is None:
            return await ctx.send("\N{NO ENTRY} This channel is not following that Twitter handle.")
        message = await ctx.send(embed=discord.Embed(description="\N{HOURGLASS} Please wait..."))
        await self.stream_listener.remove_feed(ctx.channel, handle)
        embed = message.embeds[0]
        embed.description = f"Removed the Twitter handle, [`{handle}`](https://twitter.com/{handle}), from this text channel."
        await message.edit(embed=embed)

    @twitter.command(aliases=['handle', 'feeds', 'feed', 'list'])
    async def handles(self, ctx):
        """Lists the Twitter handles being followed in this channel."""
        query = "SELECT handle FROM twitter WHERE channel_id = $1;"
        records = await ctx.db.fetch(query, ctx.channel.id)
        if records is None:
            return await ctx.send("No handles are being followed in this channel.")
        await ctx.send(embed=discord.Embed(title='Handles followed', description='\n'.join(f'[@{record["handle"]}](https://twitter.com/{record["handle"]})' for record in records), colour=0x00ACED))
        
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if isinstance(channel, discord.TextChannel):
            async with self.bot.pool.acquire() as con:
                await con.execute("DELETE FROM twitter WHERE channel_id = $1", channel.id)

    def process_tweet_text(self, text, entities):
        mentions = {}
        for mention in entities["user_mentions"]:
            mentions[text[mention["indices"][0]:mention["indices"][1]]] = mention["screen_name"]
        for mention, screen_name in mentions.items():
            text = text.replace(mention, f"[{mention}](https://twitter.com/{screen_name})")
        for hashtag in entities["hashtags"]:
            text = text.replace(f'#{hashtag["text"]}', f'[#{hashtag["text"]}](https://twitter.com/hashtag/{hashtag["text"]})')
        for symbol in entities["symbols"]:
            text = text.replace(f'${symbol["text"]}', f'[${symbol["text"]}](https://twitter.com/search?q=${symbol["text"]})')
        for url in entities["urls"]:
            text = text.replace(url['url'], url['expanded_url'])
        # Remove Variation Selector-16 characters
        # Unescape HTML entities (&gt;, &lt;, &amp;, etc.)
        return html.unescape(text.replace('\uFE0F', ''))

    async def start_twitter_feeds(self):
        await self.bot.wait_until_ready()
        feeds = {}
        try:
            async with self.bot.pool.acquire() as connection:
                async with connection.transaction():
                    # Postgres requires non-scrollable cursors to be created and used within a transaction
                    async for record in connection.cursor("SELECT * FROM twitter"):
                        try:
                            partial = functools.partial(self.bot.twitter_api.get_user, record['handle'])
                            user = await self.bot.loop.run_in_executor(None, partial)
                            feeds[record['channel_id']] = feeds.get(record['channel_id'], []) + [user.id_str]
                        except tweepy.TweepError as e:
                            if e.api_code in (50, 63):
                                # User not found (50) or suspended (63)
                                continue
                            raise e
            await self.stream_listener.start_feeds(feeds=feeds)
        except Exception as e:
            log.error("Uncaught Twitter task exception\n", exc_info=(type(e), e, e.__traceback__))
            print("Exception in Twitter task", file=sys.stderr)
            traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return

async def setup(bot):
    await bot.add_cog(Twitter(bot))
