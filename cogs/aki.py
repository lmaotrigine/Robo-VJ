from discord.ext import commands, tasks
import discord
import asyncio
from akinator.async_aki import Akinator
import akinator
from .utils import db
from .utils.context import Context
from collections import defaultdict
from bot import RoboVJ

class AkiConfig(db.Table, table_name='aki_config'):
    user_id = db.Column(db.Integer(big=True), index=True, primary_key=True)
    language = db.Column(db.String(length=2, fixed=True), default='en')
    no_nsfw = db.Column(db.Boolean, default=False)

LANGUAGES = {
    'en': 'English',
    'ar': 'اَلْعَرَبِيَّةُ',
    'cn': '普通话',
    'de': 'Deutsch',
    'es': 'Español',
    'fr': 'Français',
    'il': 'עִבְרִית‎',
    'it': 'Italiano',
    'jp': '日本語',
    'kr': '한국어',
    'nl': 'Nederlands',
    'pl': 'Polski',
    'pt': 'português',
    'ru': 'Русский',
    'tr': 'Türkçe'
}

POSSIBLE_ANSWERS = ('yes', 'no', 'probably', 'probably not', 'idk', 'y', 'n', 'p', 'i', 'pn', 'b', 'back')

class _Akinator(commands.Cog, name='Akinator'):
    """Fairly simple Akinator implementation. This has not been tested extensively and may be unstable?
    
    Idk just report bugs if you find them."""
    def __init__(self, bot: RoboVJ):
        self.bot = bot
        self.in_play = defaultdict(set)

    def get_q_embed(self, ctx, question: str, num: int):
        embed = discord.Embed(title=f"Question {num + 1}: {question}")
        embed.set_author(name=self.bot.user.display_name, icon_url=self.bot.user.avatar.url)
        embed.set_footer(text=f'[{ctx.author}] | (y)es | (n)o | (i)dk | (p)robably | (pn)probably not | (b)ack')
        return embed

    def get_guess_embed(self, ctx, num_guesses: int, guess: dict):
        embed = discord.Embed(title=guess['name'], description=guess['description'])
        embed.set_author(name=self.bot.user.display_name, icon_url=self.bot.user.avatar.url)
        embed.set_image(url=guess['absolute_picture_path'])
        embed.set_footer(text=f'{ctx.author} | [Guess {num_guesses} / 3] Did I get it right? (y|n)')
        return embed

    @commands.group(name='aki')
    async def _aki(self, ctx: Context):
        """Akinator commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help('aki')

    @_aki.command(name='start')
    async def aki_start(self, ctx: Context):
        """Starts an Akinator session."""
        guild_id = None if ctx.guild is None else ctx.guild.id
        if ctx.author.id in self.in_play[guild_id]:
            return await ctx.send("You already have a game in progress. Please stop it first before continuing.")
        aki = Akinator()
        query = "SELECT language, no_nsfw FROM aki_config WHERE user_id = $1;"
        record = await ctx.db.fetchrow(query, ctx.author.id)
        if record is None:
            lang = 'en'
            child_mode = False
        else:
            lang = record['language']
            child_mode = record['no_nsfw']
        q = await aki.start_game(language=lang, child_mode=child_mode)
        q_num = 0
        self.in_play[guild_id].add(ctx.author.id)
        def guess_check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and m.content.lower() in POSSIBLE_ANSWERS

        def win_check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and m.content.lower() in ('y', 'n', 'yes', 'no')
        
        num_guesses = 0
        while num_guesses < 3:
            if ctx.author.id not in self.in_play[guild_id]:
                return
            if aki.progression > 80 or (num_guesses > 0 and aki.step >= 25):
                await aki.win()
                num_guesses += 1
                await ctx.send(embed=self.get_guess_embed(ctx, num_guesses, aki.first_guess))
                try:
                    msg = await self.bot.wait_for('message', check=win_check, timeout=60.0)
                except asyncio.TimeoutError:
                    await ctx.send('You took too long. Stopping your game. Goodbye.')
                    self.in_play[guild_id].discard(ctx.author.id)
                    return
                else:
                    if msg.content.lower() in ('yes', 'y'):
                        await ctx.send(embed=discord.Embed(title='Right again! Huzzah!'))
                        self.in_play[guild_id].discard(ctx.author.id)
                        return
                    if num_guesses == 3 and msg.content.lower() in ('no', 'n'):
                        await ctx.send(embed=discord.Embed(description=f'Bravo! {msg.author.mention}. You have defeated me.'))
                        self.in_play[guild_id].discard(ctx.author.id)
                        return
                    if msg.content.lower() in ('no', 'n'):
                        q = await aki.start()
                        q_num += 1
        
            await ctx.send(embed=self.get_q_embed(ctx, q, q_num))
            try:
                msg = await self.bot.wait_for('message', check=guess_check, timeout=60.0)
            except asyncio.TimeoutError:
                await ctx.send('You took too long. Stopping your game. Goodbye.')
                self.in_play[guild_id].discard(ctx.author.id)
                return
            if msg.content.lower() in ('back', 'b'):
                try:
                    q = await aki.back()
                    q_num -= 1
                except akinator.CantGoBackAnyFurther:
                    pass
            else:
                q = await aki.answer(msg.content.lower())
                q_num += 1
    
    @_aki.command(name='stop')
    async def aki_stop(self, ctx):
        """Stops your currently running game in this server or DM."""
        guild_id = None if ctx.guild is None else ctx.guild.id
        if ctx.author.id in self.in_play[guild_id]:
            self.in_play[guild_id].discard(ctx.author.id)
            await ctx.send(f'{ctx.author.mention} Stopped your game.')
        else:
            await ctx.send('You have no games in progress here.')

    @_aki.command(name='language', aliases=['lang'])
    async def aki_lang(self, ctx, language: str):
        """Change your preferred language. This applies globally for a user."""
        if language.lower() not in LANGUAGES.keys():
            embed = discord.Embed(title='Invalid language specified. Please enter a two-character language code from one of the following')
            embed.description = '\n'.join(f"**{key}**: {value}" for key, value in LANGUAGES.items())
            return await ctx.send(embed=embed)
        query = "INSERT INTO aki_config (user_id, language) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET language = $2;"
        await ctx.db.execute(query, ctx.author.id, language)
        await ctx.send(f"{ctx.author}, Your language has been set to {language}.")

    @_aki.command(name='nsfw')
    async def aki_set_nsfw(self, ctx, option: str=None):
        """Toggle NSFW guesses. This setting is ON by default."""
        if option is None:
            query = "SELECT no_nsfw FROM aki_config WHERE user_id = $1;"
            record = await ctx.db.fetchval(query, ctx.author.id)
            if record is None:
                return await ctx.send(f"NSFW mode is ON for {ctx.author}. Aki will ask you questions about things that are NSFW.")
            else:
                if not record:
                    return await ctx.send(f"NSFW mode is ON for {ctx.author}. Aki will ask you questions about things that are NSFW.")
                else:
                    return await ctx.send(f"NSFW mode is OFF for {ctx.author}. Aki will not ask you questions about things that are NSFW.")
        else:
            query = "INSERT INTO aki_config (user_id, no_nsfw) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET no_nsfw = $2;"
            if option.lower() not in ('on', 'off'):
                return await ctx.send("Invalid option specified. Must be either 'on' or 'off'.")
            if option.lower() == 'on':
                await ctx.db.execute(query, ctx.author.id, False)
                return await ctx.send(f"NSFW mode is ON for {ctx.author}. Aki will ask you questions about things that are NSFW.")
            elif option.lower() == 'off':
                await ctx.db.execute(query, ctx.author.id, True)
                return await ctx.send(f"NSFW mode is OFF for {ctx.author}. Aki will not ask you questions about things that are NSFW.")
    
async def setup(bot: RoboVJ):
    await bot.add_cog(_Akinator(bot))
