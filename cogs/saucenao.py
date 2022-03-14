from discord.ext import commands
from lxml import etree


class SauceNao(commands.Cog):
    sauce_url = 'https://saucenao.com/search.php'

    def __init__(self, bot):
        self.session = bot.session
        self.parser = etree.HTMLParser()

    @commands.command(aliases=['sauce'])
    async def saucenao(self, ctx, *, link: str = '') -> None:
        """Find the source of a linked or attached image using saucenao."""
        async with ctx.typing():
            if not link:
                if ctx.message.attachments:
                    link = ctx.message.attachments[0].url
                else:
                    raise commands.BadArgument('No link or attached image found.')

            link = link.strip('<>')
            payload = {'url': link}

            async with self.session.post(self.sauce_url, data=payload) as resp:
                root = etree.fromstring(await resp.text(), self.parser)

            results = root.xpath('.//div[@class="result"]')
            sim_percent = 0.0
            if len(results):
                similarity = root.find('.//div[@class="resultsimilarityinfo"]').text
                sim_percent = float(similarity[:-1])

            if sim_percent <= 60:
                await ctx.send('No sauce found.')
            else:
                result = results[0]
                if (
                        booru_link := result.find('.//div[@class="resultmiscinfo"]/a')
                ) is not None:
                    link = f"<{booru_link.get('href')}>"
                elif (
                        source_link := result.find('.//div[@class="resultcontentcolumn"]/a')
                ) is not None:
                    link = f"<{source_link.get('href')}>"
                else:
                    link = "with no author information."
                await ctx.send(f"Sauce found ({similarity}) {link}")

    @saucenao.error
    async def saucenao_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)


async def setup(bot):
    await bot.add_cog(SauceNao(bot))
