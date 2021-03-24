import asyncpg
import aiohttp
import discord
from discord.ext import commands
import re
from .utils import db

GUILD_ID = 824219708827369512
UPLOADS_ID = 824236694210478121 
ADMINS_ID = 824321929812508724

FILE_REGEX = re.compile(r'^(?P<id>\w+)_(?P<language>TA|UR|HI|BN|KA|PA)\.(?P<extension>pdf|odt|doc|docx)$')
URL_REGEX = re.compile(r'^https?://(www\.)?instagram\.com/p/(?P<id>[^\W/]+)/?$')


def is_admin():
    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        return ctx.author._roles.has(ADMINS_ID)
    return commands.check(predicate)


class PostConverter(commands.Converter):
    def __init__(self, _id=None, language=None):
        self.id = id
        self.language = language

    @classmethod
    async def convert(cls, ctx, argument):
        _id = argument
        if match := URL_REGEX.match(argument):
            _id = match.group('id')
        return cls(_id)


class FileConverter(PostConverter):
    @classmethod
    async def convert(cls, ctx, argument):
        if match := FILE_REGEX.match(argument):
            _id = match.group('id')
            language = match.group('language')
        if await cls.validate_id(ctx.bot, _id):
            return cls(_id, language)
        raise commands.BadArgument(f'Filename `{argument}` is not valid.')

    @classmethod
    async def validate_id(cls, bot, _id):
        rec = await bot.pool.fetchrow('SELECT * FROM naarivad_posts WHERE id = $1;', _id)
        if not rec:
            url = f'https://instagram.com/naarivad.in/p/{_id}'
            async with bot.session.get(url) as resp:
                if resp.status == 200:
                    raise commands.BadArgument(f'The post `{_id}` was found, but not added to the database. Take this '
                                               f'up with the admins.')
        return True


class NaarivadPosts(db.Table, table_name='naarivad_posts'):
    id = db.Column(db.String, primary_key=True)
    translated_into = db.Column(db.Array(db.String(length=3)))


class Naarivad(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_check(self, ctx):
        return ctx.guild and ctx.guild.id == GUILD_ID

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            return await ctx.send('Only page admins can run this command.')
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(str(error))
        if isinstance(error, commands.BadArgument):
            return await ctx.send(str(error))

    @commands.Cog.listener('on_message')
    async def auto_upload(self, message):
        if message.guild is None or message.guild.id != GUILD_ID:
            return
        if message.channel.id != UPLOADS_ID:
            return
        if not message.attachments:
            return
        statuses = {}
        for attachment in message.attachments:
            try:
                post = await FileConverter.convert(await self.bot.get_context(message), attachment.filename)
            except commands.BadArgument as e:
                await message.channel.send(f'{e}. Skipping upload.')
                continue
            stat = await self.upload(attachment, post)
            statuses[attachment.filename] = stat
        await message.channel.send('\n'.join(f'`{key}`: status {val}' for key, val in statuses.items()))

    async def upload(self, attachment, post):
        bytes_ = await attachment.read()
        headers = {'Authorization': self.bot.config.naarivad_upload_token}
        data = aiohttp.FormData()
        data.add_field('fileupload', bytes_, filename=attachment.filename)
        async with self.bot.session.post('https://docs.naarivad.in/upload', data=data, headers=headers) as resp:
            stat = resp.status
        if stat == 200:
            await self.update(post)
        return stat

    @commands.command(name='notify_upload')
    @is_admin()
    async def notify(self, ctx, post_id: PostConverter):
        try:
            await ctx.db.execute('INSERT INTO naarivad_posts (id, translated_into) VALUES ($1, $2);', post_id.id, [])
        except asyncpg.UniqueViolationError:
            return await ctx.send('This post already exists in the database.')
        await ctx.send(ctx.tick(True))

    async def update(self, post):
        async with self.bot.pool.acquire() as con:
            query = "SELECT translated_into FROM naarivad_posts WHERE id = $1;"
            langs = await con.fetchrow(query, post.id)
            if post.language not in langs:
                langs.append(post.language)
            query = 'UPDATE naarivad_posts SET translated_into = $1 WHERE id = $2;'
            await con.execute(query, langs, post.id)


def setup(bot):
    bot.add_cog(Naarivad(bot))
