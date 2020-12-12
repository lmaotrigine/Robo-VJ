import discord
from discord.ext import commands, menus

import datetime
import html
import math
import re
import textwrap

import dateutil.parser
import inflect
import more_itertools
import tabulate

from .utils.paginator import SimplePages


class Finance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.inflect_engine = inflect.engine()

    @commands.group(description='Powered by [CoinDesk](https://www.coindesk.com/price/)', invoke_without_command=True)
    async def bitcoin(self, ctx, currency: str = ''):
        """
        Bitcoin Price Index (BPI)
        To specify a currency, enter the three-character currency code (e.g. USD, GBP, EUR)
        """
        if currency:
            url = f'https://api.coindesk.com/v1/bpi/currentprice/{currency}'
            async with self.bot.session.get(url) as resp:
                if resp.status == 404:
                    error = await resp.text()
                    return await ctx.reply(f':no_entry: Error: {error}')
                data = await resp.json(content_type='application/javascript')
            currency_data = data['bpi'][currency.upper()]
            title = currency_data['description']
            description = f'{currency_data["code"]} {currency_data["rate"]}\n'
            fields = ()
        else:
            url = 'https://api.coindesk.com/v1/bpi/currentprice.json'
            async with self.bot.session.get(url) as resp:
                data = await resp.json(content_type='application/javascript')
            title = data['chartName']
            description = ''
            fields = []
            for currency in data['bpi'].values():
                field_value = f'{currency["code"]} {html.unescape(currency["symbol"])}{currency["rate"]}'
                fields.append((currency['description'], field_value))
        description += 'Powered by [CoinDesk](https://www.coindesk.com/price/)'
        footer_text = data['disclaimer'].rstrip('.') + '. Updated'
        timestamp = dateutil.parser.parse(data['time']['updated'])
        embed = discord.Embed(title=title, description=description, timestamp=timestamp)
        for field in fields:
            embed.add_field(name=field[0], value=field[1])
        embed.set_footer(text=footer_text)
        await ctx.reply(embed=embed)

    @bitcoin.command(name='currencies')
    async def bitcoin_currencies(self, ctx):
        """Supported currencies for BPI conversion."""
        async with self.bot.session.get("https://api.coindesk.com/v1/bpi/supported-currencies.json") as resp:
            data = await resp.json(content_type='text/html')
        desc1 = ', '.join('{0[currency]} ({0[country]})'.format(c) for c in data[:int(len(data) / 2)])
        desc2 = ', '.join('{0[currency]} ({0[country]})'.format(c) for c in data[int(len(data) / 2):])
        pages = SimplePages([desc1, desc2], per_page=1)
        try:
            await pages.start(ctx)
        except menus.MenuError as e:
            await ctx.send(e)

    @bitcoin.command(name='historical', aliases=['history', 'past', 'previous', 'day', 'date'])
    async def bitcoin_historical(self, ctx, date: str = "", currency: str = ''):
        """
        Historical BPI
        Date must be in YYYY-MM-DD format (default is yesterday)
        To specify a currency, enter the three-character currency code
        (e.g. USD, GBP, EUR) (Default is USD)
        """
        # TODO: Date converter: Current converter can't handle past dates
        if date:
            params = {'start': date, 'end': date}
            if currency:
                params['currency'] = currency
        else:
            params = {'for': 'yesterday'}
        url = 'https://api.coindesk.com/v1/bpi/historical/close.json'
        async with self.bot.session.get(url, params=params) as resp:
            if resp.status == 404:
                error = await resp.text()
                await ctx.reply(f':no_entry: Error: {error}')
                return
            data = await resp.json(content_type='application/javascript')
        if date:
            description = str(data.get('bpi', {}).get(date, 'N/A'))
        else:
            description = str(list(data['bpi'].values())[0])
        description += '\nPowered By [CoinDesk](https://www.coindesk.com/price/)'
        footer_text = data['disclaimer'] + ' Updated'
        timestamp = dateutil.parser.parse(data['time']['updated'])
        embed = discord.Embed(description=description, timestamp=timestamp).set_footer(text=footer_text)
        await ctx.reply(embed=embed)

    @commands.group(name='exchange', aliases=['rates'], invoke_without_command=True)
    async def currency(self, ctx, against: str = '', request: str = ''):
        """
        Current foreign exchange rates
        Hourly updates
        Exchange rate ata delivered is midpoint data
        Midpoint rates are determined by calculating the average
        median rate of Bid and Ask at a certain time
        [against]: currency to quote against (base) (default is EUR)
        [request]: currencies to request rate for (separated by commas with no spaces)
        To specify a currency, enter the three-character currency code (e.g. USD, GBP, EUR)

        The `currency` command works slightly differently. It uses only the European Central Bank as a source.
        Use that as a fallback in case Fixer rate-limits me.
        """
        # TODO: Acknowledge Fixer
        await self.process_currency(ctx, against, request)

    @currency.command(name='historical', aliases=['history', 'past', 'previous', 'day', 'date'])
    async def currency_historical(self, ctx, date: str, against: str = '', request: str = ''):
        """
        Historical foreign exchange rates
        End Of Day historical exchange rates, which become available at 00:05 am GMT
        for the previous day and are time stamped at one second before midnight
        Date must be in YYYY-MM-DD format
        [against]: currency to quote against (base) (default is EUR)
        [request]: currencies to request rate for (separated by commas with no spaces)
        To specify a currency, enter the three-character currency code (e.g. USD, GBP, EUR)
        """
        # TODO: Date converter
        await self.process_currency(ctx, against, request, date)

    @currency.command(name='symbols', aliases=['acronyms', 'abbreviations'])
    async def currency_symbols(self, ctx):
        """Currency symbols."""
        url = 'http://data.fixer.io/api/symbols'
        params = {'access_key': self.bot.config.fixer_api_key}
        async with self.bot.session.get(url, params=params) as resp:
            # TODO: Handle errors
            data = await resp.json()
        if not data.get('success'):
            return await ctx.reply(':no_entry: Error: API response was unsuccessful.')
        symbols = list(data['symbols'].items())
        tabulated_symbols = tabulate.tabulate(symbols, tablefmt='plain').split('\n')
        fields = []
        while tabulated_symbols:
            formatted_symbols = ''
            if not len(fields) % 3:
                inline_field_count = min(math.ceil((len('\n'.join(tabulated_symbols)) + 8) / 1024), 3)
                # 8 = len('```\n' + '\n```') for code block
                # 1024 = Character limit for embed field value
                # TODO: Handle possibility of textwrap indents increasing inline field count by 1 when < 3?
            while tabulated_symbols and len(
                formatted_symbols + (
                    formatted_line := '\n'.join(textwrap.wrap(tabulated_symbols[0],
                                                              56 // inline_field_count,
                                                              subsequent_indent=' ' * 5))
                )
            ) < 1024 - 8:
                # 56 = Embed description code block row character limit
                # 5 = len(symbol + '  '), e.g. 'USD  '
                formatted_symbols += '\n' + formatted_line
                tabulated_symbols.pop(0)
            if fields:
                fields.append(('\u200b', f'```\n{formatted_symbols}\n```'))
                # Zero-width space for empty field title.
            else:
                fields.append(('Currency Symbols', f'```\n{formatted_symbols}\n```'))
        # TODO: Paginate
        embed = discord.Embed()
        for field in fields:
            embed.add_field(name=field[0], value=field[1])
        await ctx.reply(embed=embed)

    async def process_currency(self, ctx, against, request, date=''):
        params = {'access_key': self.bot.config.fixer_api_key}
        if against:
            params['base'] = against
        if request:
            params['symbols'] = request.upper()
        url = 'http://data.fixer.io/api/'
        url += str(date) if date else 'latest'
        async with self.bot.session.get(url, params=params) as resp:
            # TODO: Use Etags
            if resp.status in (404, 422):
                # TODO: Handle other errors
                data = await resp.json(content_type='text/html')
                return await ctx.reply(f':no_entry: Error: {data["error"]}')
            data = await resp.json()
        if not data.get('success'):
            # TODO: Include error message
            return await ctx.reply(':no_entry: Error: API response was unsuccessful.')
        rates = list(data['rates'].items())
        parts = len(tabulate.tabulate(rates, tablefmt='plain', floatfmt='f')) // 1024 + 1
        # 1024 = Embed field value character limit
        if len(rates) >= 3:
            parts = max(parts, 3)
        rates_parts = more_itertools.divide(parts, rates)
        tabulated_rates = tabulate.tabulate(rates_parts[0], tablefmt='plain', floatfmt='f')
        field_title = f'Currency {self.inflect_engine.plural("Rate", len(rates))} Against {data["base"]}'
        fields = [(field_title, f'```\n{tabulated_rates}\n```')]
        for rates_part in rates_parts[1:]:
            tabulated_rates = tabulate.tabulate(rates_part, tablefmt='plain', floatfmt='f')
            fields.append(('\u200b', f'```\n{tabulated_rates}\n```'))
        # TODO: Paginate
        footer_text = self.inflect_engine.plural('Rate', len(rates)) + ' from'
        timestamp = datetime.datetime.utcfromtimestamp(data['timestamp'])
        embed = discord.Embed(timestamp=timestamp)
        embed.set_footer(text=footer_text)
        for field in fields:
            embed.add_field(name=field[0], value=field[1])
        await ctx.reply(embed=embed)

    # TODO: Handle ServerDisconnectedError?
    @commands.group(aliases=['stocks'],
                    description='Data provided for free by [IEX](https://iextrading.com/developer).',
                    invoke_without_command=True)
    async def stock(self, ctx, symbol: str):
        """
        WIP
        https://iextrading.com/api-exhibit-a
        """
        url = f'https://api.iextrading.com/1.0/stock/{symbol}/price'
        async with self.bot.session.get(url) as resp:
            data = await resp.text()
        attribution = '\nData provided for free by [IEX](https://iextrading.com/developer).'
        await ctx.reply(data + attribution)

    @stock.command(name='company')
    async def stock_company(self, ctx, symbol: str):
        """Company information."""
        url = f'https://api.iextrading.com/1.0/stock/{symbol}/company'
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
        url = f'https://api.iextrading.com/1.0/stock/{symbol}/logo'
        async with self.bot.session.get(url) as resp:
            logo_data = await resp.json()
        description = f'{data["description"]}\nWebsite: {data["website"]}'
        attribution = '\nData provided for free by [IEX](https://iextrading.com/developer).'
        title = f'{data["companyName"]} ({data["symbol"]})'
        fields = (('Exchange', data['exchange']), ('Industry', data['industry']), ('CEO', data['CEO']))
        thumbnail_url = logo_data.get('url', discord.Embed.Empty)
        embed = discord.Embed(description=description + attribution, title=title)
        embed.set_thumbnail(url=thumbnail_url)
        for field in fields:
            embed.add_field(name=field[0], value=field[1])
        await ctx.reply(embed=embed)

    @stock.command(name='earnings')
    async def stock_earnings(self, ctx, symbol: str):
        """Earnings data from the most recent reported quarter."""
        url = f'https://api.iextrading.com/1.0/stock/{symbol}/earnings'
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
        report = data['earnings'][0]
        # TODO: Paginate other reports
        fields = []
        for key, value in report.items():
            if key != 'EPSReportDate':
                # Add spaces: l( )U and U( )Ul [l = lowercase, U = uppercase]
                field_title = re.sub(r'([a-z](?=[A-Z])|[A-Z](?=[A-Z][a-z]))', r'\1 ', key)
                # Capitalise first letter
                field_title = field_title[0].upper() + field_title[1:]
                fields.append((field_title, value))
        footer_text = f'EPS Report Date: {report["EPSReportDate"]}'
        embed = discord.Embed(title=data['symbol'])
        embed.set_footer(text=footer_text)
        for field in fields:
            embed.add_field(name=field[0], value=field[1])
        await ctx.reply(embed=embed)

    @stock.command(name='financials')
    async def stock_financials(self, ctx, symbol: str):
        """Income statement, balance sheet, and cash flow data from the most recent reported quarter."""
        url = f'https://api.iextrading.com/1.0/stock/{symbol}/financials'
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
        report = data['financials'][0]
        # TODO: Paginate other reports
        fields = []
        for key, value in report.items():
            if key != 'reportDate':
                # Add spaces: l( )U and U( )Ul [l = lowercase, U = uppercase]
                field_title = re.sub(r'([a-z](?=[A-Z])|[A-Z](?=[A-Z][a-z]))', r'\1 ', key)
                # Capitalise first letter
                field_title = field_title[0].upper() + field_title[1:]
                # Replace And with & to fit Research And Development into field title nicely
                field_title = field_title.replace('And', '&')
                if isinstance(value, int):
                    value = f'{value:,}'
                fields.append((field_title, value))
        footer_text = f'Report Date: {report["reportDate"]}'
        embed = discord.Embed(title=data['symbol'])
        embed.set_footer(text=footer_text)
        for field in fields:
            embed.add_field(name=field[0], value=field[1])
        await ctx.reply(embed=embed)

    @stock.command(name='quote')
    async def stock_quote(self, ctx, symbol: str):
        """WIP"""
        url = f'https://api.iextrading.com/1.0/stock/{symbol}/quote'
        async with self.bot.session.get(url) as resp:
            data = await resp.json()
        description = f'{data["companyName"]}\nData provided for free by [IEX](https://iextrading.com/developer).'
        fields = []
        if 'iexRealtimePrice' in data:
            fields.append(('IEX Real-Time Price', data['iexRealtimePrice']))
        timestamp = discord.Embed.Empty
        iex_last_updated = data.get('iexLastUpdated')
        if iex_last_updated and iex_last_updated != -1:
            timestamp = datetime.datetime.utcfromtimestamp(iex_last_updated / 1000)
        embed = discord.Embed(title=data['symbol'], description=description, timestamp=timestamp)
        embed.set_footer(text=data['primaryExchange'])
        for field in fields:
            embed.add_field(name=field[0], value=field[1])
        await ctx.reply(embed=embed)


def setup(bot):
    bot.add_cog(Finance(bot))
