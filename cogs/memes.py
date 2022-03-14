import aiohttp
import contextlib
import random
import string
from datetime import datetime
from typing import Any, List

import discord
from discord import Embed  # must fix soon :tm:
from discord.ext import commands, menus
from .utils.paginator import RoboPages
from .utils.reddit import Reddit

random.seed(datetime.utcnow())


class PagedEmbedMenu(menus.ListPageSource):
    def __init__(self, embeds: List[Embed]):
        self.embeds = embeds
        super().__init__([*range(len(embeds))], per_page=1)

    async def format_page(self, menu, page):
        return self.embeds[page]


class Memes(commands.Cog):
    """Memes cog. Probably gonna be loaded with dumb commands."""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(headers={'User-Agent': 'Discord Bot'})
        self._reddit = Reddit.from_sub('aww', cs=self.session)

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    def _gen_embeds(self, requester: str, posts: List[Any]) -> List[Embed]:
        embeds = []

        for post in posts:
            embed = Embed(
                title=post.title,
                description=post.selftext,
                colour=random.randint(0, 0xFFFFFF),
                url=post.url
            )
            embed.set_author(name=f'u/{post.author}')

            if post.media:
                embed.set_image(url=post.media.url)
                embed.add_field(name='Video', value=f'[Click Here]({post.media.url})')

            embed.add_field(name='Updoots', value=post.ups, inline=True)
            embed.add_field(name='Total Comments', value=post.num_comments, inline=True)
            page = f'Result {posts.index(post) + 1} of {len(posts)}'
            embed.set_footer(text=f'{page} | r/{post.subreddit} | Requested by {requester}')
            embeds.append(embed)
        return embeds

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.channel, wait=False)
    async def reddit(self, ctx, sub: str = 'memes', sort: str = 'hot', timeframe: str = 'all', comments: bool = False):
        """Gets the <sub>reddit's posts sorted by <sort> method within the <timeframe> with <comments>
        determining whether to fetch comments too.
        """
        if not sort.lower() in ('hot', 'new', 'top', 'rising', 'controversial'):
            return await ctx.send('Not a valid sort method.')

        if sub != self._reddit.sub:
            self._reddit = await Reddit.from_sub(
                sub,
                method=sort,
                timeframe=timeframe,
                cs=self.session
            ).load(comments=comments)
        else:
            await self._reddit.load(comments=comments)

        if not ctx.channel.is_nsfw():
            posts = filter(lambda p: not p.over_18, self._reddit.posts)
        else:
            posts = self._reddit.posts

        embeds = self._gen_embeds(ctx.author, posts)
        pages = RoboPages(PagedEmbedMenu(embeds))
        try:
            await pages.start(ctx)
        except menus.MenuError as e:
            await ctx.send(f'{e}')

    @reddit.error
    async def reddit_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, commands.NSFWChannelRequired):
            return await ctx.send('This ain\'t an NSFW channel.')
        elif isinstance(error, commands.BadArgument):
            msg = 'There seem to be no Reddit posts to show, common cases are:\n' \
                  '- Not a real subreddit.\n'
            return await ctx.send(msg)

    @commands.command(name='mock')
    async def _mock(self, ctx, *, message: str):
        with contextlib.suppress(discord.Forbidden):
            await ctx.message.delete()
        output = ''
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


async def setup(bot):
    await bot.add_cog(Memes(bot))
