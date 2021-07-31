from __future__ import annotations

import asyncio
import random
from collections.abc import Iterator
from functools import cache, cached_property, partial
from typing import Any, Literal, Optional, TypeVar, Union, overload, TYPE_CHECKING

import discord
from discord.ext import commands, menus
from discord.utils import MISSING

from .utils import db
from .utils.paginator import RoboPages, SimplePageSource

if TYPE_CHECKING:
    from bot import RoboVJ
    from .utils.context import Context

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

MIN_DEPTH = 3
MAX_DEPTH = 5

BACKGROUND = '\N{BLACK CIRCLE FOR RECORD}\N{VARIATION SELECTOR-16}'
DISCS = ('\N{LARGE RED CIRCLE}', '\N{LARGE YELLOW CIRCLE}')

K = 32  # Ranking K-factor

B = TypeVar('B', bound='Board')

BoardState = list[list[Optional[bool]]]


class Games(db.Table):
    game_id = db.PrimaryKeyColumn()
    players = db.Column(db.Array(db.Integer(big=True)))
    winner = db.Column(db.Integer(small=True))
    finished = db.Column(db.Boolean)


class Ranking(db.Table):
    user_id = db.Column(db.Integer(big=True), primary_key=True)
    ranking = db.Column(db.Integer, default=1000)
    games = db.Column(db.Integer, default=0)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)


class Board:
    def __init__(self, state: BoardState, current_player: bool = MISSING, last_move: Optional[tuple[int, int]] = None):
        self.state = state
        if current_player is MISSING:
            self.current_player = random.choice((True, False))
        else:
            self.current_player = current_player
        self.last_move = last_move
        self.winner: Optional[bool] = MISSING

    @property
    def legal_moves(self) -> Iterator[int]:
        for c in range(COLUMNS):
            for r in range(ROWS):
                if self.state[r][c] is None:
                    yield c
                    break

    @cached_property
    def hash(self) -> int:
        return hash((self.state, self.__class__.__name__))

    def move(self, col: int, cls: type[B] = MISSING, *, flipped: bool = False) -> B:
        if col not in self.legal_moves:
            raise ValueError('Illegal move')

        new_state = [[self.state[r][c] for c in range(COLUMNS)] for r in range(ROWS)]

        iterator = range(ROWS)
        if not flipped:
            iterator = reversed(iterator)

        for row in iterator:
            if self.state[row][col] is None:
                new_state[row][col] = self.current_player
                break

        if cls is MISSING:
            cls = self.__class__  # type: ignore

        return cls(new_state, not self.current_player, (row, col))  # type: ignore

    @cache
    def in_a_row(self, n: int, position: tuple[int, int]) -> bool:

        r, c = position
        token = self.state[r][c]

        counts = [0 for _ in range(4)]  # 4 directions

        for o in range(-(n - 1), n):

            # horizontal
            if 0 <= c + o < COLUMNS:
                if self.state[r][c + o] == token:
                    counts[0] += 1
                else:
                    counts[0] = 0

            # vertical
            if 0 <= r + o < ROWS:
                if self.state[r + o][c] == token:
                    counts[1] += 1
                else:
                    counts[1] = 0

                # asc diag
                if 0 <= c + o < COLUMNS:
                    if self.state[r + o][c + o] == token:
                        counts[2] += 1
                    else:
                        counts[2] = 0

                # desc diag
                if 0 <= c - o < COLUMNS:
                    if self.state[r + o][c - o] == token:
                        counts[3] += 1
                    else:
                        counts[3] = 0
            if any(c >= n for c in counts):
                return True

        return False

    @cached_property
    def over(self) -> bool:

        counts = [0, 0]

        for c in range(COLUMNS):
            for r in range(ROWS):
                token = self.state[r][c]
                if token is None:
                    continue

                if self.in_a_row(4, (r, c)):
                    counts[token] += 1

        # Handle weird case where multiple wins occur
        if sum(counts):
            if counts[0] > counts[1]:
                self.winner = False
            elif counts[0] < counts[1]:
                self.winner = True
            else:
                self.winner = None

            return True

        # Check if board is empty
        for _ in self.legal_moves:
            break
        else:
            self.winner = None
            return True

        return False

    @classmethod
    def new_game(cls: type[B]) -> B:
        state: BoardState = [[None for _ in range(COLUMNS)] for _ in range(ROWS)]
        return cls(state, False)


class Flip(Board):
    def __init__(self, *args: Any, flipped: bool = False, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.flipped = flipped

    def flip(self) -> Board:

        state: BoardState = [[None for _ in range(COLUMNS)] for _ in range(ROWS)]

        for c in range(COLUMNS):
            o = 0
            if not self.flipped:
                for o in range(ROWS):
                    if self.state[o][c] is not None:
                        break

                for r in range(ROWS - o):
                    state[r][c] = self.state[r + o][c]

            else:
                for o in range(ROWS):
                    if self.state[ROWS - 1 - o][c] is not None:
                        break

                for r in range(ROWS - o):
                    state[r + o][c] = self.state[r][c]

        return Flip(state, self.current_player, flipped=not self.flipped)

    def move(self, column: int, *, cls=MISSING) -> Board:
        board = super().move(column, cls=cls, flipped=self.flipped)

        if board.over:
            return board

        if self.flipped:
            board.flipped = True

        if self.current_player:
            board = board.flip()

        return board  # type: ignore


class AI:
    def __init__(self, player: bool) -> None:
        self.player = player

    def move(self, game: Board) -> Board:
        column = random.choice(tuple(game.legal_moves))
        return game.move(column)


class NegamaxAI(AI):
    def __init__(self, player: bool, depth: int = MAX_DEPTH):
        self.max_depth = depth
        super().__init__(player)

    def heuristic(self, game: Board, sign: int) -> float:
        if sign == -1:
            player = not self.player
        else:
            player = self.player

        if game.over:
            if game.winner is None:
                return 0
            if game.winner == player:
                return 1_000_000
            return -1_000_000

        return random.randint(-10, 10)

        score = 0
        return score
        for r in range(ROWS):
            for c in range(COLUMNS):
                token = game.state[r][c]
                if token != None:
                    if game.in_a_row(3, (r, c)):
                        if token == self.player:
                            score += 2.5
                        else:
                            score -= 2.5
        return score / depth

    @overload
    def negamax(self, game: Board, depth: Literal[0] = ...,
                alpha: float = ..., beta: float = ..., sign: int = ...) -> int:
        ...

    @overload
    def negamax(self, game: Board, depth: int = ..., alpha: float = ..., beta: float = ..., sign: int = ...) -> float:
        ...

    def negamax(self, game: Board, depth: int = 0,
                alpha: float = float('-inf'), beta: float = float('inf'), sign: int = 1) -> Union[float, int]:
        if depth == self.max_depth or game.over:
            return sign * self.heuristic(game, sign)

        move = MISSING

        score = float('-inf')
        for c in game.legal_moves:
            move_score = -self.negamax(game.move(c), depth + 1, -beta, -alpha, -sign)

            if move_score > score:
                score = move_score
                move = c

            alpha = max(alpha, score)
            if alpha >= beta:
                break

        if depth == 0:
            return move
        else:
            return score

    def move(self, game: B) -> B:
        return game.move(self.negamax(game))


class Game(menus.Menu):
    async def start(self, ctx, opponent, *, channel=None, wait=False, ranked: bool = True, cls: type[Board] = Board):
        self.players = (ctx.author, opponent)
        self.ranked = ranked

        if self.ranked:
            for player in self.players:
                await ctx.db.execute('INSERT INTO ranking (user_id) VALUES ($1) ON CONFLICT DO NOTHING;', player.id)

        self.board = cls.new_game()

        if self.players[self.board.current_player].bot:
            await self._ai_turn()

        # Setup bottons
        for emoji in REGIONAL_INDICATOR_EMOJI:
            self.add_button(menus.Button(emoji, self.place))

        await super().start(ctx, channel=channel, wait=wait)

    async def send_initial_message(self, ctx, channel):
        return await channel.send(
            f'{self.players[self.board.current_player].mention}\'s ({DISCS[self.board.current_player]}) turn!',
            embed=self.state,
        )

    def reaction_check(self, payload):
        if payload.message_id != self.message.id:
            return False

        if payload.user_id == self.bot.user.id:
            return False

        if payload.user_id != self.players[self.board.current_player].id:
            return False

        return payload.emoji in self.buttons

    @property
    def state(self):
        state = ''
        for r in range(ROWS):
            emoji = []
            for c in range(COLUMNS):
                token = self.board.state[r][c]
                if token is None:
                    emoji.append(BACKGROUND)
                else:
                    emoji.append(DISCS[token])

            state += '\n' + ' '.join(emoji)

        state += '\n ' + ' '.join(REGIONAL_INDICATOR_EMOJI)

        return discord.Embed(description=state)

    async def _ai_turn(self):
        delta = MAX_DEPTH - MIN_DEPTH
        depth = self.players[self.board.current_player].id % delta + MAX_DEPTH + 1
        ai = NegamaxAI(self.board.current_player, depth)
        move_call = partial(ai.move, self.board)
        self.board = await self.bot.loop.run_in_executor(None, move_call)

    async def _next_turn(self):
        if self.board.over:
            return await self._end_game()

        await self.message.edit(
            content=f'{self.players[self.board.current_player].mention}\'s ({DISCS[self.board.current_player]}) turn!',
            embed=self.state,
        )

        # if AI auto play turn
        if self.players[self.board.current_player].bot:
            await self._ai_turn()
            await self._next_turn()

    async def _end_game(self, resignation: int = None):
        winner: Optional[int]

        if resignation is not None:
            winner = int(not resignation)
            content = f'Game cancelled by {self.players[resignation].mention} ({DISCS[resignation]})!'
        elif self.board.winner is not None:
            winner = int(self.board.winner)
            content = f'{self.players[self.board.winner].mention} ({DISCS[self.board.winner]}) Wins!'
        else:
            winner = None
            content = 'Draw!'

        await self.message.edit(content=f'Game over! {content}', embed=self.state)
        self.stop()

        if not self.ranked:
            return

        # Calculate new ELO
        query = '\'-- noinspection SqlResolveForFile @ table/"ranking"\n\nINSERT INTO games (players, winner, finished) VALUES ($1, $2, $3);\''
        await self.ctx.db.execute(query, [p.id for p in self.players], winner, resignation is None)
        query = 'SELECT * FROM ranking WHERE user_id = $1;'
        record_1 = await self.ctx.db.fetchrow(query, self.players[0].id)
        record_2 = await self.ctx.db.fetchrow(query, self.players[1].id)

        R1 = 10 ** (record_1['ranking'] / 400)
        R2 = 10 ** (record_2['ranking'] / 400)

        E1 = R1 / (R1 + R2)
        E2 = R2 / (R1 + R2)

        S1 = (winner == 0) if winner is not None else 0.5
        S2 = (winner == 1) if winner is not None else 0.5

        r1 = record_1['ranking'] + K * (S1 - E1)
        r2 = record_2['ranking'] + K * (S2 - E2)

        query = 'UPDATE ranking SET ranking = $2, games = $3, wins = $4, losses = $5 WHERE user_id = $1;'
        await self.ctx.db.execute(query, self.players[0].id, round(r1), record_1['games'] + 1,
                                  record_1['wins'] + (winner == 0), record_1['losses'] + (winner == 1))
        await self.ctx.db.execute(query, self.players[1].id, round(r1), record_2['games'] + 1,
                                  record_2['wins'] + (winner == 1), record_2['losses'] + (winner == 0))

    async def place(self, payload):
        column = REGIONAL_INDICATOR_EMOJI.index(str(payload.emoji))
        if column not in self.board.legal_moves:
            return ...

        self.board = self.board.move(column)
        await self._next_turn()

    @menus.button('\N{BLACK SQUARE FOR STOP}\ufe0f', position=menus.Last(0))
    async def cancel(self, payload):
        await self._end_game(resignation=self.board.current_player)


class ConnectFour(commands.Cog):
    def __init__(self, bot: RoboVJ):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)

    async def _get_opponent(self, ctx: Context) -> Optional[discord.Member]:
        message = await ctx.send(
            embed=discord.Embed(description=f'{ctx.author.mention} wants to play Connect Four.').set_footer(
                text='react with \N{WHITE HEAVY CHECK MARK} to accept the challenge.'
            )
        )
        await message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

        def check(reaction, user):
            if reaction.emoji != '\N{WHITE HEAVY CHECK MARK}':
                return False
            if user.bot:
                return False
            if user == ctx.author:
                return False
            if reaction.message != message:
                return False
            return True

        try:
            _, opponent = await self.bot.wait_for('reaction_add', check=check, timeout=60.0)
            return opponent
        except asyncio.TimeoutError:
            pass
        finally:
            await message.delete()
        return None

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    # @commands.max_concurrency(1, per=commands.BucketType.channel)
    async def c4(self, ctx: Context, *, opponent: Optional[discord.Member] = None):
        """Start a Connect Four game!

        `opponent`: Another member of the server to play against. If not set, an open challenge is started.
        """
        if opponent is None:
            opponent = await self._get_opponent(ctx)
        else:
            if opponent == ctx.author:
                raise commands.BadArgument('You cannot play against yourself.')

            if not await ctx.prompt(
                f'{opponent.mention}, {ctx.author.mention} has challenged you to Connect 4!',
                author_id=opponent.id
            ):
                opponent = None

        # If challenge timed out, or rejected
        if opponent is None:
            raise commands.BadArgument('Challenge cancelled.')

        await Game().start(ctx, opponent, wait=True, ranked=not opponent.bot)

    @c4.command(invoke_without_command=True, name='flip', aliases=['antigravity'])
    @commands.guild_only()
    # @commands.max_concurrency(1, per=commands.BucketType.channel)
    async def c4_flip(self, ctx: Context, *, opponent: Optional[discord.Member] = None):
        """ """
        if opponent is None:
            opponent = await self._get_opponent(ctx)
        else:
            if opponent == ctx.author:
                raise commands.BadArgument('You cannot play against yourself.')

            if not await ctx.prompt(
                    f'{opponent.mention}, {ctx.author.mention} has challenged you to Connect 4!',
                    author_id=opponent.id
            ):
                opponent = None

        # If challenge timed out, or rejected
        if opponent is None:
            raise commands.BadArgument('Challenge cancelled.')

        await Game().start(ctx, opponent, wait=True, ranked=False, cls=Flip)

    @c4.command(name='ranking', aliases=['elo', 'leaderboard', 'rankings'])
    async def c4_ranking(self, ctx: Context, *, player: Optional[discord.Member] = None):
        """Get a player's ranking."""
        if player is not None:
            record = await ctx.db.fetchrow('SELECT * FROM ranking WHERE user_id = $1;', player.id)
            if not record:
                raise commands.BadArgument(f'{player} does not have a ranking.')

            user_id, ranking, games, wins, losses = record

            embed = discord.Embed(title=f'{player}\'s ranking:').add_field(name='Ranking', value=ranking) \
                .add_field(name='Games Played', value=f'**{games}**') \
                .add_field(name='Wins', value=f'**{wins}** ({wins / games:.0%})') \
                .add_field(name='Losses', value=f'**{losses}** ({losses / games:.0%})')

            return await ctx.send(embed=embed)
        records = await ctx.db.fetch('SELECT * FROM ranking ORDER BY ranking DESC ;')
        pages = RoboPages(source=RankingSource(self.bot, records))
        await pages.start(ctx)


class RankingSource(SimplePageSource):
    def __init__(self, bot: RoboVJ, entries, *, per_page=12):
        super().__init__(entries, per_page=per_page)
        self.bot = bot

    async def format_page(self, menu, entries):
        embed = discord.Embed(title='Connect 4 rankings:', colour=discord.Colour.og_blurple())
        for entry in entries:
            if entry['games'] == 0:
                continue
            user = self.bot.get_user(entry['user_id']) or 'Unknown User'
            embed.add_field(
                name=f'{user} | {entry["ranking"]}',
                value=f'Games: **{entry["games"]}** | Wins: **{entry["wins"]}** | Losses: **{entry["losses"]}**'
            )
        if not embed.fields:
            embed.description = 'No records found...'
        return embed


def setup(bot: RoboVJ):
    bot.add_cog(ConnectFour(bot))
