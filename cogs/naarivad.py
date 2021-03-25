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

FILE_REGEX = re.compile(r'^(?P<id>\w+)_(?P<language>TA|UR|HI|BN|KA|PA)\.(?P<extension>pdf|odt|doc|docx)$')
URL_REGEX = re.compile(r'^<?https?://(www\.)?instagram\.com/(naarivad\.in/)?p/(?P<id>[^\W/]+)/?>?$')


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
        self.id = id
        self.language = language

    async def convert(self, ctx, argument):
        if match := URL_REGEX.match(argument):
            self.id = match.group('id')
        else:
            raise commands.BadArgument('This is not a valid Instagram post URL.')
        return self


class FileConverter(PostConverter):
    async def convert(self, ctx, argument):
        if match := FILE_REGEX.match(argument):
            _id = match.group('id')
            language = match.group('language')
        if await self.validate_id(ctx.bot, _id):
            self.id = _id
            self.language = language
            return self
        raise commands.BadArgument(f'Filename `{argument}` is not valid.')

    async def validate_id(self, bot, _id):
        rec = await bot.pool.fetchrow('SELECT * FROM naarivad_posts WHERE id = $1;', _id)
        if not rec:
            url = f'https://instagram.com/naarivad.in/p/{_id}'
            async with bot.session.get(url) as resp:
                if resp.status == 200:
                    raise commands.BadArgument(f'The post `{_id}` was found, but not added to the database. Take this '
                                               f'up with the admins.')
                else:
                    raise commands.BadArgument(f'The post `{_id}` was not found. Check the ID once again.')
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
                post = await FileConverter().convert(await self.bot.get_context(message), attachment.filename)
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
    async def notify(self, ctx, *post_urls: PostConverter):
        """Add the ID of an uploaded post to the database so that translation auto-uploads validate for it.

        This takes an arbitrary number of valid Instagram URLs.

        Any post that is not notified to the bot through this command will not pass the filename validator and uploads
        of translations will fail.
        """
        posts = list(post_urls)
        for post_id in post_urls:
            try:
                await ctx.db.execute('INSERT INTO naarivad_posts (id, translated_into) VALUES ($1, $2);', post_id.id, [])
            except asyncpg.UniqueViolationError:
                await ctx.send(f'The post {post_id.id} already exists in the database. Skipping.')
                posts.remove(post_id)
        await ctx.send(f'{ctx.tick(True)} post{"s" if len(posts) != 1 else ""} have been updated in the database\n'
                       f'{chr(10).join(f"https://instagram.com/p/{post_url}" for post_url in posts)}\n'
                       f'<@&{TRANSLATORS_ID}>')

    async def update(self, post):
        async with self.bot.pool.acquire() as con:
            query = "SELECT translated_into FROM naarivad_posts WHERE id = $1;"
            langs = await con.fetchval(query, post.id)
            if post.language not in langs:
                langs.append(post.language)
            query = 'UPDATE naarivad_posts SET translated_into = $1 WHERE id = $2;'
            await con.execute(query, langs, post.id)

    @commands.command()
    async def status(self, ctx):
        records = await ctx.db.fetch("SELECT * FROM naarivad_posts;")
        res = []
        for record in records:
            text = f'<https://instagram.com/p/{record["id"]}>: '
            if record['translated_into']:
                text += ", ".join(record["translated_into"])
            else:
                text += 'None'
            res.append(text)
        embed = discord.Embed(colour=discord.Colour.blurple(), title='Completed Translations')
        embed.description = '\n'.join(res)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Naarivad(bot))
