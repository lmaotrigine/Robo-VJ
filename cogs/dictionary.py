import discord
from discord.ext import commands, menus
from .utils.paginator import RoboPages
from .utils.asyncjisho import Jisho


class DictPageSource(menus.ListPageSource):
    jisho_url = 'http://jisho.org/search/{}'

    def __init__(self, entries):
        super().__init__(entries=entries, per_page=1)

    async def format_page(self, menu, page):
        maximum = self.get_max_pages()
        title = page['keywords']
        url = self.jisho_url.format('%20'.join(page['keywords'].split()))
        embed = discord.Embed(title=title, url=url, colour=0x56D926)
        embed.add_field(name="Words", value=page["words"])
        embed.add_field(name="Readings", value=page["readings"])
        embed.add_field(name="Parts of Speech", value=page["parts_of_speech"])
        embed.add_field(name="Meanings", value=page["english"])
        if maximum:
            embed.set_footer(text=f'Page {menu.current_page + 1}/{maximum}')
        return embed


class Dictionary(commands.Cog):
    jisho_url = 'http://jisho.org/search/{}'

    def __init__(self, bot):
        self.jisho = Jisho(session=bot.session)

    @commands.command(name='jisho')
    async def jisho_(self, ctx, *, keywords: str) -> None:
        """Get results from Jisho.org, Japanese dictionary."""
        async with ctx.typing():
            data = await self.jisho.lookup(keywords)
        if not data:
            await ctx.send('No words found.')
            return
        results = []
        for res in data:
            res = {k: '\n'.join(set(v)) or 'None' for k, v in res.items()}
            res['english'] = ', '.join(res['english'].split('\n'))
            res['keywords'] = keywords
            results.append(res)

        pages = RoboPages(DictPageSource(results))
        try:
            await pages.start(ctx)
        except menus.MenuError as e:
            await ctx.send(e)


def setup(bot):
    bot.add_cog(Dictionary(bot))
