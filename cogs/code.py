from discord.ext import commands, tasks
import discord
import json
import io
import re
import urllib.parse
from lxml import etree
from yaml import safe_load as yaml_load
import asyncio
from bs4 import BeautifulSoup
from bs4.element import NavigableString

from .utils.rtfm._tio import Tio


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
    """Trial programming Cog.

    Don't abuse these.
    """
    wrapping = {
        'c': '#include <stdio.h>\nint main() {code}',
        'cpp': '#include <iostream>\nint main() {code}',
        'cs': 'using System;class Program {static void Main(string[] args) {code}}',
        'java': 'public class Main {public static void main(String[] args) {code}}',
        'rust': 'fn main() {code}',
        'd': 'import std.stdio; void main(){code}',
        'kotlin': 'fun main(args: Array<String>) {code}'
    }
    
    def __init__(self, bot):
        self.bot = bot
        self.languages = ()
        self.languages_url = 'https://tio.run/languages.json'
        with open('default_langs.yml', 'r') as f:
            self.default = yaml_load(f)
        self.update_langs.start()

    def get_content(self, tag):
        """Returns content between two h2 tags"""

        bssiblings = tag.next_siblings
        siblings = []
        for elem in bssiblings:
            # get only tag elements, before the next h2
            # Putting away the comments, we know there's
            # at least one after it.
            if type(elem) == NavigableString:
                continue
            # It's a tag
            if elem.name == 'h2':
                break
            siblings.append(elem.text)
        content = '\n'.join(siblings)
        if len(content) >= 1024:
            content = content[:1021] + '...'

        return content

    async def cog_command_error(self, ctx, error):
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            await ctx.send(error)

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    def cog_unload(self):
        self.update_langs.cancel()

    @tasks.loop(hours=1)
    async def update_langs(self):
        async with self.bot.session.get(self.languages_url) as resp:
            if resp.status != 200:
                print(f'Could not reach languages.json (status code: {resp.status})')
            languages = tuple(sorted(json.loads(await resp.text())))

        # Rare reassignments
        if languages != self.languages:
            self.languages = languages

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

    @staticmethod
    def get_raw(link):
        """Returns the url for the raw version on a HasteBin-like."""
        link = link.strip('<>/')  # Allow for no embed links

        authorised = (
            'https://hastebin.com',
            'https://gist.github.com',
            'https://gist.githubusercontent.com'
        )

        if not any([link.startswith(url) for url in authorised]):
            raise commands.BadArgument(f'I only accept links from {", ".join(authorised)}. (Starting with "https")')

        domain = link.split('/')[2]

        if domain == 'hastebin.com':
            if '/raw/' in link:
                return link
            token = link.split('/')[-1]
            if '.' in token:
                token = token[:token.rfind('.')]  # removes extension
            return f'https://hastebin.com/raw/{token}'
        else:
            # GitHub uses redirection so raw -> usercontent and no raw -> normal
            # We still need to ensure that we get a raw version after this potential redirection
            if '/raw' in link:
                return link
            return link + '/raw'

    async def paste(self, text):
        """Return an online bin of the given text."""

        async with self.bot.session.post('https://hastebin.com/documents', data=text) as post:
            if post.status == 200:
                resp = await post.text()
                return f'https://hastebin.com/{resp[8:-2]}'

        # Rollback bin
        async with self.bot.session.post('https://bin.drlazor.be', data={'val': text}) as post:
            if post.status == 200:
                return post.url

    @commands.group(brief='Execute code in a given programming language.',
                      usage='run <language> [--wrapped] [--stats] <code>',
                    invoke_without_command=True)
    async def run(self, ctx, language, *, code=''):
        """Execute code in a given programming language.

        For command-line-options, compiler-flags and arguments you may
        add a line starting with this argument, and after a space add
        your options, flags or args.

        Stats option displays more information on execution consumption
        Wrapped allows you to not put main function in some languages, which
        you can see in `run list wrapped argument`
        <code> may be normal code, but also an attached file, or a link from
        [hastebin](https://hastebin.com) or [Github gist](https://gist.github.com)
        If you use a link, your command must end with this syntax:
        `link=<link>` (no space around `=`)
        for instance : `?run python link=https://hastebin.com/resopedahe.py`
        The link may be the raw version, and with/without the file extension
        If the output exceeds 40 lines or Discord max message length, it will be put
        in a new hastebin and the link will be returned.
        When the code returns your output, you may delete it by clicking :wastebasket:
        in the following minute.
        Useful to hide your syntax fails or when you forgot to print the result.
        """
        options = {
            '--stats': False,
            '--wrapped': False
        }

        lang = language.strip('`').lower()

        options_amount = len(options)

        # Setting options and removing them from the beginning of the command.
        # Options may be separated by any single whitespace, which we keep in the list.
        code = re.split(r'(\s)', code, maxsplit=options_amount)

        for option in options:
            if option in code[:options_amount * 2]:
                options[option] = True
                i = code.index(option)
                code.pop(i)
                code.pop(i)  # Remove the following whitespace character.

        code = ''.join(code)

        compiler_flags = []
        command_line_options = []
        args = []
        inputs = []

        lines = code.split('\n')
        code = []
        for line in lines:
            if line.startswith('input '):
                inputs.append(' '.join(line.split(' ')[1:]).strip('`'))
            elif line.startswith('compiler-flags '):
                compiler_flags.extend(line[15:].strip('`').split(' '))
            elif line.startswith('command-line-options '):
                command_line_options.extend(line[21:].strip('`').split(' '))
            elif line.startswith('arguments '):
                args.extend(line[10:].strip('`').split(' '))
            else:
                code.append(line)

        inputs = '\n'.join(inputs)
        code = '\n'.join(code)
        text = None

        async with ctx.typing():
            if ctx.message.attachments:
                # Code in file
                file = ctx.message.attachments[0]
                if file.size > 20000:
                    return await ctx.send('File must be smaller than 20kB.')
                buffer = io.BytesIO()
                await ctx.message.attachments[0].save(buffer)
                text = buffer.read().decode('utf-8')
            elif code.split(' ')[-1].startswith(('link=', 'link =')):
                # Code in a webpage
                base_url = urllib.parse.quote_plus(code.split(' ')[-1][5:].strip('/'), safe=';/?:@&=$,><-[]')

                url = self.get_raw(base_url)

                async with ctx.session.get(url) as resp:
                    if resp.status == 404:
                        return await ctx.send('Nothing found.Check your link.')
                    elif resp.status != 200:
                        return await ctx.send(f'An error occurred (status code: {resp.status}). Retry later.')
                    text = await resp.text()
                    if len(text) > 20000:
                        return await ctx.send('Code must be shorter than 20,000 characters.')
            elif code.strip('`'):
                # Code in message
                text = code.strip('`')
                first_line = text.splitlines()[0]
                if re.fullmatch(r'( |[0-9A-z]*)\b', first_line):
                    text = text[len(first_line) + 1:]

            if text is None:
                # Ensures code isn't empty after removing options
                raise commands.MissingRequiredArgument(ctx.command.clean_params['code'])

            # common identifiers, also used in highlight.js and thus discord codeblocks
            quickmap = {
                'asm': 'assembly',
                'c#': 'cs',
                'c++': 'cpp',
                'csharp': 'cs',
                'f#': 'fs',
                'fsharp': 'fs',
                'js': 'javascript',
                'nimrod': 'nim',
                'py': 'python',
                'q#': 'qs',
                'rs': 'rust',
                'sh': 'bash',
            }

            if lang in quickmap:
                lang = quickmap[lang]

            if lang in self.default:
                lang = self.default[lang]
            if lang not in self.languages:
                matches = '\n'.join([l for l in self.languages if lang in l][:10])
                lang = discord.utils.escape_mentions(lang)
                message = f'`{lang}` is not available.'
                if matches:
                    message += f' Did you mean:\n{matches}'
                return await ctx.send(message)

            if options['--wrapped']:
                if not (any(map(lambda x: lang.split('-')[0] == x, self.wrapping))) or lang in (
                'cs-mono-shell', 'cs-csi'):
                    return await ctx.send(f'`{lang}` cannot be wrapped')

                for beginning in self.wrapping:
                    if lang.split('-')[0] == beginning:
                        text = self.wrapping[beginning].replace('code', text)
                        break

            tio = Tio(lang, text, compiler_flags=compiler_flags, inputs=inputs,
                      command_line_options=command_line_options, args=args)

            result = await tio.send()

            if not options['--stats']:
                try:
                    start = result.rindex('Real time: ')
                    end = result.rindex('%\nExit code: ')
                    result = result[:start] + result[end + 2:]
                except ValueError:
                    # Too much output removes these markers
                    pass

            if len(result) > 1991 or result.count('\n') > 40:
                # If it exceeds 2000 characters (Discord message character limit), counting ` and ph\n characters
                # or if it floods with more than 40 lines
                # create a hastebin and send it back
                link = await self.paste(result)

                if link is None:
                    return await ctx.send("Your output was too long, but I couldn't make an online bin out of it")
                return await ctx.send(f'Output was too long (more than 2000 characters or 40 lines) '
                                      f'so I put it here: {link}')

            zero = '\u200b'
            result = re.sub('```', f'{zero}`{zero}`{zero}`{zero}', result)

            # ph, as placeholder, prevents Discord from taking the first line
            # as a language identifier for markdown and remove it.
            returned = await ctx.send(f'```ph\n{result}```')

        await returned.add_reaction('\U0001f5d1')
        returned_id = returned.id

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == '\U0001f5d1' and reaction.message.id == returned_id

        try:
            await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            pass
        else:
            await returned.delete()

    @run.command(name='list')
    async def _list(self, ctx, *, group=None):
        """Lists available choices for other commands."""
        choices = {
            "wrapped argument": self.wrapping,
        }
        if group == 'languages':
            emb = discord.Embed(title=f"Available for {group}: {len(self.languages)}",
                                description=f'View them on [tio.run](https://tio.run/#), '
                                            f'or in [JSON format](https://tio.run/languages.json)')
            return await ctx.send(embed=emb)

        if not group in choices:
            emb = discord.Embed(title="Available listed commands", description=f"`languages`, `{'`, `'.join(choices)}`")
            return await ctx.send(embed=emb)

        availables = choices[group]
        description = f"`{'`, `'.join([*availables])}`"
        emb = discord.Embed(title=f"Available for {group}: {len(availables)}", description=description)
        await ctx.send(embed=emb)

    @commands.command()
    async def man(self, ctx, *, page: str):
        """Returns the manual's page for a (mostly Debian) linux command."""

        base_url = f'https://man.cx/{page}'
        url = urllib.parse.quote_plus(base_url, safe=';/?:@&=$,><-[]')

        async with ctx.session.get(url) as resp:
            if resp.status != 200:
                return await ctx.send(f'An error occurred (status code: {resp.status}). Retry later.')

            soup = BeautifulSoup(await resp.text(), 'lxml')

            name_tag = soup.find('h2', string='NAME\n')

            if not name_tag:
                # No NAME, no page
                return await ctx.send(f'No manual entry for `{page}`. (Debian)')

            # Get the two (or less) first parts from the nav aside
            # The first one is NAME, we already have it in name_tag
            contents = soup.find_all('nav', limit=2)[1].find_all('li', limit=3)[1:]

            if contents[-1].string == 'COMMENTS':
                contents.remove(-1)

            title = self.get_content(name_tag)

            emb = discord.Embed(title=title, url=f'https://man.cx/{page}')
            emb.set_author(name='Debian Linux man pages')
            emb.set_thumbnail(url='https://www.debian.org/logos/openlogo-nd-100.png')

            for tag in contents:
                h2 = tuple(soup.find(attrs={'name': tuple(tag.children)[0].get('href')[1:]}).parents)[0]
                emb.add_field(name=tag.string, value=self.get_content(h2))

            await ctx.send(embed=emb)


def setup(bot):
    bot.add_cog(Code(bot))
