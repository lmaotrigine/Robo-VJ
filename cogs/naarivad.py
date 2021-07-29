import asyncpg
import aiohttp
import discord
from discord.ext import commands
import re
from .utils import db

GUILD_ID = 824219708827369512
UPLOADS_ID = 824236694210478121 
ADMINS_ID = 824321929812508724
TRANSLATORS_ID = 824583293562388500

FILE_REGEX = re.compile(r'^(?P<id>[A-Za-z0-9\-_]+)_(?P<language>TA|UR|HI|BN|KA|PA)\.(?P<extension>pdf|odt|doc|docx)$')
URL_REGEX = re.compile(r'^<?https?://(www\.)?instagram\.com/(naarivad\.in/)?p/(?P<id>[A-Za-z0-9_\-]+)/?>?$')


def is_admin():
    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        return ctx.author._roles.has(ADMINS_ID)
    return commands.check(predicate)


def is_translator():
    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        return ctx.author._roles.has(TRANSLATORS_ID)
    return commands.check(predicate)


def is_translator_or_admin():
    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        return ctx.author._roles.has(TRANSLATORS_ID) or ctx.author._roles.has(ADMINS_ID)
    return commands.check(predicate)


class PostConverter(commands.Converter):
    def __init__(self, _id=None, language=None):
        self.id = _id
        self.language = language

    async def convert(self, ctx, argument):
        if match := URL_REGEX.match(argument):
            self.id = match.group('id')
        else:
            raise commands.BadArgument('This is not a valid Instagram post URL.')
        return self


class FileConverter(PostConverter):
    async def convert(self, ctx, argument):
        _id = None
        language = None
        if match := FILE_REGEX.match(argument):
            _id = match.group('id')
            language = match.group('language')
        if await self.validate_id(ctx.bot, _id):
            self.id = _id
            self.language = language
            return self
        raise commands.BadArgument(f'Filename `{argument}` is not valid.')

    async def validate_id(self, bot, _id):
        async with bot.session.get(f'https://backend.naarivad.in/{_id}') as r:
            if r.status == 404:
                raise commands.BadArgument(f'Post with ID `{_id}` doesn\'t exist in the database. '
                                           f'Take this up with admins or VJ.')
        return True


class Naarivad(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.webhook = discord.Webhook.partial(*bot.config.naarivad_webhook, session=bot.session)

    def cog_check(self, ctx):
        return ctx.guild and ctx.guild.id == GUILD_ID

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(str(error))
        if isinstance(error, commands.BadArgument):
            return await ctx.send(str(error))

    @commands.Cog.listener('on_message')
    async def auto_upload(self, message):
        if message.author.bot:
            return
        if message.guild is None or message.guild.id != GUILD_ID:
            return
        if message.channel.id != UPLOADS_ID:
            return
        if not message.attachments:
            return
        statuses = {}
        for attachment in message.attachments:
            try:
                await FileConverter().convert(await self.bot.get_context(message), attachment.filename)
            except commands.BadArgument as e:
                await message.channel.send(f'{e}. Skipping upload.')
                continue
            stat = await self.upload(attachment)
            statuses[attachment.filename] = stat
        await self.webhook.send('\n'.join(f'[`{key}`](https://docs.naarivad.in/{key}): status {val}' for key, val in statuses.items()))

    async def upload(self, attachment):
        bytes_ = await attachment.read()
        headers = {'Authorization': self.bot.config.naarivad_upload_token}
        data = aiohttp.FormData()
        data.add_field('file', bytes_, filename=attachment.filename)
        async with self.bot.session.post('https://docs.naarivad.in/upload', data=data, headers=headers) as resp:
            stat = resp.status
        return stat

    @commands.command(aliases=['notify_upload'])
    @is_admin()
    async def notify(self, ctx, *post_urls: PostConverter):
        """Add the ID of an uploaded post to the database so that translation auto-uploads validate for it.

        This takes an arbitrary number of valid Instagram URLs.

        Any post that is not notified to the bot through this command will not pass the filename validator and uploads
        of translations will fail.
        """
        posts = list(post_urls)
        description = 'Unknown Post'
        headers = {
            'Authorization': ctx.bot.config.naarivad_backend_auth,
            'X-Post-Description': description,
        }
        if not post_urls:
            return await ctx.send_help(ctx.command)
        for post_id in post_urls:
            headers['X-Post-Url'] = f'https://www.instagram.com/p/{post_id.id}'
            async with self.bot.session.get(f'https://backend.naarivad.in/{post_id.id}') as r:
                if r.status == 200:
                    await ctx.send(f'`{post_id.id}` exists. Skipping.')
                    posts.remove(post_id)
                    continue
            async with self.bot.session.post('https://backend.naarivad.in/update', headers=headers) as res:
                js = await res.json()
            if js['message']:
                return await ctx.send(js['message'])

        await ctx.send(f'{ctx.tick(True)} post{"s" if len(posts) != 1 else ""} ha{"ve" if len(posts) != 1 else "s"} '
                       f'been updated in the database\n'
                       f'{chr(10).join(f"https://instagram.com/p/{post_url.id}" for post_url in posts)}\n'
                       f'<@&{TRANSLATORS_ID}>')

    @commands.command()
    async def status(self, ctx):
        """Fetch translation status of posts in the database."""
        await ctx.send('Deprecated in favour of <https://trello.naarivad.in> and <https://docs.naarivad.in/tree/>')

    @commands.command()
    @is_admin()
    async def describe(self, ctx, post: PostConverter, *, description: str):
        """Provide a user-friendly description to a post.

        This is useful for Trello etc.
        Also shows up in https://backend.naarivad.in/posts
        """
        headers = {
            'Authorization': ctx.bot.config.naarivad_backend_auth,
            'X-Post-Url': f'https://www.instagram.com/p/{post.id}',
            'X-Post-Description': description,
        }
        async with self.bot.session.post('https://backend.naarivad.in/update', headers=headers) as r:
            js = r.json()
        return await ctx.send(str(js))


def setup(bot):
    bot.add_cog(Naarivad(bot))
