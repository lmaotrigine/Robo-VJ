import discord
from discord.ext import commands

import asyncio
import copy
import pydealer
import pydealer.tools


class Games(commands.Cog):

    """Only Blackjack for now. More on the way."""

    def __init__(self, bot):
        self.bot = bot
        self.blackjack_ranks = copy.deepcopy(pydealer.const.DEFAULT_RANKS)
        self.blackjack_ranks['values'].update({'Ace': 0, 'King': 9, 'Queen': 9, 'Jack': 9})
        for value in self.blackjack_ranks['values']:
            self.blackjack_ranks['values'][value] += 1
        # check default values

    @staticmethod
    def cards_to_string(cards):
        return ''.join(f':{card.suit.lower()}: {card.value} ' for card in cards)

    @commands.command()
    async def blackjack(self, ctx):
        """
        Play a game of Blackjack.
        Manage Messages permissions required for message cleanup.
        """
        if ctx.prefix.lower() in ('hit', 'stay'):
            return await ctx.reply('This is a stupid prefix that you can\'t use to play this game.'
                                   'Use another prefix or mention me and call this command again.')
        # TODO: S17
        deck = pydealer.Deck()
        deck.shuffle()
        dealer = deck.deal(2)
        player = deck.deal(2)
        dealer_string = f':grey_question: :{dealer.cards[1].suit.lower()}: {dealer.cards[1].value}'
        player_string = self.cards_to_string(player.cards)
        dealer_total = self.blackjack_total(dealer.cards)
        player_total = self.blackjack_total(player.cards)
        embed = discord.Embed(description=f'Dealer: {dealer_string} (?)\n{ctx.author.display_name}: {player_string} '
                                          f'({player_total})\n',
                              title='Blackjack')
        embed.set_footer(text='Hit or Stay?')
        response = await ctx.reply(embed=embed)
        while True:
            action = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author and
                                             m.content.lower().strip(ctx.prefix) in ('hit', 'stay'))
            try:
                await action.delete()
            except discord.HTTPException:
                pass
            if action.content.lower().strip(ctx.prefix) == 'hit':
                player.add(deck.deal())
                player_string = self.cards_to_string(player.cards)
                player_total = self.blackjack_total(player.cards)
                embed.description = f'Dealer: {dealer_string} (?)\n{ctx.author.display_name}: {player_string} ' \
                                    f'({player_total})\n'
                await response.edit(embed=embed)
                if player_total > 21:
                    embed.description += ':boom: You have busted.'
                    embed.set_footer(text='You lost :(')
                    break
            else:
                dealer_string = self.cards_to_string(dealer.cards)
                embed.description = f'Dealer: {dealer_string} ({dealer_total})\n{ctx.author.display_name}: ' \
                                    f'{player_string} ({player_total})\n'
                if dealer_total > 21:
                    embed.description += ':boom: The dealer busted.'
                    embed.set_footer(text='You win!')
                    break
                elif dealer_total > player_total:
                    embed.description += 'The dealer beat you.'
                    embed.set_footer(text='You lost :(')
                    break
                embed.set_footer(text='Dealer\'s turn...')
                await response.edit(embed=embed)
                while True:
                    await asyncio.sleep(5)
                    dealer.add(deck.deal())
                    dealer_string = self.cards_to_string(dealer.cards)
                    dealer_total = self.blackjack_total(dealer.cards)
                    embed.description = f'Dealer: {dealer_string} ({dealer_total})\n{ctx.author.display_name}: ' \
                                        f'{player_string} ({player_total})\n'
                    await response.edit(embed=embed)
                    if dealer_total > 21:
                        embed.description += ':boom: The dealer busted.'
                        embed.set_footer(text='You win!')
                        break
                    elif dealer_total > player_total:
                        embed.description += 'The dealer beat you.'
                        embed.set_footer(text='You lost :(')
                        break
                    elif dealer_total == player_total == 21:
                        embed.set_footer(text='It\'s a push (tie)')
                        break
                break
        await response.edit(embed=embed)

    def blackjack_total(self, cards):
        total = sum(self.blackjack_ranks['values'][card.value] for card in cards)
        if pydealer.tools.find_card(cards, term='Ace', limit=1) and total <= 11:
            total += 10
        return total


async def setup(bot):
    await bot.add_cog(Games(bot))
