from discord.ext import commands
import discord
import aiohttp
import json
from lxml import etree

class CodeBlock:
    missing_error = "Missing code block. Please use the following markdown\n\\`\\`\\`language\ncode here\n\\`\\`\\`"
    def __init__(self, argument):
        try:
            block, code = argument.split('\n', 1)
        except ValueError:
            raise commands.BadArgument(self.missing_error)

        if not block.startswith('```') and not code.endswith('```'):
            raise commands.BadArgument(self.missing_error)

        language = block[3:]
        self.command = self.get_command_from_language(language.lower())
        self.source = code.rstrip('`').replace('```', '')

    def get_command_from_language(self, language):
        cmds = {
            'cpp': 'g++ -std=c++1z -O2 -Wall -Wextra -pedantic -pthread main.cpp -lstdc++fs && ./a.out',
            'c': 'mv main.cpp main.c && gcc -std=c11 -O2 -Wall -Wextra -pedantic main.c && ./a.out',
            'py': 'python3 main.cpp',
            'python': 'python3 main.cpp',
            'haskell': 'runhaskell main.cpp'
        }

        cpp = cmds['cpp']
        for alias in ('cc', 'h', 'c++', 'h++', 'hpp'):
            cmds[alias] = cpp
        try:
            return cmds[language]
        except KeyError as e:
            if language:
                fmt = f'Unknown language to compile for: {language}'
            else:
                fmt = 'Could not find a language to compile with'
            raise commands.BadArgument(fmt) from e

class Code(commands.Cog, name='c++'):
    """Trial C++ Cog.

    Don't abuse these.
    """
    
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    @commands.command()
    async def coliru(self, ctx, *, code: CodeBlock):
        """Compiles code via Coliru.

        You have to pass in a code block with the language syntax
        set to one of these:

        - cpp
        - c
        - haskell
        - py
        - python

        Anything else isn't supported. The C++ compiler uses g++ -std=c++14.

        The python support is now 3.5.2.

        Please don't spam this for Stacked's sake.
        """
        payload = {
            'cmd': code.command,
            'src': code.source
        }

        data = json.dumps(payload)
        
        async with ctx.typing():
            async with ctx.session.post('http://coliru.stacked-crooked.com/compile', data=data) as resp:
                if resp.status != 200:
                    await ctx.send('Coliru didn\'t respond in time.')
                    return
                
                output = await resp.text(encoding='utf-8')

                if len(output) < 1992:
                    await ctx.send(f'```\n{output}\n```')
                    return
                
                # output is too big so post it in gist
                async with ctx.session.post('http://coliru.stacked-crooked.com/share', data=data) as r:
                    if r.status != 200:
                        await ctx.send('Could not create Coliru shared link')
                    else:
                        shared_id = await r.text()
                        await ctx.send(f'Output too big. Coliru link: http://coliru.stacked-crooked.com/a/{shared_id}')

    @coliru.error
    async def coliru_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(CodeBlock.missing_error)

    @commands.command()
    async def cpp(self, ctx, *, query: str):
        """Search something on cppreference."""

        url = 'https://en.cppreference.com/mwiki/index.php'
        params = {
            'title': 'Special:Search',
            'search': query
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
        }

        async with ctx.session.get(url, headers=headers, params=params) as resp:
            if resp.status != 200:
                return await ctx.send(f'An error occurred. (status code: {resp.status}). Retry later.')
            
            if resp.url.path != '/mwiki/index.php':
                return await ctx.send(f'<{resp.url}>')

            embed = discord.Embed()
            root = etree.fromstring(await resp.text(), etree.HTMLParser())

            nodes = root.findall(".//div[@class='mw-search-result-heading']/a")

            description = []
            special_pages = []
            for node in nodes:
                href = node.attrib['href']
                if not href.startswith('/w/cpp'):
                    continue

                if href.startswith(('/w/cpp/language', '/w/cpp/concept')):
                    # special page
                    special_pages.append(f'[{node.text}](https://en.cppreference.com{href})')
                else:
                    description.append(f'[{node.text}](http://en.cppreference.com{href})')

            if len(special_pages) > 0:
                embed.add_field(name='Language Results', value='\n'.join(special_pages), inline=False)
                if len(description):
                    embed.add_field(name='Library Results', value='\n'.join(description[:10]), inline=False)
            else:
                if not len(description):
                    return await ctx.send('No results found.')
                
                embed.title = 'Search Results'
                embed.description = '\n'.join(description[:15])

            embed.add_field(name='See More', value=f'[`{discord.utils.escape_markdown(query)}` results]({resp.url})')
            await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(Code(bot))