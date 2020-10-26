import discord
from discord.ext import commands
from cogs.utils.formats import human_join
import asyncio
import base64
import binascii
import re
import yarl

TOKEN_REGEX = re.compile(r'[a-zA-z0-9_-]{23,28}\.[a-zA-Z0-9_-]{6,7}\.[a-zA-Z0-9_-]{27}')
ROBO_VJ_GUILD = 746769944774967440

def validate_token(token):
    try:
        # Just check if the first part validates as a User ID
        (user_id, _, _) = token.split('.')
        user_id = int(base64.b64decode(user_id, validate=True))
    except (ValueError, binascii.Error):
        return False
    else:
        return True

class GithubError(commands.CommandError):
    pass

class Github(commands.Cog):
    """GitHub API things, mostly just uploading files and tracking issues."""

    def __init__(self, bot):
        self.bot = bot
        self.issue = re.compile(r'##(?P<number>[0-9]+)')
        self._req_lock = asyncio.Lock(loop=self.bot.loop)
    
    def cog_check(self, ctx):
        return ctx.guild and ctx.guild.id == ROBO_VJ_GUILD

    async def cog_command_error(self, ctx, error):
        if isinstance(error, GithubError):
            await ctx.send(f"GitHub Error: {error}")
    
    async def github_request(self, method, url, *, params=None, data=None, headers=None):
        hdrs = {
            'Accept': 'application/vnd.github.inertia-preview+json',
            'User-Agent': 'Robo-VJ Github Cog',
            'Authorization': f'token {self.bot.config.github_token}'
        }
        req_url = yarl.URL('https://api.github.com') / url

        if headers is not None and isinstance(headers, dict):
            hdrs.update(headers)

        await self._req_lock.acquire()
        try:
            async with self.bot.session.request(method, req_url, params=params, json=data, headers=hdrs) as r:
                remaining = r.headers.get('X-Ratelimit-Remaining')
                js = await r.json()
                if r.status == 429 or remaining == '0':
                    # wait before we release the lock
                    delta = discord.utils._parse_ratelimit_header(r)
                    await asyncio.sleep(delta)
                    self._req_lock.release()
                    return await self.github_request(method, url, params=params, data=data, headers=headers)
                elif 300 > r.status >=200:
                    return js
                else:
                    raise GithubError(js['message'])
        finally:
            if self._req_lock.locked():
                self._req_lock.release()

    async def create_gist(self, content, *, description=None, filename=None, public=True):
        headers = {
            'Accept': 'application/vnd.github.v3+json',
        }

        filename = filename or 'output.txt'
        data = {
            'public': public,
            'files': {
                filename: {
                    'content': content
                }
            }
        }

        if description:
            data['description'] = description

        js = await self.github_request('POST', 'gists', data=data, headers=headers)
        return js['html_url']

    async def redirect_attachments(self, message):
        attachment = message.attachments[0]
        if not attachment.filename.endswith(('.txt', '.py', '.json')):
            return
        
        # If this file is more than 2MiB, then it's definitely too big
        if attachment.size > (2 * 1024 * 1024):
            return

        try:
            contents = await attachment.read()
            contents = contents.decode('utf-8')
        except (UnicodeDecodeError, discord.HTTPException):
            return

        description = f'A file by {message.author} in the Robo-VJ guild'
        gist = await self.create_gist(contents, description=description, filename=attachment.filename)
        await message.channel.send(f'File automatically uploaded to gist: <{gist}>')

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.guild.id != ROBO_VJ_GUILD:
            return

        tokens = [token for token in TOKEN_REGEX.findall(message.content) if validate_token(token)]
        if tokens and message.author.id != self.bot.user.id:
            url = await self.create_gist('\n'.join(tokens), description='Discord tokens detected')
            msg = f'{message.author.mention}, I have found tokens and sent them to <{url}> to be invalidated for you.'
            return await message.channel.send(msg)

        if message.author.bot:
            return

        m = self.issue.search(message.content)
        if m is not None:
            url = 'https://github.com/darthshittious/Robo-VJ/issues/'
            await message.channel.send(url + m.group('number'))
    
    async def get_valid_labels(self):
        labels = await self.github_request('GET', 'repos/darthshittious/Robo-VJ/labels')
        return {e['name'] for e in labels}

    async def edit_issue(self, number, *, labels=None, state=None):
        url_path = f'repos/darthshittious/Robo-VJ/issues/{number}'
        issue = await self.github_request('GET', url_path)
        if issue.get('pull_request'):
            raise GithubError('That is a pull request, not an issue.')

        current_state = issue.get('state')
        if state == 'closed' and current_state == 'closed':
            raise GithubError('This issue is already closed.')

        data = {}
        if state:
            data['state'] = state

        if labels:
            current_labels = {e['name'] for e in issue.get('labels', [])}
            valid_labels = await self.get_valid_labels()
            labels = set(labels)
            diff = [repr(x) for x in (labels - valid_labels)]
            if diff:
                raise GithubError(f'Invalid labels passed: {human_join(diff, final="and")}')
            data['labels'] = list(current_labels | labels)

        return await self.github_request('PATCH', url_path, data=data)

    @commands.group(aliases=['gh'])
    async def github(self, ctx):
        """GitHub administration commands."""
        pass

    @github.command(name='close')
    @commands.is_owner()
    async def github_close(self, ctx, number:int, *labels):
        """Closes and optionally labels an issue."""
        js = await self.edit_issue(number, labels=labels, state='closed')
        await ctx.send(f'Successfully closed <{js["html_url"]}>')

    @github.command(name='open')
    @commands.is_owner()
    async def github_open(self, ctx, number: int):
        """Re-open an issue."""
        js = await self.edit_issue(number, state='open')
        await ctx.send(f'Successfully reopened <{js["html_url"]}>')

    @github.command(name='label')
    @commands.is_owner()
    async def github_label(self, ctx, number: int, *labels):
        """Adds labels to an issue."""
        if not labels:
            await ctx.send("Missing labels to assign.")
        js = await self.edit_issue(number, labels=labels)
        await ctx.send(f'Successfully labelled <{js["html_url"]}>')

def setup(bot):
    bot.add_cog(Github(bot))