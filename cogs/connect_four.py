from asyncio import ensure_future
import random
from typing import List, Tuple, Optional, Union, Iterable

import discord
from discord.ext import commands, menus


REGIONAL_INDICATOR_EMOJI = (
    '\N{REGIONAL INDICATOR SYMBOL LETTER A}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER B}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER C}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER D}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER E}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER F}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER G}',
)


ROWS = 6
COLUMNS = 7

BACKGROUND = '\N{BLACK CIRCLE FOR RECORD}\N{VARIATION SELECTOR-16}'
DISCS = ('\N{LARGE RED CIRCLE}', '\N{LARGE YELLOW CIRCLE}')

DIRECTIONS = ((1, 0), (0, 1), (1, -1), (1, 1))


class Board:

    def __init__(self, *, state: List[List[str]] = None, move: Tuple[Tuple[int, int], str] = None):
        self.columns = state or [[BACKGROUND for _ in range(ROWS)] for _ in range(COLUMNS)]
        if move is not None:
            self.last_move, disc = move
            column, row = self.last_move
            self.columns[column][row] = disc
        else:
            self.last_move = None
            disc = DISCS[1]

        self.current_player = not DISCS.index(disc)
        self.winner = None
        self.game_over = self.check_game_over()
        
    @property
    def legal_moves(self) -> List[int]:
        return [i for i, column in enumerate(self.columns) if column.count(BACKGROUND)]

    def copy(self, *, move=None):
        return Board(state=[[state for state in column] for column in self.columns], move=move)

    def check_game_over(self) -> bool:
        if self.last_move is None:
            return False

        column, row = self.last_move
        disc = self.columns[column][row]
        # Check if last move was winning move
        counts = [0 for _ in range(4)]
        for i in range(-3, 4):

            # Shortcut for the last played disc
            if i == 0:
                for n in range(4):
                    counts[n] += 1
            else:
                # horizontal
                if 0 <= column + i < COLUMNS:
                    if self.columns[column + i][row] == disc:
                        counts[0] += 1
                    else:
                        counts[0] = 0

                if 0 <= row + i < ROWS:
                    # vertical
                    if self.columns[column][row + i] == disc:
                        counts[1] += 1
                    else:
                        counts[1] = 0

                    # descending
                    if 0 <= column + i < COLUMNS:
                        if self.columns[column + i][row + i] == disc:
                            counts[2] += 1
                        else:
                            counts[2] = 0

                    # ascending
                    if 0 <= column - i < COLUMNS:
                        if self.columns[column - i][row + i] == disc:
                            counts[3] += 1
                        else:
                            counts[3] = 0

            for count in counts:
                if count >= 4:
                    self.winner = DISCS.index(disc)
                    return True

        # No moves left draw
        return len(self.legal_moves) == 0

    def move(self, column: int, disc: str):
        row = self.columns[column].index(BACKGROUND)
        return self.copy(move=((column, row), disc))


class Game(menus.Menu):
    async def send_initial_message(self, ctx, channel):
        current_player = self.board.current_player
        return await channel.send(content=f'{self.players[current_player].mention}\'s ({DISCS[current_player]}) turn!',
                                  embed=self.state)

    def reaction_check(self, payload):
        if payload.message_id != self.message.id:
            return False

        current_player = self.board.current_player
        if payload.user_id != self.players[current_player].id:
            return False

        return payload.emoji in self.buttons

    @property
    def state(self):
        state = ' '.join(REGIONAL_INDICATOR_EMOJI)

        for row in range(ROWS):
            emoji = []
            for column in range(COLUMNS):
                emoji.append(self.board.columns[column][row])

            state = ' '.join(emoji) + '\n' + state

        return discord.Embed(description=state)

    async def start(self, ctx, opponent, *, channel=None, wait=False):
        self.draw = False

        if random.random() < 0.5:
            self.players = (ctx.author, opponent)
        else:
            self.players = (opponent, ctx.author)

        self.board = Board()

        self.is_bot = True

        # setup buttons
        for emoji in REGIONAL_INDICATOR_EMOJI:
            self.add_button(menus.Button(emoji, self.place))
        self.add_button(menus.Button('\N{BLACK SQUARE FOR STOP}\N{VARIATION SELECTOR-16}', self.cancel))

        await super().start(ctx, channel=channel, wait=wait)

    async def _end_game(self):
        if self.board.winner is not None:
            content = f'{self.players[self.board.winner].mention} ({DISCS[self.board.winner]}) Wins!'
        else:
            content = 'Draw!'

        await self.message.edit(content=f'Game over! {content}', embed=self.state)

    async def place(self, payload):
        column = REGIONAL_INDICATOR_EMOJI.index(str(payload.emoji))
        if column not in self.board.legal_moves:
            return

        self.board = self.board.move(column, DISCS[self.board.current_player])

        if self.board.game_over:
            return await self._end_game()

        current_player = self.board.current_player
        await self.message.edit(content=f'{self.players[current_player].mention}\'s ({DISCS[current_player]}) turn!',
                                embed=self.state)

    async def cancel(self, payload):
        current_player = self.board.current_player
        await self.message.edit(content=f'Game cancelled by {self.players[current_player].mention} ({DISCS[current_player]})!',
                                embed=self.state)
        self.stop()


class ConnectFour(commands.Cog, name='Connect Four'):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['connect4'])
    async def c4(self, ctx, *, opponent: discord.Member):
        if opponent.bot:
            return await ctx.send('You cannot play against a bot yet.')
        if opponent == ctx.author:
            return await ctx.send('You cannot play against yourself.')

        if await confirm(self.bot, f'{opponent.mention}, {ctx.author} has challenged you to Connect 4! Do you accept?',
                         opponent, channel=ctx.channel):
            await Game().start(ctx, opponent, wait=True)


async def confirm(bot: commands.Bot, message: Union[str, discord.Message], user: discord.User, *, channel: Optional[discord.TextChannel] = None, timeout=60, delete_after=True):
    if isinstance(message, str):
        message = await channel.send(message)

    confirm = False
    reactions = ['\N{thumbs up sign}', '\N{thumbs down sign}']

    def check(payload):
        if payload.message_id == message.id and payload.user_id == user.id:
            if str(payload.emoji) in reactions:
                return True
        return False

    await add_reactions(message, reactions)

    try:
        payload = await bot.wait_for('raw_reaction_add', check=check, timeout=timeout)
        if str(payload.emoji) == '\N{thumbs up sign}':
            confirm = True
    finally:
        if delete_after:
            await message.delete()

        return confirm


async def add_reactions(message: discord.Message, reactions: Iterable):
    async def react():
        for reaction in reactions:
            await message.add_reaction(reaction)

    ensure_future(react())


def setup(bot):
    bot.add_cog(ConnectFour(bot))
