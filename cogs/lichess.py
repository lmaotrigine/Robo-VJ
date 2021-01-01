import discord
from discord.ext import commands

import datetime

import emoji
import pycountry
import inflect

from .utils import time


def duration_to_string(duration: datetime.timedelta, weeks: bool = True,
                       milliseconds: bool = False, microseconds: bool = False,
                       abbreviate: bool = False, separator: str = ' ') -> str:
    # TODO: Support colon format
    # TODO: Default output for duration of 0?
    if not isinstance(duration, datetime.timedelta):
        raise RuntimeError("duration must be datetime.timedelta")
    negative = False
    if duration.total_seconds() < 0:
        duration = abs(duration)
        negative = True
    units = {"year": duration.days // 365}
    if weeks:
        units["week"] = duration.days % 365 // 7
        units["day"] = duration.days % 365 % 7
    else:
        units["day"] = duration.days % 365
    units["hour"] = duration.seconds // 3600
    units["minute"] = duration.seconds // 60 % 60
    units["second"] = duration.seconds % 60
    if milliseconds:
        units["millisecond"] = duration.microseconds // 1000
        if microseconds:
            units["microsecond"] = duration.microseconds % 1000
    elif microseconds:
        units["microsecond"] = duration.microseconds
    outputs = []
    for name, value in units.items():
        if not value:
            continue
        if negative:
            value = -value
        if abbreviate:
            if name == "millisecond":
                output = f"{value}ms"
            elif name == "microsecond":
                output = f"{value}μs"
            else:
                output = f"{value}{name[0]}"
        else:
            output = f"{value} {name}"
            if abs(value) > 1:
                output += 's'
        outputs.append(output)
    return separator.join(outputs)


class LichessUser(commands.Converter):
    async def convert(self, ctx, argument):
        url = f'https://en.lichess.org/api/user/{argument}'
        async with ctx.bot.session.get(url) as resp:
            if resp.status == 404:
                raise commands.BadArgument('User not found.')
            data = await resp.json()
        if not data:
            raise commands.BadArgument('User not found.')
        if data.get('closed'):
            raise commands.BadArgument('This account is closed.')
        return data


class Lichess(commands.Cog):
    """https://en.lichess.org/"""
    def __init__(self, bot):
        self.bot = bot
        self.modes = ('ultraBullet', 'bullet', 'blitz', 'rapid', 'classical', 'correspondence',
                      'crazyhouse', 'chess960', 'kingOfTheHill', 'threeCheck', 'antichess',
                      'atomic', 'horde', 'racingKings', 'puzzle')
        self.mode_names = ('Ultrabullet', 'Bullet', 'Blitz', 'Rapid', 'Classical', 'Correspondence',
                           'Crazyhouse', 'Chess960', 'King of the Hill', 'Three-Check', 'Antichess',
                           'Atomic', 'Horde', 'Racing Kings', 'Training')
        self.inflect_engine = inflect.engine()

        # TODO: Use unicode code points
        self.ultrabullet_emoji = '<:lichess_ultrabullet:794156128971653142>'
        self.bullet_emoji = '<:lichess_bullet:794156128757743626>'
        self.blitz_emoji = '<:lichess_blitz:794156128741228544>'
        self.rapid_emoji = '<:lichess_rapid:794156128942030849>'
        self.classical_emoji = '<:lichess_classical:794156128325730355>'
        self.correspondence_emoji = '<:lichess_correspondence:794156128790511646>'
        self.crazyhouse_emoji = '<:lichess_crazyhouse:794156128761282610>'
        self.chess960_emoji = '<:lichess_chess960:794156128782254120>'
        self.kingofthehill_emoji = '<:lichess_king_of_the_hill:794156128807419934>'
        self.threecheck_emoji = '<:lichess_three_check:794156128639385641>'
        self.antichess_emoji = '<:lichess_antichess:794156128485376062>'
        self.atomic_emoji = '<:lichess_atomic:794156128811352084>'
        self.horde_emoji = '<:lichess_horde:794156128866795520>'
        self.racingkings_emoji = '<:lichess_racing_kings:794156128811745370>'
        self.training_emoji = '<:lichess_training:794156128664944641>'
        self.uprightarrow_emoji = '<:lichess_up_right_arrow:794156128824197132>'
        self.downrightarrow_emoji = '<:lichess_down_right_arrow:794156128757874698>'
        self.forum_emoji = '<:lichess_forum:794156128602161173>'
        self.practice_emoji = '<:lichess_practice:794156128426524703>'
        self.stream_emoji = '<:lichess_stream:794156128882917396>'
        self.team_emoji = '<:lichess_team:794156129277313064>'
        self.thumbsup_emoji = '<:lichess_thumbsup:794156128744374363>'
        self.trophy_emoji = '<:lichess_trophy:794156128605831179>'
        self.mode_emojis = (self.ultrabullet_emoji, self.bullet_emoji, self.blitz_emoji,
                            self.rapid_emoji, self.classical_emoji, self.correspondence_emoji,
                            self.crazyhouse_emoji, self.chess960_emoji, self.kingofthehill_emoji,
                            self.threecheck_emoji, self.antichess_emoji, self.atomic_emoji,
                            self.horde_emoji, self.racingkings_emoji, self.training_emoji)
        self.generate_user_mode_commands()

    @commands.Cog.listener()
    async def on_ready(self):
        self.generate_user_mode_commands()

    def generate_user_mode_commands(self):
        # Creates user subcommand for a mode
        def user_mode_wrapper(mode, name, emoji):
            async def user_mode_command(ctx, username: LichessUser):
                mode_data = username['perfs'][mode]
                prov = ''
                if mode_data.get('prov'):
                    prov = '?'
                if mode_data['prog'] >= 0:
                    arrow = self.uprightarrow_emoji
                else:
                    arrow = self.downrightarrow_emoji
                embed = discord.Embed(title=username['username'])
                embed.description = f'{emoji} {name} | **Games**: {mode_data["games"]}, ' \
                                    f'**Rating**: {mode_data["rating"]}{prov}±{mode_data["rd"]} ' \
                                    f'{arrow} {mode_data["prog"]}'
                await ctx.send(embed=embed)
            return user_mode_command
        # Generate user subcommand for each mode
        for mode, name, emoji in zip(self.modes, self.mode_names, self.mode_emojis):
            internal_name = name.lower().replace(' ', '').replace('-', '')
            # Remove existing command in cases where already generated
            # Such as on_ready after cog instantiated.
            self.user.remove_command(internal_name)
            command = commands.Command(user_mode_wrapper(mode, name, emoji),
                                       name=name.lower().replace(' ', '').replace('-', ''),
                                       help=f'User {name} stats')
            setattr(self, 'user_' + internal_name, command)
            self.user.add_command(command)

    @commands.group(invoke_without_command=True)
    async def lichess(self, ctx):
        """Lichess"""
        await ctx.send_help(ctx.command)

    @lichess.group(aliases=['tournaments'], invoke_without_command=True)
    async def tournament(self, ctx):
        """Tournaments"""
        await ctx.send_help(ctx.command)

    @tournament.command(name='current', aliases=['started'])
    async def tournament_current(self, ctx):
        """Current tournaments."""
        url = 'https://en.lichess.com/api/tournament'
        async with ctx.session.get(url) as resp:
            data = await resp.json()
        data = data['started']
        fields = []
        for tournament in data:
            finishes_at = datetime.datetime.utcfromtimestamp(tournament['finishesAt'] / 1000.0)
            value = f'{tournament["clock"]["limit"] / 60:g}+{tournament["clock"]["increment"]} ' \
                    f'{tournament["perf"]["name"]} {"Rated" if tournament["rated"] else "Casual"}\n' \
                    f'Ends in: {time.human_timedelta(finishes_at, source=datetime.datetime.utcnow(), brief=True)}\n' \
                    f'[Link](https://en.lichess.org/tournament/{tournament["id"]})'
            fields.append((tournament['fullName'], value))
        embed = discord.Embed(title='Current Lichess Tournaments')
        for name, value in fields:
            embed.add_field(name=name, value=value)
        await ctx.send(embed=embed)

    @lichess.group(aliases=['stats', 'statistics', 'stat', 'statistic'], invoke_without_command=True)
    async def user(self, ctx, username: LichessUser):
        """User stats."""
        # TODO: Separate stats subcommand?
        embed = discord.Embed(title=username.get('title', '') + ' ' + username['username'], url=username['url'])
        for mode, name, emoji in zip(self.modes, self.mode_names, self.mode_emojis):
            if not username['perfs'].get(mode, {}).get('games', 0):
                continue
            mode_data = username['perfs'][mode]
            prov = ''
            if mode_data.get('prov'):
                    prov = '?'
            if mode_data['prog'] >= 0:
                arrow = self.uprightarrow_emoji
            else:
                arrow = self.downrightarrow_emoji
            value = f'Games: {mode_data["games"]}\nRating:\n' \
                    f'{mode_data["rating"]}{prov} ± {mode_data["rd"]} {arrow} {mode_data["prog"]}'
            embed.add_field(name=str(emoji) + ' ' + name, value=value)
        if 'seenAt' in username:
            embed.set_footer(text='Last seen')
            embed.timestamp = datetime.datetime.utcfromtimestamp(username['seenAt'] / 1000.0)
        await ctx.send(embed=embed)

    @user.command(name='activity')
    async def user_activity(self, ctx, username: str):
        """User activity"""
        # TODO: Use converter?
        url = f'https://lichess.org/api/user/{username}/activity'
        async with ctx.session.get(url) as resp:
            data = await resp.json()
            if resp.status == 429 and 'error' in data:
                await ctx.reply(f':no_entry: Error: {data["error"]}')
                return
        if not data:
            await ctx.reply(f':no_entry: User activity not found.')
            return
        embed = discord.Embed(title=f'{username}\'s Activity')
        total_length = 0
        for day in data:
            activity = ''
            if 'practice' in day:
                for practice in day['practice']:
                    activity += f'{self.practice_emoji} Practiced {practice["nbPositions"]} positions on ' \
                                f'[{practice["name"]}](https://lichess.org{practice["url"]})\n'
            if 'puzzles' in day:
                puzzle_wins = day['puzzles']['score']['win']
                puzzle_losses = day['puzzles']['score']['loss']
                puzzle_draws = day['puzzles']['score']['draw']
                rating_before = day['puzzles']['score']['rp']['before']
                rating_after = day['puzzles']['score']['rp']['after']
                total_puzzles = puzzle_wins + puzzle_losses + puzzle_draws
                rating_change = rating_after - rating_before
                activity += f'{self.training_emoji} Solved {total_puzzles} tactical ' \
                            f'{self.inflect_engine.plural("puzzle", total_puzzles)}\t'
                if rating_change != 0:
                    activity += str(rating_after)
                    if rating_change > 0:
                        activity += self.uprightarrow_emoji
                    elif rating_change < 0:
                        activity += self.downrightarrow_emoji
                    activity += f'{abs(rating_change)}\t'
                if puzzle_wins:
                    activity += f'{puzzle_wins} {self.inflect_engine.plural("win", puzzle_wins)} '
                if puzzle_draws:
                    activity += f'{puzzle_draws} {self.inflect_engine.plural("draw", puzzle_draws)} '
                if puzzle_losses:
                    activity += f'{puzzle_losses} {self.inflect_engine.plural("loss", puzzle_losses)}'
                activity += '\n'
            if 'games' in day:
                for mode, mode_data in day['games'].items():
                    mode_wins = mode_data['win']
                    mode_losses = mode_data['loss']
                    mode_draws = mode_data['draw']
                    rating_before = mode_data['rp']['before']
                    rating_after = mode_data['rp']['after']
                    mode_index = self.modes.index(mode)
                    total_matches = mode_wins + mode_losses + mode_draws
                    rating_change = rating_after - rating_before
                    activity += f'{self.mode_emojis[mode_index]} Played {total_matches} ' \
                                f'{self.mode_names[mode_index]} ' \
                                f'{self.inflect_engine.plural("game", total_matches)}\t'
                    if rating_change != 0:
                        activity += str(rating_after)
                        if rating_change > 0:
                            activity += self.uprightarrow_emoji
                        elif rating_change < 0:
                            activity += self.downrightarrow_emoji
                        activity += f'{abs(rating_change)}\t'
                    if mode_wins:
                        activity += f'{mode_wins} {self.inflect_engine.plural("win", mode_wins)} '
                    if mode_draws:
                        activity += f'{mode_draws} {self.inflect_engine.plural("draw", mode_draws)} '
                    if mode_losses:
                        activity += f'{mode_losses} {self.inflect_engine.plural("loss", mode_losses)}'
                    activity += '\n'
            if 'posts' in day:
                for post in day['posts']:
                    activity += f'{self.forum_emoji} Posted {len(post["posts"])} ' \
                                f'{self.inflect_engine.plural("message", len(post["posts"]))} ' \
                                f'in [{post["topicName"]}](https://lichess.org{post["topicUrl"]})\n'
            if 'correspondenceMoves' in day:
                activity += f'{self.correspondence_emoji} Played {day["correspondenceMoves"]["nb"]} ' \
                            f'{self.inflect_engine.plural("move", day["correspondenceMoves"]["nb"])}'
                game_count = len(day['correspondenceMoves']['games'])
                activity += f' in {game_count}'
                if game_count == 15:
                    activity += '+'
                activity += f' correspondence {self.inflect_engine.plural("game", game_count)}\n'
                # TODO: Include game details?
            if 'correspondenceEnds' in day:
                correspondence_wins = day['correspondenceEnds']['score']['win']
                correspondence_losses = day['correspondenceEnds']['score']['loss']
                correspondence_draws = day['correspondenceEnds']['score']['draw']
                rating_before = day['correspondenceEnds']['score']['rp']['before']
                rating_after = day['correspondenceEnds']['score']['rp']['after']
                total_matches = correspondence_wins + correspondence_losses + correspondence_draws
                rating_change = rating_after - rating_before
                activity += f'{self.correspondence_emoji} Completed {total_matches} correspondence ' \
                            f'{self.inflect_engine.plural("game", total_matches)}\t'
                if rating_change != 0:
                    activity += str(rating_after)
                    if rating_change > 0:
                        activity += self.uprightarrow_emoji
                    elif rating_change < 0:
                        activity += self.downrightarrow_emoji
                    activity += f'{abs(rating_change)}\t'
                if correspondence_wins:
                    activity += f'{correspondence_wins} {self.inflect_engine.plural("win", correspondence_wins)} '
                if correspondence_draws:
                    activity += f'{correspondence_draws} {self.inflect_engine.plural("draw", correspondence_draws)} '
                if correspondence_losses:
                    activity += f'{correspondence_losses} {self.inflect_engine.plural("loss", correspondence_losses)}'
                activity += '\n'
                # TODO: Include game details?
            if 'follows' in day:
                if 'in' in day['follows']:
                    follows_in = day['follows']['in']['ids']
                    activity += f'{self.thumbsup_emoji} Gained ' \
                                f'{day["follows"]["in"].get("nb", len(follows_in))} new ' \
                                f'{self.inflect_engine.plural("follower", len(follows_in))}\n\t' \
                                f'{", ".join(follows_in)}\n'
                if 'out' in day['follows']:
                    follows_out = day['follows']['out']['ids']
                    activity += f'{self.thumbsup_emoji} Started following ' \
                                f'{day["follows"]["out"].get("nb", len(follows_out))} ' \
                                f'{self.inflect_engine.plural("player", len(follows_out))}\n\t' \
                                f'{", ".join(follows_out)}\n'
            if 'tournaments' in day:
                activity += f'{self.trophy_emoji} Competed in {day["tournaments"]["nb"]} ' \
                            f'{self.inflect_engine.plural("tournament", day["tournaments"]["nb"])}\n'
                for tournament in day['tournaments']['best']:
                    activity += f'\tRanked #{tournament["rank"]} (top {tournament["rankPercent"]}%) ' \
                                f'with {tournament["nbGames"]} ' \
                                f'{self.inflect_engine.plural("game", tournament["nbGames"])} ' \
                                f'in [{tournament["tournament"]["name"]}]' \
                                f'(https://lichess.org/tournament/{tournament["tournament"]["id"]})\n'
            if 'teams' in day:
                activity += f'{self.team_emoji} Joined {len(day["teams"])} ' \
                            f'{self.inflect_engine.plural("team", len(day["teams"]))}\n\t'
                teams = [f'[{team["name"]}](https://lichess.org{team["url"]})' for team in day['teams']]
                activity += f'{", ".join(teams)}\n'
            if day.get('stream'):
                activity += f'{self.stream_emoji} Hosted a live stream\n'
                # TODO: Add link
            # TODO: Use embed limit variables
            # TODO: Better method of checking total embed size
            date = datetime.datetime.utcfromtimestamp(day['interval']['start'] / 1000)
            date = date.strftime('%#d %b %Y')
            # %#d for removal of leading zero on Windows with native Python executable (for testing)
            total_length += len(date) + len(activity)
            if total_length > 6000:
                break
            if 0 < len(activity) <= 1024:  # > 0 check necessary?
                embed.add_field(name=date, value=activity, inline=False)
            elif len(activity) > 1024:
                split_index = activity.rfind('\n', 0, 1024)
                # TODO: Better method of finding split index, new line could be in the middle of a section
                embed.add_field(name=date, value=activity[:split_index], inline=False)
                embed.add_field(name=f'{date} (continued)', value=activity[split_index:], inline=False)
                # TODO: Dynamically handle splits
                # TODO: Use zws?
        await ctx.send(embed=embed)

    @user.command(name='games')
    async def user_games(self, ctx, username: LichessUser):
        """User games"""
        embed = discord.Embed(title=username.get('title', '') + ' ' + username['username'], url=username['url'])
        embed.add_field(name='Games', value=username['count']['all'])
        embed.add_field(name='Rated', value=username['count']['rated'])
        embed.add_field(name='Wins', value=username['count']['win'])
        embed.add_field(name='Losses', value=username['count']['loss'])
        embed.add_field(name='Draws', value=username['count']['draw'])
        embed.add_field(name='Playing', value=username['count']['playing'])
        embed.add_field(name='Bookmarks', value=username['count']['bookmark'])
        embed.add_field(name='Imported', value=username['count']['import'])
        embed.add_field(name='AI', value=username['count']['ai'])
        if 'seenAt' in username:
            embed.set_footer(text='Last seen')
            embed.timestamp = datetime.datetime.utcfromtimestamp(username['seenAt'] / 1000.0)
        await ctx.send(embed=embed)

    @user.command(name='profile', aliases=['bio'])
    async def user_profile(self, ctx, username: LichessUser):
        """User profile"""
        embed = discord.Embed(title=username.get('title', '') + ' ' + username['username'], url=username['url'])
        profile = username.get('profile', {})
        if 'firstName' in profile or 'lastName' in profile:
            embed.add_field(name=f'{profile.get("firstName", "")} {profile.get("lastName", "")}',
                            value=profile.get('bio', '\u200b'), inline=False)
        else:
            embed.description = profile.get('bio')
        embed.add_field(name='Online', value='Yes' if username['online'] else 'No')
        embed.add_field(name='Patron', value='Yes' if username.get('patron') else 'No')
        if 'fideRating' in profile:
            embed.add_field(name='FIDE Rating', value=profile['fideRating'])
        if 'uscfRating' in profile:
            embed.add_field(name='USCF Rating', value=profile['uscfRating'])
        if 'ecfRating' in profile:
            embed.add_field(name='ECF Rating', value=profile['ecfRating'])
        if 'country' in profile:
            country = profile['country']
            country_name = pycountry.countries.get(alpha_2=country[:2]).name
            country_flag = emoji.emojize(f':{country_name.replace(" ", "_")}:')
            if len(country) > 2:  # Subdivision
                country_name = pycountry.subdivisions.get(code=country).name
            # Wait for subdivision flag emoji support from Discord
            # From Unicode 10.0/Emoji 5.0/Twemoji 2.3
            # For England, Scotland and Wales
            embed.add_field(name='Location', value=f'{profile.get("location", "")}\n{country_flag} {country_name}')
        elif 'location' in profile:
            embed.add_field(name='Location', value=profile['location'])
        created_at = datetime.datetime.utcfromtimestamp(username['createdAt'] / 1000.0)
        embed.add_field(name='Member Since', value=created_at.strftime('%#d %b %Y'))
        if 'completionRate' in username:
            embed.add_field(name='Game Completion Rate', value=f'{username["completionRate"]}%')
        embed.add_field(name='Followers', value=username['nbFollowers'])
        embed.add_field(name='Following', value=username['nbFollowing'])
        playtime = username.get('playTime', {})
        if 'total' in playtime:
            embed.add_field(name='Time Spent Playing',
                            value=duration_to_string(datetime.timedelta(seconds=playtime['total']), abbreviate=True))

        if 'tv' in playtime:
            embed.add_field(name='Time on TV',
                            value=duration_to_string(datetime.timedelta(seconds=playtime['tv']), abbreviate=True))

        if 'links' in profile:
            embed.add_field(name='Links', value=profile['links'], inline=False)

        if 'seenAt' in username:
            embed.set_footer(text='Last seen')
            embed.timestamp = datetime.datetime.utcfromtimestamp(username['seenAt'] / 1000.0)

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Lichess(bot))
