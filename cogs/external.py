import json
import textwrap
from datetime import datetime

import discord
from aiohttp import ContentTypeError
from currency_converter import CurrencyConverter
from discord.ext import commands
from .utils import time

class PypiObject:
    """PyPI objects."""

    def __init__(self, pypi_dict):
        self.module_name = pypi_dict['info']['name']
        self.module_author = pypi_dict['info']['author']
        self.module_author_email = pypi_dict['info']['author_email'] or None
        self.module_license = pypi_dict['info']['license'] or 'No license specified on PyPI.'
        self.module_minimum_py = pypi_dict['info']['requires_python'] or 'No minimum version specified.'
        self.module_latest_ver = pypi_dict['info']['version']
        self.release_time = pypi_dict['releases'][str(self.module_latest_ver)][0]['upload_time']
        self.module_description = pypi_dict['info']['summary'] or None
        self.pypi_urls = pypi_dict['info']['project_urls']
        self.raw_classifiers = pypi_dict['info']['classifiers'] or None

    @property
    def urls(self) -> str:
        return self.pypi_urls or 'No URLs listed.'

    @property
    def minimum_ver(self) -> str:
        return discord.utils.escape_markdown(self.module_minimum_py)

    @property
    def classifiers(self) -> str:
        if self.raw_classifiers:
            new = textwrap.shorten('\N{zwsp}'.join(self.raw_classifiers), width=300)
            return '\n'.join(new.split('\N{zwsp}'))

    @property
    def description(self) -> str:
        if self.module_description:
            return textwrap.shorten(self.module_description, width=300)
        return None

    @property
    def release_datetime(self) -> datetime:
        return time.hf_time(datetime.fromisoformat(self.release_time))

class External(commands.Cog):
    """External API stuff."""

    def __init__(self, bot):
        self.bot = bot
        self.headers = {'User-Agent': 'Robo VJ Discord bot.'}
        self.currency_conv = CurrencyConverter()
        self.currency_codes = json.loads(open('cogs/utils/currency_codes.json').read())

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def pypi(self, ctx, *, package_name: str):
        """Searches PyPI for a package."""
        async with ctx.session.get(f'https://pypi.org/pypi/{package_name}/json', headers=self.headers) as resp:
            js = await resp.json()
        pypi_details = PypiObject(js)

        embed = discord.Embed(title=f'{pypi_details.module_name} on PyPI', colour=discord.Colour(0x000000))
        embed.set_author(name=pypi_details.module_author)
        embed.description = pypi_details.description

        if pypi_details.module_author_email:
            embed.add_field(name='Author contact', value=pypi_details.module_author_email)
        
        embed.add_field(name='Latest released version', value=pypi_details.module_latest_ver)
        embed.add_field(name='Released at', value=pypi_details.release_datetime)
        embed.add_field(name='Supported python version(s)', value=pypi_details.minimum_ver, inline=False)

        if isinstance(pypi_details.urls, str):
            urls = pypi_details.urls
        elif isinstance(pypi_details.urls, dict):
            urls = '\n'.join([f'[{key}]({value})' for key, value in pypi_details.urls.items()])
        
        embed.add_field(name='Relevant URLs', value=urls)
        embed.add_field(name='License', value=pypi_details.module_license)

        if pypi_details.raw_classifiers:
            embed.add_field(name='Classifiers', value=pypi_details.classifiers, inline=False)
        
        embed.set_footer(text=f'Requested by: {ctx.author.display_name}')
        await ctx.send(embed=embed)

    @commands.command()
    async def currency(self, ctx, amount: float, source: str, dest: str):
        """Currency converter."""
        source = source.upper()
        dest = dest.upper()
        new_amount = self.currency_conv.convert(amount, source, dest)
        prefix = next((curr for curr in self.currency_codes if curr['cc'] == dest), None).get('symbol')
        await ctx.send(f'{prefix}{round(new_amount, 2):.2f}')

    @pypi.error
    async def pypi_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, ContentTypeError):
            error.handled = True
            return await ctx.send("That package doesn't exist on PyPI.")

def setup(bot):
    bot.add_cog(External(bot))
