import inspect
import io
import os
import re
import zlib
from asyncio import TimeoutError

from aiohttp import ClientTimeout

import discord
import discord.http
import discord.abc
import discord.state
import discord.webhook
import discord.gateway
import discord.raw_models
from lxml import etree

from discord.ext import commands, tasks
from .utils import fuzzy


class SphinxObjectFileReader:
    """ A Sphinx file reader. """
    # Inspired by Sphinx's InventoryFileReader
    BUFSIZE = 16 * 1024

    def __init__(self, buffer):
        self.stream = io.BytesIO(buffer)

    def readline(self):
        return self.stream.readline().decode('utf-8')

    def skipline(self):
        self.stream.readline()

    def read_compressed_chunks(self):
        decompressor = zlib.decompressobj()
        while True:
            chunk = self.stream.read(self.BUFSIZE)
            if len(chunk) == 0:
                break
            yield decompressor.decompress(chunk)
        yield decompressor.flush()

    def read_compressed_lines(self):
        buf = b''
        for chunk in self.read_compressed_chunks():
            buf += chunk
            pos = buf.find(b'\n')
            while pos != -1:
                yield buf[:pos].decode('utf-8')
                buf = buf[pos + 1:]
                pos = buf.find(b'\n')


class RTFX(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def parse_object_inv(self, stream, url):
        # key: URL
        # n.b.: key doesn't have `discord` or `discord.ext.commands` namespaces
        result = {}

        # first line is version info
        inv_version = stream.readline().rstrip()

        if inv_version != '# Sphinx inventory version 2':
            raise RuntimeError('Invalid objects.inv file version.')

        # next line is "# Project: <name>"
        # then after that is "# Version: <version>"
        projname = stream.readline().rstrip()[11:]
        version = stream.readline().rstrip()[11:]

        # next line says if it's a zlib header
        line = stream.readline()
        if 'zlib' not in line:
            raise RuntimeError(
                'Invalid objects.inv file, not z-lib compatible.')

        # This code mostly comes from the Sphinx repository.
        entry_regex = re.compile(
            r'(?x)(.+?)\s+(\S*:\S*)\s+(-?\d+)\s+(\S+)\s+(.*)')
        for line in stream.read_compressed_lines():
            match = entry_regex.match(line.rstrip())
            if not match:
                continue

            name, directive, _, location, dispname = match.groups()
            domain, _, subdirective = directive.partition(':')
            if directive == 'py:module' and name in result:
                # From the Sphinx Repository:
                # due to a bug in 1.1 and below,
                # two inventory entries are created
                # for Python modules, and the first
                # one is correct
                continue

            # Most documentation pages have a label
            if directive == 'std:doc':
                subdirective = 'label'

            if location.endswith('$'):
                location = location[:-1] + name

            key = name if dispname == '-' else dispname
            prefix = f'{subdirective}:' if domain == 'std' else ''

            if projname == 'discord.py':
                key = key.replace('discord.ext.commands.',
                                  '').replace('discord.', '')

            result[f'{prefix}{key}'] = os.path.join(url, location)

        return result

    async def build_rtfm_lookup_table(self, page_types):
        cache = {}
        for key, page in page_types.items():
            # sub = cache[key] = {}
            async with self.bot.session.get(page + '/objects.inv') as resp:
                if resp.status != 200:
                    raise RuntimeError(
                        'Cannot build rtfm lookup table, try again later. Code {} page {}'.format(resp.status, resp.url))

                stream = SphinxObjectFileReader(await resp.read())
                cache[key] = self.parse_object_inv(stream, page)

        self._rtfm_cache = cache

    async def do_rtfm(self, ctx, key, obj):
        page_types = {
            'discord.py': 'https://discordpy.readthedocs.io/en/latest',
            'discord.py-jp': 'https://discordpy.readthedocs.io/ja/latest',
            'discord.py-master': 'https://discordpy.readthedocs.io/en/master',
            #'discord.py-master-jp': 'https://discordpy.readthedocs.io/ja/master',
            'python': 'https://docs.python.org/3',
            'python-jp': 'https://docs.python.org/ja/3',
            'asyncpg': 'https://magicstack.github.io/asyncpg/current',
            'twitchio': 'https://twitchio.readthedocs.io/en/latest',
            'aiohttp': 'https://docs.aiohttp.org/en/stable',
            'wavelink': 'https://wavelink.readthedocs.io/en/latest'
        }

        if obj is None:
            await ctx.send(page_types[key])
            return

        if not hasattr(self, '_rtfm_cache'):
            await ctx.trigger_typing()
            await self.build_rtfm_lookup_table(page_types)

        obj = re.sub(
            r'^(?:discord\.(?:ext\.)?)?(?:commands\.)?(.+)', r'\1', obj)

        if key.startswith('discord.'):
            # point the abc.Messageable types properly:
            q = obj.lower()
            for name in dir(discord.abc.Messageable):
                if name[0] == '_':
                    continue
                if q == name:
                    obj = f'abc.Messageable.{name}'
                    break

        cache = list(self._rtfm_cache[key].items())

        matches = fuzzy.finder(obj, cache, key=lambda t: t[0], lazy=False)

        e = discord.Embed(colour=discord.Colour.blurple())
        if not matches:
            return await ctx.send('Could not find anything. Sorry.')
        e.title = f"RTFM for __**`{key}`**__: {obj}"
        e.description = '\n'.join(f'[`{key}`]({url})' for key, url in matches[:8])
        e.set_footer(text=f"{len(matches)} possible results.")
        await ctx.send(embed=e, reference=ctx.replied_reference)

    @commands.group(aliases=['rtfd'], invoke_without_command=True)
    async def rtfm(self, ctx, *, obj: str = None):
        """Gives you a documentation link for a discord.py entity.
        Events, objects, and functions are all supported through a
        a cruddy fuzzy algorithm.
        """
        await self.do_rtfm(ctx, "discord.py", obj)

    @rtfm.command(name='jp')
    async def rtfm_jp(self, ctx, *, obj: str = None):
        """Gives you a documentation link for a discord.py entity (Japanese)."""
        await self.do_rtfm(ctx, 'discord.py-jp', obj)

    @rtfm.command(name='master', aliases=['2.0'])
    async def rtfm_master(self, ctx, *, obj: str = None):
        """Gives you a documentation link for a discord.py entity (master branch)."""
        await self.do_rtfm(ctx, 'discord.py-master', obj)

    @rtfm.command(name='master-jp', aliases=['2.0-jp'])
    async def rtfm_master_jp(self, ctx, *, obj: str = None):
        """Gives you a documentation link for a discord.py entity (master branch) (Japanese)."""
        await self.do_rtfm(ctx, 'discord.py-master-jp', obj)

    @rtfm.command(name='python', aliases=['py'])
    async def rtfm_python(self, ctx, *, obj: str = None):
        """Gives you a documentation link for a Python entity."""
        await self.do_rtfm(ctx, "python", obj)

    @rtfm.command(name='py-jp', aliases=['py-ja'])
    async def rtfm_python_jp(self, ctx, *, obj: str = None):
        """Gives you a documentation link for a Python entity (Japanese)."""
        await self.do_rtfm(ctx, 'python-jp', obj)

    @rtfm.command(name="asyncpg")
    async def rtfm_asyncpg(self, ctx, *, obj: str = None):
        """ Gives you the documentation link for an `asyncpg` entity. """
        await self.do_rtfm(ctx, 'asyncpg', obj)

    @rtfm.command(name="twitchio")
    async def rtfm_twitchio(self, ctx, *, obj: str = None):
        """ Gives you the documentation link for a `twitchio` entity. """
        await self.do_rtfm(ctx, 'twitchio', obj)

    @rtfm.command(name="aiohttp")
    async def rtfm_aiohttp(self, ctx, *, obj: str = None):
        """ Gives you the documentation link for an `aiohttp` entity. """
        await self.do_rtfm(ctx, 'aiohttp', obj)

    @rtfm.command(name="wavelink")
    async def rtfm_wavelink(self, ctx, *, obj: str = None):
        """ Gives you the documentation link for a `Wavelink` entity. """
        await self.do_rtfm(ctx, 'wavelink', obj)

    async def refresh_faq_cache(self):
        self.faq_entries = {}
        base_url = 'https://discordpy.readthedocs.io/en/latest/faq.html'
        async with self.bot.session.get(base_url) as resp:
            text = await resp.text(encoding='utf-8')

            root = etree.fromstring(text, etree.HTMLParser())
            nodes = root.findall(".//div[@id='questions']/ul[@class='simple']/li/ul//a")
            for node in nodes:
                self.faq_entries[''.join(node.itertext()).strip()] = base_url + node.get('href').strip()

    @commands.command()
    async def faq(self, ctx, *, query: str = None):
        """Shows an FAQ entry from the discord.py documentation."""
        if not hasattr(self, 'faq_entries'):
            await self.refresh_faq_cache()

        if query is None:
            return await ctx.send('https://discordpy.readthedocs.io/en/latest/faq.html')

        matches = fuzzy.extract_matches(query, self.faq_entries, scorer=fuzzy.partial_ratio, score_cutoff=40)
        if len(matches) == 0:
            return await ctx.send('Nothing found...')

        paginator = commands.Paginator(suffix='', prefix='')
        for key, _, value in matches:
            paginator.add_line(f'**{key}**\n{value}')
        page = paginator.pages[0]
        await ctx.send(page, reference=ctx.replied_reference)

    @commands.command()
    async def rtfs(self, ctx, *, search: str):
        """ Read the fuckin' source of discord.py. """
        embed = discord.Embed(
            title="Read the f*ckin source",
            colour=discord.Colour.blurple()
        )
        # timeout = ClientTimeout(5)
        # try:
        #     async with self.bot.session.get(f"https://rtfs.eviee.me/dpy?search={search}", timeout=timeout) as resp:
        #         results = await resp.json()
        # except TimeoutError:
        #     return await ctx.send("API is down, go look yourself lmao: <https://github.com/Rapptz/discord.py>")
        # if not results:
        #     embed.title = "Couldn't find anything."
        # else:
        #     embed.title = f"RTFS for '{search}'"
        #     embed.description = '\n'.join(
        #         f"[`{result['module']}.{result['object']}`]({result['url']})" for result in results[:10])
        #     eviee = self.bot.get_user(402159684724719617) or "Eviee#0666"  # just in case ;q
        #     embed.set_footer(
        #         text=f"Requested by {ctx.author} | Thank you {eviee} for the API.")
        overhead = ""
        raw_search = search
        searches = []
        if '.' in search:
            searches = search.split('.')
            search = searches[0]
            searches = searches[1:]
        get = getattr(discord, search, None)
        if get is None:
            get = getattr(commands, search, None)
            if get is None:
                get = getattr(tasks, search, None)
        if get is None:
            embed.title = f'Nothing found under `{raw_search}`'
            return await ctx.send(embed=embed)
        if inspect.isclass(get) or searches:
            if searches:
                for i in searches:
                    last_get = get
                    get = getattr(get, i, None)
                    if get is None and last_get is None:
                        embed.title = f'Nothing found under `{raw_search}`'
                        return await ctx.send(embed=embed)
                    elif get is None:
                        overhead = f'Couldn\'t find `{i}` under `{last_get.__name__}`, showing source for `{last_get.__name__}`\n\n'
                        get = last_get
                        break
        if isinstance(get, property):
            get = get.fget

        lines, firstlineno = inspect.getsourcelines(get)
        try:
            module = get.__module__
            location = module.replace('.', '/') + '.py'
        except AttributeError:
            location = get.__name__.replace('.', '/') + '.py'
        
        version = 'master' if discord.__version__.endswith('a') else f'v{discord.__version__}'
        ret = f'https://github.com/Rapptz/discord.py/blob/{version}'
        final = f'{overhead}[{location}]({ret}/{location}#L{firstlineno}-L{firstlineno + len(lines) - 1})'
        embed.description = final
        return await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(RTFX(bot))
