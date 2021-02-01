"""
Discord bot cog to keep score during a quiz
"""
import datetime
import io
import random
import asyncio
import re
import discord
from discord.ext import commands, tasks
from prettytable import PrettyTable
import asyncio
from typing import Union
from .utils import checks, db
from itertools import groupby

class QuizConfig(db.Table, table_name='quiz_config'):
    guild_id = db.Column(db.Integer(big=True), primary_key=True)
    qchannel = db.Column(db.Integer(big=True))
    pchannel = db.Column(db.Integer(big=True))

def is_qm():
    async def predicate(ctx):
        if ctx.guild is None:
            return False
        if await ctx.bot.is_owner(ctx.author):
            return True
        try:
            return discord.utils.get(ctx.author.roles, name='QM') is not None  # TODO: Add this to database?
        except AttributeError:  # For some reason the author may be a User
            member = ctx.guild.get_member(ctx.author.id)
            if member is None:
                if ctx.guild.chunked:  # RIP
                    return False
                member = await ctx.guild.fetch_member(ctx.author.id)
            try:
                return discord.utils.get(member.roles, name='QM') is not None
            except discord.NotFound:  # RIP x2
                return False
    return commands.check(predicate)

class Quiz(commands.Cog):
    """Keep scores during a quiz. Requires a role named QM for the quizmaster.
    It is advised to keep the bot in a higher role than everyone else (may be lower than QM and other bots)"""

    team_regex = re.compile(r"<@&([0-9]+)>")
    member_regex = re.compile(r"<@!?([0-9]+)>")
    points_regex = re.compile(r"(\d*\.?\d*)\s<@[!&]?([0-9]+)>")
    
    def __init__(self, bot):
        self.bot = bot
        self.dm_pounces = {}
        self.mode_dict = {}
        self.score_dict = {}
        self.pounce_dict = {}
        self.pounce_open = {}
        self.in_play = {}
        self.buzz_dict = {}
        self.qchannels = {}
        self.pchannels = {}
        self.task = self.bot.loop.create_task(self._prepare_channels())

    async def _prepare_channels(self):
        async with self.bot.pool.acquire() as con:
            records = await con.fetch("SELECT guild_id, qchannel, pchannel FROM quiz_config;")
            for record in records:
                self.qchannels[record['guild_id']] = record['qchannel']
                self.pchannels[record['guild_id']] = record['pchannel']
    
    def cog_unload(self):
        self.task.cancel()

    @commands.command()
    @commands.guild_only()
    @checks.is_guild_owner()
    async def qchannel(self, ctx, channel: discord.TextChannel=None):
        channel = channel or ctx.channel
        self.qchannels[ctx.guild.id] = channel.id
        query = "INSERT INTO quiz_config (guild_id, qchannel) VALUES ($2, $1) ON CONFLICT (guild_id) DO UPDATE SET qchannel = $1 WHERE quiz_config.guild_id = $2;"
        await ctx.db.execute(query, channel.id, ctx.guild.id)
        await ctx.send(f"{channel.mention} is marked as the questions channel.")

    @commands.command()
    @commands.guild_only()
    @checks.is_guild_owner()
    async def pchannel(self, ctx, channel: discord.TextChannel=None):
        channel = channel or ctx.channel
        self.pchannels[ctx.guild.id] = channel.id
        query = "INSERT INTO quiz_config (guild_id, pchannel) VALUES ($2, $1) ON CONFLICT (guild_id) DO UPDATE SET pchannel = $1 WHERE quiz_config.guild_id = $2;"
        await ctx.db.execute(query, channel.id, ctx.guild.id)
        await ctx.send(f"{channel.mention} is now the channel where pounces will appear.")

        
    @commands.command(aliases=['score'])
    @commands.guild_only()
    async def scores(self, ctx):
        """
        Returns current scores
        """
        embed = discord.Embed(title='Current Scores', colour=discord.Colour.blurple())
        embed.description = '\n'.join(f'{team.mention}: `{score}`' for team, score in sorted(self.score_dict.get(ctx.guild.id, {}).items(), key=lambda i: i[0].name))
        if len(self.score_dict.get(ctx.guild.id, {}).keys()) == 0:
            return await ctx.send('No scores yet.')
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=False, roles=False))

    @commands.command()
    @commands.guild_only()
    async def lb(self, ctx):
        """Returns current leaderboard."""
        embed = discord.Embed(title='Current Leaderboard', colour=discord.Colour.blurple())
        embed.description = '\n'.join(f'{team.mention}: `{score}`' for team, score in sorted(self.score_dict.get(ctx.guild.id, {}).items(), key=lambda i: i[1], reverse=True))
        if len(self.score_dict.get(ctx.guild.id, {}).keys()) == 0:
            return await ctx.send('No scores yet.')
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=False, roles=False))

    @commands.command()
    @commands.guild_only()
    async def op(self, ctx, team:Union[discord.Role, discord.Member] = None):
        """Use to show your displeasure at unbalanced teams"""
        if team is None:
            try:
                OP = [(team, score) for score, team in sorted([(score, team) for team, score in self.score_dict[ctx.guild.id].items()], reverse=True)][0][0]
            except KeyError:
                OP = ctx.guild.me.top_role
        else:
            OP = team

        msg = await ctx.send(f"{OP.mention} OP")
        await msg.add_reaction("🇴")
        await msg.add_reaction("🇵")

    @commands.command(aliases=['p'])
    @commands.guild_only()
    async def pounce(self, ctx, *, answer=None):
        """Pounce on a question. Pounces appear either in a designated channel (if available) or sent to the QM(s) via DM.
        This functionality is designed only for cases where each entity (team/member) has a dedicated text channel.
        """
        if ctx.author.top_role == ctx.guild.default_role:
            return
        try:
            if not self.in_play[ctx.guild.id]:
                return
        except KeyError:
            return
        try:
            if not self.pounce_open[ctx.guild.id]:
                await ctx.send("Pounce is closed, sorry")
                return
        except KeyError:
            return

        if "spectator" in [role.name.lower() for role in ctx.author.roles]:
            await ctx.send("Your enthusiasm is admirable. Please participate next time :slight_smile:")
            return

        if answer is None:
            await ctx.send("Please enter the entire answer in a single message and pounce again.")
            return

        if ctx.channel in self.pounce_dict[ctx.guild.id].keys():
            await ctx.send("It seems you have already pounced. If you feel this is an error, please tag @QM")
            return

        self.pounce_dict[ctx.guild.id][ctx.channel] = answer
        try:
            await self.bot.get_channel(self.pchannels[ctx.guild.id]).send(f"{ctx.channel.mention}: {answer}")  # send to pounce channel
        except (AttributeError, KeyError):
            if self.dm_pounces.get(ctx.guild.id, 'on') == 'on':
                role = discord.utils.get(ctx.guild.roles, name="QM")  #if no pounce channel, DM QM(s)
                for member in role.members:
                    await member.send(f"{ctx.channel.mention}: {answer}", delete_after=21600.0)
        finally:
            await ctx.send("Noted :+1:")

    @commands.command()
    @commands.guild_only()
    async def buzz(self, ctx):
        """ To buzz on buzzer rounds. Takes no arguments."""
        if ctx.author.top_role == discord.utils.get(ctx.guild.roles, name="Approved") or ctx.author.top_role == ctx.guild.default_role:
            return
        if "spectator" in [role.name.lower() for role in ctx.author.roles]:
            await ctx.send("Your enthusiasm is admirable. Please participate next time :slight_smile:")
            return
        if self.in_play.get(ctx.guild.id, False):
            if not self.buzz_dict[ctx.guild.id]:
                self.buzz_dict[ctx.guild.id] = True
                await ctx.message.add_reaction("🚨")
                if self.mode_dict[ctx.guild.id] == 'TEAMS':
                    team = [role for role in ctx.author.roles if role.name.lower().startswith("team")][0]
                    await self.bot.get_channel(self.qchannels[ctx.guild.id]).send(f"{team.mention} has buzzed!")
                elif self.mode_dict[ctx.guild.id] == 'SOLO':
                    await self.bot.get_channel(self.qchannels[ctx.guild.id]).send(f"{ctx.author.mention} has buzzed!")

    @commands.command()
    @commands.guild_only()
    async def shady(self, ctx):
        """Use for extremely obscure fundae that cannot be worked out"""
        if self.in_play.get(ctx.guild.id):
            msg = await ctx.send(f"{discord.utils.get(ctx.guild.roles, name='QM').mention} Pah! Whatte!")
            await msg.add_reaction("🇸")
            await msg.add_reaction("🇭")
            await msg.add_reaction("🇦")
            await msg.add_reaction("🇩")
            await msg.add_reaction("🇾")

    @commands.command(usage="[<points> <team | member>...]")
    @commands.guild_only()
    @is_qm()
    async def points(self, ctx, *, args):
        """
        Award points by mentioning a team role or member
        e.g points 10 @team-01 10 @team-02 20 @team-03 etc
        """
            
        if not self.in_play.get(ctx.guild.id, False):
            return await ctx.send(random.choice([f"QM please start a `{ctx.prefix}newquiz <solo|teams>` to begin.",
                f"Please run a `{ctx.prefix}newquiz <solo|teams>` first."]))
        if self.mode_dict[ctx.guild.id] == "TEAMS":
            if re.search(self.member_regex, args):
                return await ctx.send("Mention roles, not users.")
        if self.mode_dict[ctx.guild.id] == "SOLO":
            if re.search(self.team_regex, args):
                return await ctx.send("Mention members, not roles.")
        for points, id in re.findall(self.points_regex, args):
            if self.mode_dict[ctx.guild.id] == 'SOLO':
                self.score_dict[ctx.guild.id][ctx.guild.get_member(int(id))] = self.score_dict[ctx.guild.id].get(ctx.guild.get_member(id), 0) + float(points)
            elif self.mode_dict[ctx.guild.id] == 'TEAMS':
                self.score_dict[ctx.guild.id][ctx.guild.get_role(int(id))] = self.score_dict[ctx.guild.id].get(ctx.guild.get_role(id), 0) + float(points)
        await ctx.send(random.choice(["Gotcha :+1:", "Roger That!", "Aye Aye, Cap'n!", "Done and done.", "\N{OK HAND SIGN}"]))

    @points.error
    async def points_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            if ctx.guild is not None:
                return await ctx.send("Only QM is Gwad")
        else:
            await ctx.send("Mismatch between teams and points entered. Please try again.")

    @commands.command()
    @commands.guild_only()
    @is_qm()
    async def reset(self, ctx):
        """Resets the buzzers during buzzer round."""
        if self.in_play[ctx.guild.id]:
            self.buzz_dict[ctx.guild.id] = False
            await ctx.message.add_reaction("👍")

    @commands.command()
    @commands.guild_only()
    @is_qm()
    async def pounces(self, ctx):
        """Displays pounces till the moment of invoking. Does not close pounce"""
        if not self.in_play.get(ctx.guild.id, False):
            return
        embed = discord.Embed(title='Pounces so far', description='\n'.join(f"{team.name} : {answer}" for team, answer in self.pounce_dict.get(ctx.guild.id, {}).items()))
        embed.timestamp=datetime.datetime.utcnow()
        embed.colour = discord.Colour.green() if self.pounce_open.get(ctx.guild.id, False) else discord.Colour.red()
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    @is_qm()
    async def announcewin(self, ctx):
        """Displays the final scores in the questions channel and ends the quiz"""

        lb = sorted(self.score_dict.get(ctx.guild.id, {}).items(), key=lambda i: i[1], reverse=True)
        embed = discord.Embed(title="Final Scores", colour=discord.Colour.blurple())

        medals = ['\N{FIRST PLACE MEDAL}', '\N{SECOND PLACE MEDAL}', '\N{THIRD PLACE MEDAL}']
        while len(medals) < len(lb):
            medals.append('\N{SPORTS MEDAL}')

        all_teams = [['', list(teams)] for _, teams in groupby(lb, lambda i: i[1])]

        for i in range(len(all_teams)):
            all_teams[i][0] = medals[i]

        if len(all_teams) > 3:
            top, rest = all_teams[:3], all_teams[3:]
            top_value = []
            for item in top:
                medal = item[0]
                for team , score in item[1]:
                    top_value.append(f'{medal} {team.mention}: `{score}`')
            rest_value = []
            for item in rest:
                medal = item[0]
                for team, score in item[1]:
                    rest_value.append(f'{medal} {team.mention}: `{score}`')
            embed.add_field(name='\u200b', value='\n'.join(top_value))
            embed.add_field(name='\u200b', value='\n'.join(rest_value))
        else:
            value = []
            for item in all_teams:
                medal = item[0]
                for team, score in item[1]:
                    value.append(f'{medal} {team.mention}: `{score}`')
            embed.description = '\n'.join(value)

        embed.set_footer(text='Thank you!')
        self.score_dict.pop(ctx.guild.id)
        self.mode_dict.pop(ctx.guild.id)
        self.pounce_dict.pop(ctx.guild.id)
        self.pounce_open[ctx.guild.id] = False
        self.in_play[ctx.guild.id] = False
        try:
            await self.bot.get_channel(self.qchannels[ctx.guild.id]).send(embed=embed, allowed_mentions=discord.AllowedMentions(users=False, roles=False))
        except KeyError:
            if ctx.guild.system_channel is not None:
                await ctx.guild.system_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=False, roles=False))
            else:
                await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=False, roles=False))

    @commands.command()
    @commands.guild_only()
    @is_qm()
    async def close(self, ctx):
        """Closes pounce for a question."""
        if not self.in_play.get(ctx.guild.id):
            return
        self.pounce_open[ctx.guild.id] = False
        if ctx.channel.id == self.pchannels.get(ctx.guild.id):
            embed = discord.Embed(title='Pounce closed. Final pounces:', colour=0xFF0000)
            embed.description = '\n'.join(f'{team.mention}: {pounce}' for team, pounce in self.pounce_dict[ctx.guild.id].items())
            await ctx.send(embed=embed)
        else:
            await ctx.message.delete()
            await ctx.send(embed=discord.Embed(title="Pounce closed.", colour=0xFF0000))

    @commands.command()
    @commands.guild_only()
    @is_qm()
    async def open(self, ctx):
        """Open pounces for a question."""
        if not self.in_play.get(ctx.guild.id):
            return
        self.pounce_open[ctx.guild.id] = True
        self.pounce_dict[ctx.guild.id] = dict()
        await ctx.message.delete()
        await ctx.send(embed=discord.Embed(title="Pounces open now.", colour=discord.Colour.green()))
        
    @commands.command()
    @commands.guild_only()
    @is_qm()
    async def DMpounces(self, ctx, toggle=None):
        """Toggle whether pounces are sent to the QMs via DM.
        If there is a dedicated guild channel, then that is used instead, regardless of this setting.
        """
        if toggle:
            if toggle.lower() not in ["on", "off"]:
                await ctx.send("Please enter a valid option (`on` or `off`)")
                return
            self.dm_pounces[ctx.guild.id] = toggle
            await ctx.send(f"Pounce DMs to QMs has been turned {toggle}.")
        else:
            await ctx.send(f"Pounce DMs to QMs is {self.dm_pounces.get(ctx.guild.id, 'on')}")

    @commands.command()
    @commands.guild_only()
    @is_qm()
    async def newquiz(self, ctx, mode=None):
        """
        Start a new quiz
        """
        if not mode or mode.upper() not in ['SOLO', 'TEAMS']:
            return await ctx.send(f"Please enter whether the quiz is solo or teams\ne.g. `{ctx.prefix}newquiz solo`")
        self.mode_dict[ctx.guild.id] = mode.upper()
        self.score_dict[ctx.guild.id] = dict()
        self.pounce_dict[ctx.guild.id] = dict()
        self.pounce_open[ctx.guild.id] = False
        self.in_play[ctx.guild.id] = True
        self.buzz_dict[ctx.guild.id] = False
        if mode.upper() == "TEAMS":
            await ctx.send("Teams gathered. Scores reset.")
        elif mode.upper() =="SOLO":
            await ctx.send("Users gathered. Scores reset.")

    @newquiz.error
    async def newquiz_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            return await ctx.send(f"Ask {ctx.guild.owner.mention} to make you QM.", allowed_mentions=discord.AllowedMentions(users=False))

    @commands.command(hidden=True, aliases=['in_play', 'safety', 'safe', 'state'])
    @commands.is_owner()
    async def game_state(self, ctx):
        """Shows current state of play across all servers."""
        stateinfo = PrettyTable()
        stateinfo.field_names = ['Guild', 'Owner', 'in_play']
        for guild in self.bot.guilds:
            stateinfo.add_row([guild.name, f'{guild.owner.name}#{guild.owner.discriminator}', self.in_play.get(str(guild.id), False)])
        res = f"```{stateinfo}```"
        if len(res) > 2000:
            fp = io.BytesIO(res.encode('utf-8'))
            await ctx.send("Too many results...", file=discord.File(fp, 'results.txt'))
        else:
            await ctx.send(res)

    @commands.command()
    @commands.guild_only()
    @is_qm()
    async def endquiz(self, ctx):
        """Ends quiz and resets scores and that's about it. No bells and whistles"""
        self.score_dict.pop(ctx.guild.id, None)
        self.mode_dict.pop(ctx.guild.id, None)
        self.pounce_dict.pop(ctx.guild.id, None)
        self.pounce_open[ctx.guild.id] = False
        self.in_play[ctx.guild.id] = False
        await ctx.send("Quiz conluded. Scores reset.")

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 2, commands.BucketType.member)
    @commands.check_any(is_qm(), checks.is_admin())
    async def purgeroles(self, ctx, *entities):
        """Purges all roles of a member, or all members of a role.

        You need to be QM or an admin to use this.
        You cannot remove roles that are higher or equal to your top role.
        
        If both members and roles are passed, the members lose all roles lower
        than your top role, and all members of the role specified are removed.

        You cannot specify a role with more than 10 members, or more than 10 entities
        in a single invocation due to rate limits.

        For more granular control, you should conider adding and removing roles manually.
        """
        members = set()
        roles = set()
        if len(entities) > 10:
            return await ctx.send("Too many arguments. Split these up and try again.")
        async with ctx.typing():
            for entity in entities:
                try:
                    members.add(await commands.MemberConverter().convert(ctx, entity))
                except commands.BadArgument:
                    try:
                        roles.add(await commands.RoleConverter().convert(ctx, entity))
                    except commands.BadArgument:
                        await ctx.send(f"Unable to find role or member matching '{entity}'")

            roles = [role for role in roles if role < ctx.author.top_role]
            mems = set()
            for role in roles:
                mems.update(role.members)
            for member in mems:
                await member.remove_roles(*roles)

            for member in members:
                _roles = [role for role in member.roles if role < ctx.author.top_role]
                await member.remove_roles(*_roles)
        await ctx.send('\N{OK HAND SIGN}')


def setup(bot):
    bot.add_cog(Quiz(bot))
