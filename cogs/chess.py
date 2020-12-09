import discord
from discord.ext import commands

import asyncio
import datetime
import io
import random
import subprocess
from typing import Union

import chess
import chess.engine
import chess.pgn
import chess.svg
import cpuinfo

from wand.image import Image

# TODO: Dynamically load chess engine not locked to version?
STOCKFISH_BINARY = 'stockfish_20090216_x64'
try:
    CPUID = cpuinfo.CPUID()
    CPU_FLAGS = CPUID.get_flags(CPUID.get_max_extension_support())
    if 'bmi2' in CPU_FLAGS:
        STOCKFISH_BINARY += '_bmi2'
    elif 'avx2' in CPU_FLAGS:
        STOCKFISH_BINARY += '_avx2'
    elif 'sse4_1' in CPU_FLAGS:
        STOCKFISH_BINARY += '_modern'
    elif 'ssse3' in CPU_FLAGS:
        STOCKFISH_BINARY += '_ssse'
    # BMI2 >= AVX2 > SSE4.1 + POPCNT (modern) >= SSSE3 > none
    # https://stockfishchess.org/download/
    # TODO: Handle 32-bit?
    # TODO: Handle non-Linux?
except:
    pass


class ChessCog(commands.Cog, name='Chess'):
    def __init__(self):
        self.matches = []

    def cog_unload(self):
        # TODO: Persistence - store running chess matches and add a way to continue previous ones
        for match in self.matches:
            match.task.cancel()

    @commands.group(name='chess', invoke_without_command=True)
    async def chess_command(self, ctx):
        """
        Play chess
        Supports standard algebraic and UCI notation.
        Example:
            !chess play you
            white
            e2e4
        """
        await ctx.send_help(ctx.command)

    # TODO: Use max_concurrency?
    @chess_command.command(aliases=['start'])
    async def play(self, ctx, *, opponent: Union[discord.Member, str]):
        """
        Challenge someone to a match.
        You can play me as well.
        """
        if self.get_match(ctx.channel, ctx.author):
            return await ctx.reply(':no_entry: You\'re already playing a chess match here.')
        colour = None
        if type(opponent) is str:
            if opponent.lower() in ('you', 'robo vj'):
                opponent = ctx.bot.user
            elif opponent.lower() in ('myself', 'me'):
                opponent = ctx.author
                colour = 'w'
            else:
                return await ctx.reply(':no_entry: Opponent not found.')
        if opponent != ctx.bot.user and self.get_match(ctx.channel, opponent):
            return await ctx.reply(':no_entry: Your chosen opponent is playing a chess match here.')
        if opponent == ctx.author:
            colour = 'w'
        if not colour:
            await ctx.reply('Would you like to play white, black or random?')
            message = await ctx.bot.wait_for('message',
                                             check=lambda m: m.author == ctx.author and m.channel == ctx.channel and
                                             m.content.lower() in ('white', 'black', 'random',
                                                                   'w', 'b', 'r'))
            colour = message.content.lower()
        if colour in ('random', 'r'):
            colour = random.choice(('w', 'b'))
        if colour in ('white', 'w'):
            white_player = ctx.author
            black_player = opponent
        elif colour in ('black', 'b'):
            white_player = opponent
            black_player = ctx.author
        if opponent != ctx.bot.user and opponent != ctx.author:
            await ctx.send(f'{opponent.mention}: {ctx.author.mention} has challenged you to a chess match\n'
                           'Would you like to accept? Yes/No')
            try:
                message = await ctx.bot.wait_for('message',
                                                 check=lambda m: m.author == opponent and m.channel == ctx.channel and
                                                 m.content.lower() in ('yes', 'no', 'y', 'n'),
                                                 timeout=300.0)
            except asyncio.TimeoutError:
                return await ctx.send(f'{ctx.author.mention}: {opponent} has not accepted your challenge.')
            if message.content.lower() in ('no', 'n'):
                return await ctx.send(f'{ctx.author.mention}: {opponent} has declined your challenge.')
        match = await ChessMatch.start(ctx, white_player, black_player)
        self.matches.append(match)
        await match.ended.wait()
        self.matches.remove(match)

    def get_match(self, text_channel, player):
        return discord.utils.find(lambda match: match.ctx.channel == text_channel and
                                  (match.white_player == player or match.black_player == player),
                                  self.matches)

    # TODO: Handle matches in DMs
    # TODO: Allow resignation
    # TODO: Allow draw offers

    @chess_command.group(aliases=['match'], invoke_without_command=True)
    async def board(self, ctx):
        """Current match/board"""
        match = self.get_match(ctx.channel, ctx.author)
        if not match:
            return await ctx.reply(':no_entry: Chess match not found.')
        await match.mew_match_embed()

    @board.command(name='text')
    async def board_text(self, ctx):
        """Text version of the current board"""
        match = self.get_match(ctx.channel, ctx.author)
        if not match:
            return await ctx.reply(':no_entry: Chess match not found.')
        await ctx.reply(f'```\n{match}\n```')

    @chess_command.command()
    async def fen(self, ctx):
        """FEN of the current board."""
        match = self.get_match(ctx.channel, ctx.author)
        if not match:
            return await ctx.reply(':no_entry: Chess match not found.')
        await ctx.reply(match.fen())

    @chess_command.command(hidden=True)
    async def pgn(self, ctx):
        """PGN of the current game."""
        match = self.get_match(ctx.channel, ctx.author)
        if not match:
            return await ctx.reply(':no_entry: Chess match not found.')
        await ctx.reply(chess.pgn.Game.from_board(match))

    @chess_command.command(aliases=['last'], hidden=True)
    async def previous(self, ctx):
        """Previous move."""
        match = self.get_match(ctx.channel, ctx.author)
        if not match:
            return await ctx.reply(':no_entry: Chess match not found.')
        try:
            await ctx.reply(match.peek())
        except IndexError:
            await ctx.reply(':no_entry: There was no previous move.')

    @chess_command.command(hidden=True)
    async def turn(self, ctx):
        """Whose turn is it to move?"""
        match = self.get_match(ctx.channel, ctx.author)
        if not match:
            return await ctx.reply(':no_entry: Chess match not found.')
        if match.turn:
            await ctx.reply('It\'s white\'s turn to move.')
        else:
            await ctx.reply('It\'s black\'s turn to move.')


class ChessMatch(chess.Board):

    @classmethod
    async def start(cls, ctx, white_player, black_player):
        self = cls()
        self.ctx = ctx
        self.white_player = white_player
        self.black_player = black_player
        self.bot = ctx.bot
        self.ended = asyncio.Event()
        self.engine_transport, self.chess_engine = \
            await chess.engine.popen_uci(f'bin/{STOCKFISH_BINARY}')
        self.match_message = None
        self.task = ctx.bot.loop.create_task(self.match_task(), name='Chess Match')
        return self

    def make_move(self, move):
        try:
            self.push_san(move)
        except ValueError:
            try:
                self.push_uci(move)
            except ValueError:
                return False
        return True

    def valid_move(self, move):
        try:
            self.parse_san(move)
        except ValueError:
            try:
                self.parse_uci(move)
            except ValueError:
                return False
        return True

    async def match_task(self):
        self.match_message = await self.ctx.send(embed=discord.Embed(description='Loading...'))
        await self.update_match_embed()
        while not self.ended.is_set():
            player = [self.black_player, self.white_player][int(self.turn)]
            embed = self.match_message.embeds[0]
            if player == self.bot.user:
                await self.match_message.edit(embed=embed.set_footer(text='I\'m thinking...'))
                result = await self.chess_engine.play(self, chess.engine.Limit(time=2))
                self.push(result.move)
                await self.update_match_embed(footer_text=f'I moved {result.move}')
            else:
                message = await self.bot.wait_for('message',
                                                  check=lambda m: m.author == player and m.channel == self.ctx.channel
                                                  and self.valid_move(m.content))
                await self.match_message.edit(embed=embed.set_footer(text='Processing move...'))
                self.make_move(message.content)
                if self.is_game_over():
                    footer_text = discord.Embed.Empty
                    self.ended.set()
                else:
                    footer_text = f'It is {["black", "white"][int(self.turn)]}\'s ' \
                                  f'({[self.black_player, self.white_player][int(self.turn)]}\'s) turn to move.'
                await self.update_match_embed(footer_text=footer_text)
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

    async def update_match_embed(self, *, orientation=None, footer_text=discord.Embed.Empty):
        if orientation is None:
            orientation = self.turn
        if self.move_stack:
            lastmove = self.peek()
        else:
            lastmove = None
        if self.is_check():
            check = self.king(self.turn)
        else:
            check = None
        if self.match_message:
            embed = self.match_message.embeds[0]
        else:
            embed = discord.Embed()
        chess_pgn = chess.pgn.Game.from_board(self)
        chess_pgn.headers['Site'] = 'Discord'
        chess_pgn.headers['Date'] = datetime.datetime.utcnow().strftime('%Y.%m.%d')
        chess_pgn.headers['White'] = self.white_player.mention
        chess_pgn.headers['Black'] = self.black_player.mention
        embed.description = str(chess_pgn)
        svg = chess.svg.board(self, lastmove=lastmove, check=check, orientation=orientation)
        buffer = io.BytesIO()
        with Image(blob=svg.encode()) as image:
            image.format = 'PNG'
            image.save(file=buffer)
        buffer.seek(0)
        # TODO: Upload into embed + delete and re-send to update?
        image_message = await self.bot.get_channel(786201668982538240).send(file=discord.File(buffer,
                                                                                              filename='chess_board.png'
                                                                                              ))
        embed.set_image(url=image_message.attachments[0].url)
        embed.set_footer(text=footer_text)
        if self.match_message:
            await self.match_message.edit(embed=embed)
        else:
            self.match_message = await self.ctx.send(embed=embed)

    async def new_match_embed(self, *, orientation=None, footer_text=None):
        if orientation is None:
            orientation = self.turn
        if footer_text is None:
            if self.is_game_over():
                footer_text = discord.Embed.Empty
            else:
                footer_text = f'It\'s {["black", "white"][int(self.turn)]}\'s ' \
                              f'({[self.black_player, self.white_player][int(self.turn)]}\'s) turn to move.'
        if self.match_message:
            await self.match_message.delete()
        self.match_message = None
        await self.update_match_embed(orientation=orientation, footer_text=footer_text)


def setup(bot):
    bot.add_cog(ChessCog())
