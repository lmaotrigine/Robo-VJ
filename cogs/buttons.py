import asyncio
from discord.ext import commands, menus
import discord
from .utils.paginator import RoboPages
import random
import logging
from lru import LRU
import yarl
import io
import re
from collections import namedtuple
from textwrap import shorten
import contextlib
import string


log = logging.getLogger(__name__)

def can_use_spoiler():
    def predicate(ctx):
        if ctx.guild is None:
            raise commands.BadArgument('Cannot be used in private messages.')

        my_permissions = ctx.channel.permissions_for(ctx.guild.me)
        if not (my_permissions.read_message_history and my_permissions.manage_messages and my_permissions.add_reactions):
            raise commands.BadArgument('Need Read Message History, Add Reactions and Manage Messages ' \
                                       'permissions to use this. Sorry if I spoiled you.')
        return True
    return commands.check(predicate)

SPOILER_EMOJI_ID = 768113356669714452

class UrbanDictionaryPageSource(menus.ListPageSource):
    BRACKETED = re.compile(r'(\[(.+?)\])')
    def __init__(self, data):
        super().__init__(entries=data, per_page=1)

    def cleanup_definition(self, definition, *, regex=BRACKETED):
        def repl(m):
            word = m.group(2)
            return f'[{word}](http://{word.replace(" ", "-")}.urbanup.com)'

        ret = regex.sub(repl, definition)
        if len(ret) >= 2048:
            return ret[0:2000] + '[...]'
        return ret

    async def format_page(self, menu, entry):
        maximum = self.get_max_pages()
        title = f'{entry["word"]}: {menu.current_page + 1} out of {maximum}' if maximum else entry['word']
        embed = discord.Embed(title=title, colour=0xE86222, url=entry['permalink'])
        embed.set_footer(text=f'By {entry["author"]}')
        embed.description = self.cleanup_definition(entry['definition'])

        try:
            up, down = entry['thumbs_up'], entry['thumbs_down']
        except KeyError:
            pass
        else:
            embed.add_field(name='Votes', value=f'\N{THUMBS UP SIGN} {up} \N{THUMBS DOWN SIGN} {down}', inline=False)

        try:
            date = discord.utils.parse_time(entry['written_on'][:-1])
        except (ValueError, KeyError):
            pass
        else:
            embed.timestamp = date

        return embed

class RedditMediaURL:
    def __init__(self, url):
        self.url = url
        self.filename = url.parts[1] + '.mp4'

    @classmethod
    async def convert(cls, ctx, argument):
        try:
            url = yarl.URL(argument)
        except Exception as e:
            raise commands.BadArgument('Not a valid URL.')

        headers = {
            'User-Agent': 'Discord:RoboVJ:v4.0 (by /u/bowtiesarecool26)'
        }
        await ctx.trigger_typing()
        if url.host == 'v.redd.it':
            # have to do a request to fetch the 'main' URL.
            async with ctx.session.get(url, headers=headers) as resp:
                url = resp.url

        is_valid_path = url.host and url.host.endswith('.reddit.com')
        if not is_valid_path:
            raise commands.BadArgument('Not a reddit URL.')

        # Now we go the long way
        async with ctx.session.get(url / '.json', headers=headers) as resp:
            if resp.status != 200:
                raise commands.BadArgument(f'Reddit API failed with {resp.status}.')

            data = await resp.json()
            try:
                submission = data[0]['data']['children'][0]['data']
            except (KeyError, TypeError, IndexError):
                raise commands.BadArgument('Could not fetch submission.')

            try:
                media = submission['media']['reddit_video']
            except (KeyError, TypeError):
                try:
                    # maybe it's a cross post
                    crosspost = submission['crosspost_parent_list'][0]
                    media = crosspost['media']['reddit_video']
                except (KeyError, TypeError, IndexError):
                    raise commands.BadArgument('Could not fetch media information.')

            try:
                fallback_url = yarl.URL(media['fallback_url'])
            except KeyError:
                raise commands.BadArgument('Could not fetch fall back URL.')

            return cls(fallback_url)

class SpoilerCache:
    __slots__ = ('author_id', 'channel_id', 'title', 'text', 'attachments')

    def __init__(self, data):
        self.author_id = data['author_id']
        self.channel_id = data['channel_id']
        self.title = data['title']
        self.text = data['text']
        self.attachments = data['attachments']

    def has_single_image(self):
        return self.attachments and self.attachments[0].filename.lower().endswith(('.gif', '.png', '.jpg', '.jpeg'))

    def to_embed(self, bot):
        embed = discord.Embed(title=f'{self.title} Spoiler', colour = 0x01AEEE)
        if self.text:
            embed.description = self.text
        
        if self.has_single_image():
            if self.text is None:
                embed.title = f'{self.title} Spoiler Image'
            embed.set_image(url=self.attachments[0].url)
            attachments = self.attachments[1:]
        else:
            attachments = self.attachments

        if attachments:
            value = '\n'.join(f'[{a.filename}]({a.url})' for a in attachments)
            embed.add_field(name='Attachments', value=value, inline=False)

        user = bot.get_user(self.author_id)
        if user:
            embed.set_author(name=str(user), icon_url=user.avatar.url)

        return embed

    def to_spoiler_embed(self, ctx, storage_message):
        description = 'React with <:spoiler:768113356669714452> to reveal the spoiler.'
        embed = discord.Embed(title=f'{self.title} Spoiler', description=description)
        if self.has_single_image() and self.text is None:
            embed.title = f'{self.title} Spoiler Image'
        
        embed.set_footer(text=storage_message.id)
        embed.colour = 0x01AEEE
        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar.url)
        return embed

class SpoilerCooldown(commands.CooldownMapping):
    def __init__(self):
        super().__init__(commands.Cooldown(1, 10.0), commands.BucketType.user)

    def _bucket_key(self, tup):
        return tup

    def is_rate_limited(self, message_id, user_id):
        bucket = self.get_bucket((message_id, user_id))
        return bucket.update_rate_limit() is not None

class Buttons(commands.Cog):
    """Buttons that make you feel."""

    def __init__(self, bot):
        self.bot = bot
        self._spoiler_cache = LRU(128)
        self._spoiler_cooldown = SpoilerCooldown()

    @commands.command(hidden=True)
    async def feelgood(self, ctx):
        """press"""
        await ctx.send('*pressed*')

    @commands.command(hidden=True)
    async def feelbad(self, ctx):
        """depress"""
        await ctx.send('*depressed*')

    @commands.command()
    async def love(self, ctx):
        """What is love?"""
        responses = [
            'https://www.youtube.com/watch?v=HEXWRTEbj1I',
            'https://www.youtube.com/watch?v=i0p1bmr0EmE',
            'an intense feeling of deep affection',
            'something we don\'t have'
        ]

        response = random.choice(responses)
        await ctx.send(response)

    @commands.command(hidden=True)
    async def bored(self, ctx):
        """boredom looms"""
        await ctx.send('http://i.imgur.com/BuTKSzf.png')

    @commands.command()
    @commands.cooldown(rate=1, per=60.0, type=commands.BucketType.user)
    async def feedback(self, ctx, *, content: str):
        """Gives feedback about the bot.

        This is a quick way to request features or bug fixes
        without being in the bot's server.

        The bot will communicate with you via PM about the status
        of your request if possible.

        You can only request feedback once a minute.
        """

        e = discord.Embed(title='Feedback', colour=0x738BD7)
        guild = self.bot.get_guild(746769944774967440)
        if guild is None:
            return

        channel = guild.get_channel(768131518991302656)
        if channel is None:
            return

        e.set_author(name=str(ctx.author), icon_url=ctx.author.avatar.url)
        e.description = content
        e.timestamp = ctx.message.created_at

        if ctx.guild is not None:
            e.add_field(name='Server', value=f'{ctx.guild.name} (ID: {ctx.guild.id})', inline=False)
        
        e.add_field(name='Channel', value=f'{ctx.channel} (ID: {ctx.channel.id})')
        e.set_footer(text=f'Author ID: {ctx.author.id}')

        await channel.send(embed=e)
        await ctx.send(f'{ctx.tick(True)} Successfully sent feedback.')

    @commands.command()
    @commands.is_owner()
    async def pm(self, ctx, user_id: int, *, content: str):
        user = self.bot.get_user(user_id) or (await self.bot.fetch_user(user_id))

        fmt = content + '\n\n*This is a DM sent because you had previously requested feedback or I found a bug' \
                        'in a command you used, I do not monitor this DM.*'
        try:
            await user.send(fmt)
        except:
            await ctx.send(f'Could not PM user by ID {user_id}.')
        else:
            await ctx.send('PM successfully sent.')

    async def redirect_post(self, ctx, title, text):
        storage = self.bot.get_guild(746769944774967440).get_channel(768134268467413002)
        
        supported_attachments = ('.png', '.jpg', '.webm', '.jpeg', '.gif', '.mp4', '.txt')
        if not all(attach.filename.lower().endswith(supported_attachments) for attach in ctx.message.attachments):
            raise RuntimeError(f'Unsupported file in attachments. Only {", ".join(supported_attachments)} supported.')

        files = []
        total_bytes = 0
        eight_mib = 8 * 1024 * 1024
        for attach in ctx.message.attachments:
            async with ctx.session.get(attach.url) as resp:
                if resp.status!= 200:
                    continue

                content_length = int(resp.headers.get('content-Length'))

                # file too big, skip it
                if (total_bytes + content_length) > eight_mib:
                    continue

                total_bytes += content_length
                fp = io.BytesIO(await resp.read())
                files.append(discord.File(fp, filename=attach.filename))

            if total_bytes >= eight_mib:
                break

        # on mobile, messages that are deleted immediately sometimes persist client side
        await asyncio.sleep(0.2, loop=self.bot.loop)
        await ctx.message.delete()
        data = discord.Embed(title=title)
        if text:
            data.description = text
        
        data.set_author(name=ctx.author.id)
        data.set_footer(text=ctx.channel.id)

        try:
            message = await storage.send(embed=data, files=files)
        except discord.HTTPException as e:
            raise RuntimeError(f'Sorry. Could not store messages due to {e.__class__.__name__}: {e}.') from e
        
        to_dict = {
            'author_id': ctx.author.id,
            'channel_id': ctx.channel.id,
            'attachments': message.attachments,
            'title': title,
            'text': text
        }

        cache = SpoilerCache(to_dict)
        return message, cache

    async def get_spoiler_cache(self, channel_id, message_id):
        try:
            return self._spoiler_cache[message_id]
        except KeyError:
            pass

        storage = self.bot.get_guild(746769944774967440).get_channel(768134268467413002)

        # slow path requires 2 lookups
        # first is looking up the message_id of the original post
        # to get the embed footer imformation which points to the storage message ID
        # the second is getting the storage message ID and extracting the information from it
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return None

        try:
            original_message = await channel.fetch_message(message_id)
            storage_message_id = int(original_message.embeds[0].footer.text)
            message = await storage.fetch_message(storage_message_id)
        except:
            # this message is probably not the proper format or the storage died
            return None

        data = message.embeds[0]
        to_dict = {
            'author_id': int(data.author.name),
            'channel_id': int(data.footer.text),
            'attachments': message.attachments,
            'title': data.title,
            'text': None if not data.description else data.description
        }
        cache = SpoilerCache(to_dict)
        self._spoiler_cache[message_id] = cache
        return cache

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.id != SPOILER_EMOJI_ID:
            return

        if self._spoiler_cooldown.is_rate_limited(payload.message_id, payload.user_id):
            return

        user = self.bot.get_user(payload.user_id) or (await self.bot.fetch_user(payload.user_id))
        if not user or user.bot:
            return

        cache = await self.get_spoiler_cache(payload.channel_id, payload.message_id)
        embed = cache.to_embed(self.bot)
        await user.send(embed=embed)

    @commands.command()
    @can_use_spoiler()
    async def spoiler(self, ctx, title, *, text=None):
        """Marks your post a spoiler with a title.

        Once your post is marked as a spoiler it will be
        automatically deleted and the bot will DM those who
        opt-in to view the spoiler.

        The only media types supported are png, gif, jpeg, mp4,
        and webm.

        Only 8MiB of total media can be uploaded at once.
        Sorry, Discord limitation.

        To opt-in to a post's spoiler you must click the reaction.
        """

        if len(title) > 100:
            return await ctx.send("Sorry. Title has to be shorter than 100 characters.")

        try:
            storage_message, cache = await self.redirect_post(ctx, title, text)
        except Exception as e:
            return await ctx.send(str(e))

        spoiler_message = await ctx.send(embed = cache.to_spoiler_embed(ctx, storage_message))
        self._spoiler_cache[spoiler_message.id] = cache
        await spoiler_message.add_reaction(':spoiler:768113356669714452')

    @commands.command(usage='<url>')
    @commands.cooldown(1, 5.0, commands.BucketType.member)
    async def vreddit(self, ctx, *, reddit: RedditMediaURL):
        """Downloads a v.redd.it submission.

        Regular Reddit URLs or v.redd.it URLs are supported.
        """

        filesize = ctx.guild.filesize_limit if ctx.guild else 8388608
        async with ctx.session.get(reddit.url) as resp:
            if resp.status != 200:
                return await ctx.send("Could not download video.")

            if int(resp.headers['Content-Length']) >= filesize:
                return await ctx.send("Video is too big to be uploaded.")

            data = await resp.read()
            await ctx.send(file=discord.File(io.BytesIO(data), filename=reddit.filename))

    @vreddit.error
    async def on_vreddit_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)

    @commands.command(name='urban')
    async def _urban(self, ctx, *, word):
        """Searches urban dictionary."""

        url = 'http://api.urbandictionary.com/v0/define'
        async with ctx.session.get(url, params={'term': word}) as resp:
            if resp.status != 200:
                return await ctx.send(f'An error occurred: {resp.status} {resp.reason}')

            js = await resp.json()
            data = js.get('list', [])
            if not data:
                return await ctx.send('No results found. Sorry.')

        pages = RoboPages(UrbanDictionaryPageSource(data))
        try:
            await pages.start(ctx)
        except menus.MenuError as e:
            await ctx.send(e)

    def _gen_embeds(self, requester: str, iterable: list) -> list:
        embeds = []

        for item in iterable:
            embed = discord.Embed(
                title=item.title,
                description=item.self_text,
                colour=random.randint(0, 0xFFFFFF),
                url=item.url,
            )
            embed.set_author(name=f'u/{item.author}', url=f'https://www.reddit.com/u/{item.author}')

            if item.image_link:
                embed.set_image(url=item.image_link)

            if item.video_link:
                embed.add_field(
                    name="Video",
                    value=f"[Click here!]({item.video_link})",
                    inline=False,
                )
            embed.add_field(name="Updoots", value=item.upvotes, inline=True)
            embed.add_field(
                name="Total comments", value=item.comment_count, inline=True
            )
            page_counter = f"Result {iterable.index(item)+1} of {len(iterable)}"
            embed.set_footer(
                text=f"{page_counter} | r/{item.subreddit} | Requested by {requester}"
            )

            embeds.append(embed)

        return embeds

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.channel, wait=False)
    async def reddit(self, ctx, sub: str = "memes", sort: str = "hot"):
        """Gets the <sub>reddits <amount> of posts sorted by <method>"""
        if sort.lower() not in ("top", "hot", "best", "controversial", "new", "rising"):
            return await ctx.send("Not a valid sort-by type.")

        PostObj = namedtuple(
            "PostObj",
            [
                "title",
                "self_text",
                "url",
                "author",
                "image_link",
                "video_link",
                "upvotes",
                "comment_count",
                "subreddit",
            ],
        )

        posts = set()

        if sub.lower().startswith('r/'):
            sub = sub[2:]

        subr_url = f"https://www.reddit.com/r/{sub}/about.json"
        base_url = f"https://www.reddit.com/r/{sub}/{sort}.json"

        async with self.bot.session.get(
                subr_url, headers={"User-Agent": "discord bot"}
        ) as subr_resp:
            subr_deets = await subr_resp.json()

        if "data" not in subr_deets:
            raise commands.BadArgument("Subreddit does not exist.")
        if subr_deets["data"].get("over18", None) and not ctx.channel.is_nsfw():
            raise commands.NSFWChannelRequired(ctx.channel)

        async with self.bot.session.get(base_url) as res:
            page_json = await res.json()

        idx = 0
        for post_data in page_json["data"]["children"]:
            image_url = None
            video_url = None

            if idx == 20:
                break

            post = post_data["data"]
            if post["stickied"] or (post["over_18"] and not ctx.channel.is_nsfw()):
                idx += 1
                continue

            title = shorten(post["title"], width=250)
            self_text = shorten(post["selftext"], width=1500)
            url = f"https://www.reddit.com{post['permalink']}"
            author = post["author"]
            image_url = (
                post["url"]
                if post["url"].endswith((".jpg", ".png", ".jpeg", ".gif", ".webp"))
                else None
            )
            if "v.redd.it" in post["url"]:
                image_url = post["thumbnail"]
                if post.get("media", None):
                    video_url = post["url"]
                else:
                    continue
            upvotes = post["score"]
            comment_count = post["num_comments"]
            subreddit = post["subreddit"]

            _post = PostObj(
                title=title,
                self_text=self_text,
                url=url,
                author=author,
                image_link=image_url,
                video_link=video_url,
                upvotes=upvotes,
                comment_count=comment_count,
                subreddit=subreddit,
            )

            posts.add(_post)
        embeds = self._gen_embeds(ctx.author, list(posts))
        pages = RoboPages(PagedEmbedMenu(embeds))
        try:
            await pages.start(ctx)
        except menus.MenuError as e:
            await ctx.send(f'{e}')

    @reddit.error
    async def reddit_error(self, ctx, error):
        """ Local Error handler for reddit command. """
        error = getattr(error, "original", error)
        if isinstance(error, commands.NSFWChannelRequired):
            return await ctx.send("This ain't an NSFW channel.")
        elif isinstance(error, commands.BadArgument):
            msg = (
                "There seems to be no Reddit posts to show, common cases are:\n"
                "- Not a real subreddit.\n"
            )
            return await ctx.send(msg)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.NSFWChannelRequired):
            await ctx.send(error)

    @commands.command(name="mock")
    async def _mock(self, ctx, *, message: str):
        with contextlib.suppress(discord.Forbidden):
            await ctx.message.delete()
        output = ""
        for counter, char in enumerate(message):
            if char != string.whitespace:
                if counter % 2 == 0:
                    output += char.upper()
                else:
                    output += char
            else:
                output += string.whitespace

        mentions = discord.AllowedMentions(everyone=False, users=False, roles=False)
        await ctx.send(output, allowed_mentions=mentions)


class PagedEmbedMenu(menus.ListPageSource):
    def __init__(self, embeds: list):
        self.embeds = embeds
        super().__init__([*range(len(embeds))], per_page=1)

    async def format_page(self, menu, page):
        return self.embeds[page]


async def setup(bot):
    await bot.add_cog(Buttons(bot))
