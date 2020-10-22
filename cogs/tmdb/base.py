import discord
from discord.ext import commands
from ..utils.api.tmdb import TMDBClient

class TMDBBaseCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_embed(self, instance, icon):
        icon = discord.File(f"assets/{icon}.png", filename="icon.png")
        footer_icon = discord.File("assets/tmdb.png", filename="tmdb.png")
        embed = discord.Embed(colour=discord.Colour.blurple())
        embed.set_thumbnail(url=instance.poster or discord.Embed.Empty)
        embed.description = instance.overview
        embed.set_author(name=instance.title, url=instance.homepage or discord.Embed.Empty, icon_url=f"attachment://icon.png")
        if instance.credits.director:
            embed.add_field(name="Director", value=instance.credits.director.name)
        if instance.credits.writer:
            embed.add_field(name=f"Writer", value=instance.credits.writer.name)
        if instance.credits.screenplay:
            embed.add_field(name=f"Screenplay", value=instance.credits.screenplay.name)
        if instance.genres:
            embed.add_field(name=f"Genres", value=", ".join(instance.genres))
        if instance.release_date:
            embed.timestamp = instance.release_date
        if instance.credits.cast:
            embed.add_field(
                name=f"Top Billed Cast", inline=False,    # len(embed.fields) % 2 == 0,
                value=", ".join(c.name for c in instance.credits.cast[:7])
            )
        embed.set_footer(
            text=f"{instance.votes} Votes | {instance.status}",
            icon_url="attachment://tmdb.png"
        )
        return (embed, [icon, footer_icon])

    @commands.group(name='movie', aliases=['movies'], invoke_without_command=True)
    async def movie(self, ctx, *, name):
        """Displays the details of the first movie found in search results."""
        movie = await TMDBClient.fetch_movie_from_search(query=name)
        if not movie:
            return await ctx.send(embed=discord.Embed(description=f"❌    No movies found matching with specified name.", colour=discord.Colour.red()), delete_after=15.0)
        embed, files = self._get_embed(movie, icon="movie")
        await ctx.channel.send(embed=embed, files=files)

    @commands.group(name="show", aliases=["shows", "tvshow", "tvshows"], invoke_without_command=True)
    async def tvshow(self, ctx, *, name):
        """Displays the details of the first TV Show found in the search results."""
        tvshow = await TMDBClient.fetch_tvshow_from_search(query=name)
        if not tvshow:
            return await ctx.send(embed=discord.Embed(description=f"❌    No TV Show found matching with specified name.", colour=discord.Colour.red()), delete_after=15.0)
        embed, files = self._get_embed(tvshow, icon="tvshow")
        embed.set_footer(
            text=f"{embed.footer.text} | Last Air", icon_url=embed.footer.icon_url
        )
        embed.timestamp = tvshow.last_air_date
        if tvshow.creators and (tvshow.creators[0] != getattr(tvshow.credits.writer, "name", None)):
            embed.insert_field_at(0, name=f"{self.emotes.director}    Creators", value=", ".join(tvshow.creators))
        if tvshow.next_episode:
            embed.insert_field_at(
                2, name=f"{self.emotes.film_reel}    Upcoming Episode", value=tvshow.next_episode.name
            )
        else:
            if tvshow.last_episode:
                embed.insert_field_at(
                    2, name=f"{self.emotes.film_reel}    Last Episode", value=tvshow.last_episode.name
                )
        # embed.description = f"{tvshow.seasons_count} Seasons | {tvshow.episodes_count} Episodes\n" + embed.description

        await ctx.channel.send(embed=embed, files=files)