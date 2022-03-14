import discord
from discord.ext import commands
from ..utils.api.tmdb import TMDBClient

class TMDBBaseCog(commands.Cog, name="Search"):
    """Shows information from TMDB about a TV show or film."""
    def __init__(self, bot):
        self.bot = bot
        self.client = TMDBClient()
        self.emotes = {
                "director": "<:director:768770081927856149>",
                "film_reel": "<:film_reel:768770081546436620>",
                "two_hearts": "<:two_hearts:768770081886437376>",
                "hero": "<:hero:768774437163106314>",
                "draw": "<:draw:768774137325813762>",
                "documentary": "<:file:788005034867818526>",
                "cash": "<:cash:788005035006099486>"
            }

    @staticmethod
    def localise_number(number):
        import locale
        locale.setlocale(locale.LC_ALL, 'en_GB.UTF-8')
        return locale.format_string('%d', number, grouping=True)

    def _get_embed(self, instance, icon):
        icon = discord.File(f"assets/Emojis/{icon}.png", filename="icon.png")
        footer_icon = discord.File("assets/Emojis/tmdb.png", filename="tmdb.png")
        embed = discord.Embed(colour=discord.Colour.blurple())
        embed.set_image(url=instance.poster or discord.Embed.Empty)
        embed.description = instance.overview
        embed.set_author(name=instance.title, url=instance.homepage or discord.Embed.Empty, icon_url=f"attachment://icon.png")
        if instance.credits.director:
            embed.add_field(name=f"{self.emotes['director']}    Director", value=instance.credits.director.name)
        if instance.credits.writer:
            embed.add_field(name=f"{self.emotes['draw']}    Writer", value=instance.credits.writer.name)
        if instance.credits.screenplay:
            embed.add_field(name=f"{self.emotes['film_reel']}    Screenplay", value=instance.credits.screenplay.name)
        if instance.genres:
            embed.add_field(name=f"{self.emotes['two_hearts']}    Genres", value=", ".join(instance.genres))
        if instance.revenue:
            embed.add_field(
                name=f'{self.emotes["cash"]}    Total Revenue',
                value=f'${self.localise_number(instance.revenue)}'
            )
        if hasattr(instance, "ratings") and instance.ratings.runtime:
            # TODO Add this attribute to instance directly
            embed.add_field(name=f"{self.emotes['film_reel']}    Runtime", value=instance.ratings.runtime)
        if instance.release_date:
            embed.timestamp = instance.release_date
        if instance.productions:
            embed.add_field(
                name=f'{self.emotes["film_reel"]}    Productions',
                value=' • '.join(instance.productions),
                inline=False
            )
        if instance.credits.cast:
            embed.add_field(
                name=f"{self.emotes['hero']}    Top Billed Cast", inline=False,    # len(embed.fields) % 2 == 0,
                value=", ".join(c.name for c in instance.credits.cast[:7])
            )
        if hasattr(instance, 'ratings'):
            if instance.ratings.imdb:
                embed.add_field(name="IMDb rating", value=(f"{instance.ratings.imdb} ({instance.ratings.imdb_votes} votes)" if instance.ratings.imdb_votes else instance.ratings.imdb), inline=True)
            if instance.ratings.rtomatoes:
                embed.add_field(name="Rotten Tomatoes", value=instance.ratings.rtomatoes, inline=True)
            if instance.ratings.metascore:
                embed.add_field(name="Metascore (Metacritic)", value=instance.ratings.metascore, inline=True)

        embed.set_footer(
            text=f"{instance.votes} Votes | {instance.status}",
            icon_url="attachment://tmdb.png"
        )
        return (embed, [icon, footer_icon])
    async def cog_unload(self):
        self.client.http.session.close()

    @commands.group(name='film', aliases=['films', 'movie', 'movies'], invoke_without_command=True)
    async def movie(self, ctx, *, name):
        """Displays the details of the first movie found in search results."""
        movie = await self.client.fetch_movie_from_search(query=name)
        if not movie:
            return await ctx.send(embed=discord.Embed(description=f"❌    No movies found matching with specified name.", colour=discord.Colour.red()), delete_after=15.0)
        embed, files = self._get_embed(movie, icon="movie")
        await ctx.channel.send(embed=embed, files=files)

    @commands.group(name="show", aliases=["shows", "tvshow", "tvshows"], invoke_without_command=True)
    async def tvshow(self, ctx, *, name):
        """Displays the details of the first TV Show found in the search results."""
        tvshow = await self.client.fetch_tvshow_from_search(query=name)
        if not tvshow:
            return await ctx.send(embed=discord.Embed(description=f"❌    No TV Show found matching with specified name.", colour=discord.Colour.red()), delete_after=15.0)
        embed, files = self._get_embed(tvshow, icon="tvshow")
        embed.set_footer(
            text=f"{embed.footer.text} | Last Air", icon_url=embed.footer.icon_url
        )
        embed.timestamp = tvshow.last_air_date
        if tvshow.creators and (tvshow.creators[0] != getattr(tvshow.credits.writer, "name", None)):
            embed.insert_field_at(0, name=f"{self.emotes['director']}    Creators", value=", ".join(tvshow.creators))
        if tvshow.next_episode:
            embed.insert_field_at(
                2, name=f"{self.emotes['film_reel']}    Upcoming Episode", value=tvshow.next_episode.name
            )
        else:
            if tvshow.last_episode:
                embed.insert_field_at(
                    2, name=f"{self.emotes['film_reel']}    Last Episode", value=tvshow.last_episode.name
                )
        embed.description = f"**{tvshow.seasons_count} Seasons | {tvshow.episodes_count} Episodes**\n\n" + embed.description

        await ctx.channel.send(embed=embed, files=files)

async def setup(bot):
    await bot.add_cog(TMDBBaseCog(bot))
