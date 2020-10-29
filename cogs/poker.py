from discord.ext import commands
import asyncio
import discord
import pydealer
import treys
from .utils import checks

class Poker(commands.Cog):
    """Poker implementation (WIP)"""
    def __init__(self, bot):
        self.bot = bot
        self.status = None
        self.players = []
        self.deck = None
        self.hands = {}
        self.turn = None
        self.bets = {}
        self.current_bet = None
        self.pot = None
        self.community_cards = None
        self.folded = []
        # check default values

    @commands.group(invoke_without_command=True)
    async def poker(self, ctx):
        """Work in progress."""
        await ctx.send_help(ctx.command)

    @poker.command()
    async def start(self, ctx):
        # TODO: Handle folds
        if self.status not in (None, 'started'):
            await ctx.send("There is already a round of poker in progress.")
        elif self.status is None:
            self.status = 'started'
            self.players = []
            self.hands = {}
            # reset other
            self.deck = pydealer.Deck()
            self.deck.shuffle()
            self.pot = 0
            await ctx.send(embed=discord.Embed(description=f"has started a round of poker\n`{ctx.prefix}poker join` to join\n`{ctx.prefix}poker start` again to start.").set_author(name=f"{ctx.author}", icon_url=ctx.author.avatar_url))
        elif self.players:
            self.status = 'pre-flop'
            await ctx.send(embed=discord.Embed(description=f"The poker round has started\nPlayers: {', '.join(player.mention for player in self.players)}"))
            for player in self.players:
                cards_string = self.cards_to_string(self.hands[player.id].cards)
                await player.send(embed=discord.Embed(title="Your poker hand", description={cards_string}, colour=discord.Colour.blurple()))
            await self.betting(ctx)
            while self.status:
                await asyncio.sleep(1)
            await ctx.send(embed=discord.Embed(title="The pot", description=f"{self.pot}"))
            self.community_cards = self.deck.deal(3)
            await ctx.send(embed=discord.Embed(title="The flop", description=self.cards_to_string(self.community_cards)))
            await self.betting(ctx)
            while self.status:
                await asyncio.sleep(1)
            await ctx.send(embed=discord.Embed(title='The pot', description=f"{self.pot}"))
            self.community_cards.add(self.deck.deal(1))
            await ctx.send(embed=discord.Embed(title="The turn", description=self.cards_to_string(self.community_cards)))
            await self.betting(ctx)
            while self.status:
                await asyncio.sleep(1)
            await ctx.send(embed=discord.Embed(title="The pot", description=f"{self.pot}"))
            self.community_cards.add(self.deck.deal(1))
            await ctx.send(embed=discord.Embed(title="The river", description=self.cards_to_string(self.community_cards)))
            await self.betting(ctx)
            while self.status:
                await asyncio.sleep(1)
            await ctx.send(embed=discord.Embed(title="The pot", description=f"{self.pot}"))

            evaluator = treys.Evaluator()
            board = []
            for card in self.community_cards.cards:
                abbreviation = pydealer.card.card_abbrev(card.value[0] if card.value != '10' else 'T', card.suit[0].lower())
                board.append(treys.Card.new(abbreviation))
            best_hand_value = 7462
            best_player = None
            for player, hand in self.hands.items():
                hand_stack = []
                for card in hand:
                    abbreviation = pydealer.card.card_abbrev(card.value[0] if card.value != '10' else 'T', card.suit[0].lower())
                    hand_stack.append(treys.Card.new(abbreviation))
                value = evaluator.evaluate(board, hand_stack)
                if value < best_hand_value:
                    best_hand_value = value
                    best_player = player
            player = await self.bot.fetch_user(player)
            kind = evaluator.class_to_string(evaluator.get_rank_class(best_hand_value))
            await ctx.send(embed=discord.Embed(description=f"{player.mention} is the winner with a {kind}"))

    @poker.command()
    async def join(self, ctx):
        if self.status == "started":
            self.players.append(ctx.author)
            self.hands[ctx.author.id] = self.deck.deal(2)
            await ctx.send(embed=discord.Embed(description='has joined the poker game').set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url))
        elif self.status is None:
            await ctx.send(embed=discord.Embed(description=f"There's not currently a round of poker going on\nUse `{ctx.prefix}poker start` to start one"))
        else:
            await ctx.send(embed=discord.Embed(description="\N{NO ENTRY} The current round of poker has already started."))

    @poker.command(name='raise')
    async def poker_raise(self, ctx, points: int):
        if self.turn and self.turn.id == ctx.author.id:
            if points > self.current_bet:
                self.bets[self.turn.id] = points
                self.current_bet = points
                await ctx.send(embed=discord.Embed(description=f"has raised to {points}").set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url))
                self.turn = None
            elif points == self.current_bet:
                self.bets[self.turn.id] = points
                await ctx.send(embed=discord.Embed(description='has called').set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url))
                self.turn = None
            else:
                await ctx.send(embed=discord.Embed(description=f"{ctx.author.mention}, the current bet is more than that."))
        else:
            await ctx.send(embed=discord.Embed(description=f"\N{NO ENTRY} {ctx.author.mention} you can't do that right now."))

    @poker.command()
    async def check(self, ctx):
        if self.turn and self.turn.id == ctx.author.id:
            if self.current_bet != 0 and (self.turn.id not in self.bets or self.bets[self.turn.id] < self.current_bet):
                await ctx.send(embed=discord.Embed(description=f"\N{NO ENTRY} {ctx.author.mention} you can't check."))
            else:
                self.bets[self.turn.id] = self.current_bet
                await ctx.send(embed=discord.Embed(description='has checked').set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url))
                self.turn = None
        else:
            await ctx.send(embed=discord.Embed(description=f"\N{NO ENTRY} {ctx.author.mention} you can't do that right now."))

    @poker.command()
    async def call(self, ctx):
        if self.turn and self.turn.id == ctx.author.id:
            if self.current_bet == 0 or (self.turn.id in self.bets and self.bets[self.turn.id] == self.current_bet):
                await ctx.send(embed=discord.Embed(description=f"{ctx.author.mention} you can't call. You have checked instead."))
                await ctx.send(embed=discord.Embed(description='has checked').set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url))
            else:
                self.bets[self.turn.id] = self.current_bet
                await ctx.send(embed=discord.Embed(description='has called').set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url))
            self.turn = None
        else:
            await ctx.send(embed=discord.Embed(description=f"\N{NO ENTRY} {ctx.author.mention} you can't do that right now."))

    @poker.command()
    async def fold(self, ctx):
        if self.turn and self.turn.id == ctx.author.id:
            self.bets[self.turn.id] = -1
            self.folded.append(self.turn)
            await ctx.send(embed=discord.Embed(description='has folded').set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url))
            self.turn = None
        else:
            await ctx.send(embed=discord.Embed(description=f"\N{NO ENTRY} {ctx.author.mention} you can't do that right now."))

    async def betting(self, ctx):
        self.status = 'betting'
        self.current_bet = 0
        while True:
            for player in self.players:
                self.turn = player
                if player in self.folded:
                    continue
                await ctx.send(embed=discord.Embed(description=f"{player.mention}'s turn"))
                while self.turn:
                    await asyncio.sleep(1)
            if all([bet == -1 or bet == self.current_bet for bet in self.bets.values()]):
                break
        for bet in self.bets.values():
            if bet != -1:
                self.pot += bet
        self.status = None

    # Utility functions
    def cards_to_string(self, cards):
        return " ".join(f":{card.suit.lower()}: {card.value}" for card in cards)

def setup(bot):
    bot.add_cog(Poker(bot))