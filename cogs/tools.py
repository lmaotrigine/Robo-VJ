import discord
from discord.ext import commands

import io
import re

import matplotlib
import matplotlib.figure
import numexpr
import numpy
import seaborn
import math
import multiprocessing
import concurrent.futures
import asyncio
import sympy


class Paginator(commands.Paginator):

    def __init__(self, separator='\n', prefix='```', suffix='```', max_size=2000):
        super().__init__(prefix, suffix, max_size)
        self.separator = separator
        self._current_page = []

    def add_section(self, section='', *, empty=False):
        if len(section) > self.max_size - len(self.prefix) - 2:
            raise RuntimeError('Section exceeds maximum page size %s' % (self.max_size - len(self.prefix) - 2))

        if self._count + len(section) + len(self.separator) > self.max_size:
            self.close_page()

        self._count += len(section) + len(self.separator)
        self._current_page.append(section)

        if empty:
            self._current_page.append('')
            self._count += len(self.separator)

    def close_page(self):
        self._pages.append(self.prefix + '\n' + self.separator.join(self._current_page) + '\n' + self.suffix)
        self._current_page = []
        self._count = len(self.prefix) + len(self.separator)
        
    @property
    def pages(self):
        if len(self._current_page) > 0:
            self.close_page()
        return self._pages


class Tools(commands.Cog):
    """Random stuff. WIP."""
    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=['plot'], invoke_without_command=True)
    async def graph(self, ctx, lower_limit: int, upper_limit: int, *, equation: str):
        """WIP"""
        try:
            equation = self.string_to_equation(equation)
        except SyntaxError as e:
            return await ctx.reply(f':no_entry: Error: {e}')
        x = numpy.linspace(lower_limit, upper_limit, 250)
        try:
            y = numexpr.evaluate(equation)
        except Exception as e:
            return await ctx.reply(f'```py\n{e.__class__.__name__}: {e}\n```')
        figure = matplotlib.figure.Figure()
        axes = figure.add_subplot()
        try:
            axes.plot(x, y)
        except ValueError as e:
            return await ctx.reply(f":no_entry: Error: {e}")
        buffer = io.BytesIO()
        figure.savefig(buffer, format="PNG")
        buffer.seek(0)
        await ctx.reply(file=discord.File(buffer, filename='graph.png'))

    def string_to_equation(self, string):
        replacements = {'^': "**"}
        allowed_words = (
        'x', "sin", "cos", "tan", "arcsin", "arccos", "arctan", "arctan2", "sinh", "cosh", "tanh", "arcsinh", "arccosh",
        "arctanh", "log", "log10", "log1p", "exp", "expm1", "sqrt", "abs", "conj", "complex")
        for word in re.findall("[a-zA-Z_]+", string):
            if word not in allowed_words:
                raise SyntaxError("`{}` is not supported".format(word))
        for old, new in replacements.items():
            string = string.replace(old, new)
        return string

    @graph.command(name="alternative", aliases=["alt", "complex"])
    @commands.is_owner()
    async def graph_alternative(self, ctx, *, data: str):
        """WIP"""
        buffer = io.BytesIO()
        seaborn.jointplot(**eval(data)).savefig(buffer, format='PNG')
        buffer.seek(0)
        await ctx.reply(file=discord.File(buffer, filename='graph.png'))

    @commands.command(require_var_positional=True)
    async def add(self, ctx, *numbers: float):
        """Add numbers together"""
        await ctx.reply(embed=discord.Embed(description=f"{' + '.join(f'{number:g}' for number in numbers)} = "
                                                        f"{sum(numbers):g}"))

    # TODO: Fix/Improve
    @commands.command(aliases=["calc", "calculator"])
    async def calculate(self, ctx, *, equation: str):
        """Calculator"""
        # _equation = re.sub("[^[0-9]+-/*^%\.]", "", equation).replace('^', "**") #words
        replacements = {"pi": "math.pi", 'e': "math.e", "sin": "math.sin",
                        "cos": "math.cos", "tan": "math.tan", '^': "**"}
        allowed = set("0123456789.+-*/^%()")
        for key, value in replacements.items():
            equation = equation.replace(key, value)
        # TODO: use filter
        equation = "".join(character for character in equation if character in allowed)
        print("Calculated " + equation)

        with multiprocessing.Pool(1) as pool:
            async_result = pool.apply_async(eval, (equation,))
            future = ctx.bot.loop.run_in_executor(None, async_result.get, 10.0)
            try:
                result = await asyncio.wait_for(future, 10.0)
                await ctx.reply(embed=discord.Embed(description=f"{equation} = {result}"))
            except discord.HTTPException:
                # TODO: use textwrap/paginate
                await ctx.reply(embed=discord.Embed(description=":no_entry: Output too long"))
            except SyntaxError:
                await ctx.reply(embed=discord.Embed(description=":no_entry: Syntax error"))
            except TypeError as e:
                await ctx.reply(embed=discord.Embed(description=f":no_entry: Error: {e}"))
            except ZeroDivisionError:
                await ctx.reply(embed=discord.Embed(description=":no_entry: Error: Division by zero"))
            except (concurrent.futures.TimeoutError, multiprocessing.context.TimeoutError):
                await ctx.ereply(embed=discord.Embed(description=":no_entry: Execution exceeded time limit"))

    @commands.command()
    async def exp(self, ctx, value: float):
        """
        Exponential function
        e ** value | e ^ value
        """
        try:
            await ctx.reply(embed=discord.Embed(description=str(math.exp(value))))
        except OverflowError as e:
            await ctx.reply(f":no_entry: Error: {e}")

    @commands.command()
    async def factorial(self, ctx, value: int):
        """Factorial"""
        try:
            await ctx.reply(embed=discord.Embed(description=str(math.factorial(value))))
        except OverflowError as e:
            await ctx.reply(f":no_entry: Error: {e}")

    @commands.command(aliases=["greatest_common_divisor"])
    async def gcd(self, ctx, value_a: int, value_b: int):
        """Greatest common divisor"""
        await ctx.reply(embed=discord.Embed(description=str(math.gcd(value_a, value_b))))

    @commands.command(aliases=['π'])
    async def pi(self, ctx, digits: int = 3, start: int = 1):
        """Digits of pi."""
        # Handle decimal point being considered a digit
        if start <= 1:
            start = 0
            # Don't exceed 1000 digit limit
            if 1 < digits < 1000:
                digits += 1
        url = 'https://api.pi.delivery/v1/pi'
        params = {'start': start, 'numberOfDigits': digits}
        async with self.bot.session.get(url, params=params) as resp:
            data = await resp.json()
        if 'content' in data:
            return await ctx.reply(embed=discord.Embed(description=data['content']))
        await ctx.reply(f':no_entry: Error: {data.get("Error", "N/A")}')

    @commands.command(aliases=["squareroot", "square_root"])
    async def sqrt(self, ctx, value: float):
        """Square root"""
        await ctx.reply(embed=discord.Embed(description=str(math.sqrt(value))))

    # Calculus

    @commands.command(aliases=["differ", "derivative", "differentiation"])
    async def differentiate(self, ctx, *, equation: str):
        """
        Differentiate an equation
        with respect to x (dx)
        """

        x = sympy.symbols('x')
        try:
            await ctx.reply(embed=discord.Embed(description=f'`{sympy.diff(equation.strip("`"), x)}`',
                                                title=f'Derivative of {equation}'))
        except Exception as e:
            await ctx.reply(embed=discord.Embed(description=f'```py\n{e.__class__.__name__}: {e}\n```',
                                                title='Error'))

    @commands.group(aliases=["integral", "integration"], invoke_without_command=True, case_insensitive=True)
    async def integrate(self, ctx, *, equation: str):
        """
        Integrate an equation
        with respect to x (dx)
        """
        x = sympy.symbols('x')
        try:
            await ctx.reply(embed=discord.Embed(description=f'`{sympy.integrate(equation.strip("`"), x)}`',
                                                title=f'Integral of {equation}'))
        except Exception as e:
            await ctx.reply(embed=discord.Embed(description=f'```py\n{e.__class__.__name__}: {e}\n```',
                                                title='Error'))

    @integrate.command(name="definite")
    async def integrate_definite(self, ctx, lower_limit: str, upper_limit: str, *, equation: str):
        """
        Definite integral of an equation
        with respect to x (dx)
        """
        x = sympy.symbols('x')
        try:
            await ctx.reply(embed=discord.Embed(
                description=f'`{sympy.integrate(equation.strip("`"), (x, lower_limit, upper_limit))}`',
                title=f'Definite integral of {equation} from {lower_limit} to {upper_limit}'))
        except Exception as e:
            await ctx.reply(embed=discord.Embed(description=f'```py\n{e.__class__.__name__}: {e}\n```',
                                                title='Error'))

    # Trigonometry
    # TODO: a(sin/cos/tan)h aliases

    @commands.command(alises=["acosine", "arccos", "arccosine", "a_cosine", "arc_cos", "arc_cosine"])
    async def acos(self, ctx, value: float):
        """Arc cosine function"""
        await ctx.reply(embed=discord.Embed(description=str(math.acos(value))))

    @commands.command(alises=["acosineh", "arccosh", "arccosineh", "a_cosineh", "arc_cosh", "arc_cosineh"])
    async def acosh(self, ctx, value: float):
        """Inverse hyperbolic cosine function"""
        await ctx.reply(embed=discord.Embed(description=str(math.acosh(value))))

    @commands.command(alises=["asine", "arcsin", "arcsine", "a_sine", "arc_sin", "arc_sine"])
    async def asin(self, ctx, value: float):
        """Arc sine function"""
        await ctx.reply(embed=discord.Embed(description=str(math.asin(value))))

    @commands.command(alises=["asineh", "arcsinh", "arcsineh", "a_sineh", "arc_sinh", "arc_sineh"])
    async def asinh(self, ctx, value: float):
        """Inverse hyperbolic sine function"""
        await ctx.reply(embed=discord.Embed(description=str(math.asinh(value))))

    # TODO: atan2
    @commands.command(alises=["atangent", "arctan", "arctangent", "a_tangent", "arc_tan", "arc_tangent"])
    async def atan(self, ctx, value: float):
        """Arc tangent function"""
        await ctx.reply(embed=discord.Embed(description=str(math.atan(value))))

    @commands.command(alises=["atangenth", "arctanh", "arctangenth", "a_tangenth", "arc_tanh", "arc_tangenth"])
    async def atanh(self, ctx, value: float):
        """Inverse hyperbolic tangent function"""
        await ctx.reply(embed=discord.Embed(description=str(math.atanh(value))))

    @commands.command(alises=["cosine"])
    async def cos(self, ctx, value: float):
        """Cosine function"""
        await ctx.reply(embed=discord.Embed(description=str(math.cos(value))))

    @commands.command(alises=["cosineh"])
    async def cosh(self, ctx, value: float):
        """Hyperbolic cosine function"""
        await ctx.reply(embed=discord.Embed(description=str(math.cosh(value))))

    @commands.command(alises=["sine"])
    async def sin(self, ctx, value: float):
        """Sine function"""
        await ctx.reply(embed=discord.Embed(description=str(math.sin(value))))

    @commands.command(alises=["sineh"])
    async def sinh(self, ctx, value: float):
        """Hyperbolic sine function"""
        await ctx.reply(embed=discord.Embed(description=str(math.sinh(value))))

    @commands.command(alises=["tangent"])
    async def tan(self, ctx, value: float):
        """Tangent function"""
        await ctx.reply(embed=discord.Embed(description=str(math.tan(value))))

    @commands.command(alises=["tangenth"])
    async def tanh(self, ctx, value: float):
        """Hyperbolic tangent function"""
        await ctx.reply(embed=discord.Embed(description=str(math.tanh(value))))


def setup(bot):
    bot.add_cog(Tools(bot))
