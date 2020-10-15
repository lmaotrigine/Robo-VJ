"""
Discord bot cog to keep score during a quiz
"""
import io
import random
import asyncio
import re
import discord
from discord.ext import commands, tasks
from prettytable import PrettyTable
import asyncio
from typing import Union

class GameState(commands.Cog):
    """Keeps track of state variables during quizzes"""
    dm_pounces = {}
    mode_dict = {}
    score_dict = {}
    pounce_dict = {}
    pounce_open = {}
    in_play = {}
    buzz_dict = {}
    def __init__(self, bot):
        self.bot = bot


class Quiz(GameState):
    """Keep scores during a quiz. Requires a role named QM for the quizmaster.
    It is advised to keep the bot in a higher role than everyone else (may be lower than QM and other bots)"""
    def __init__(self, bot):
        super().__init__(bot)

    # commands
    @commands.command(aliases=['score'])
    @commands.guild_only()
    async def scores(self, ctx):
        """
        Returns current scores
        """
        msg = ""
        for item in sorted([(key, val) for key, val in self.score_dict.get(ctx.guild.id, {}).items()], key=lambda x: (x[0].name, x[1])):
            msg += f"{item[0]} : {item[1]}"
            if item[1] < 0:
                msg += " :cry:"
            msg += "\n"
        if len(msg) == 0:
            msg += "No scores yet."
        await ctx.send(msg.rstrip())

    @commands.command()
    @commands.guild_only()
    async def lb(self, ctx):
        """Returns current leaderboard"""
        msg = ""
        for score, team in sorted([(score, team) for team, score in self.score_dict.get(ctx.guild.id, {}).items()], reverse=True):
            msg += f"{team} : {score}\n"
        if len(msg) == 0:
            msg += "No scores yet."
        await ctx.send(msg.rstrip())



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
        This functionality is designed only for cases where each entity (team/member) has a dedicated text channel."""
        if ctx.author.top_role == discord.utils.get(ctx.guild.roles, name="Approved") or ctx.author.top_role == ctx.guild.default_role:
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
            await self.bot.get_channel(self.bot.pchannels[ctx.guild.id]).send(f"{ctx.channel.mention}: {answer}") # send to pounce channel
        except:
            if self.dm_pounces.get(ctx.guild.id, 'on') == 'on':
                role = discord.utils.get(ctx.guild.roles, name="QM")            #if no pounce channel, DM QM(s)
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
                    await self.bot.get_channel(self.bot.qchannels[ctx.guild.id]).send(f"{team.mention} has buzzed!")
                elif self.mode_dict[ctx.guild.id] == 'SOLO':
                    await self.bot.get_channel(self.bot.qchannels[ctx.guild.id]).send(f"{ctx.author.mention} has buzzed!")


    @commands.command()
    @commands.guild_only()
    async def shady(self, ctx):
        """Use for extremely obscure fundae that cannot be worked out"""
        if self.in_play[ctx.guild.id]:
            msg = await ctx.send(f"{discord.utils.get(ctx.guild.roles, name='QM').mention} Pah! Whatte!")
            await msg.add_reaction("🇸")
            await msg.add_reaction("🇭")
            await msg.add_reaction("🇦")
            await msg.add_reaction("🇩")
            await msg.add_reaction("🇾")

    # error handling



class QMOnly(GameState, name="QM Commands"):
    """Commands only QM can use"""
    team_regex = re.compile("<@&([0-9]+)>")
    member_regex = re.compile("<@!?([0-9]+)>")
    points_regex = re.compile("(\d*\.?\d*)\s<@[!&]?([0-9]+)>")
    def __init__(self, bot):
        super().__init__(bot)

    @commands.command()
    @commands.guild_only()
    async def assign(self, ctx, members: commands.Greedy[discord.Member], team: discord.Role):
        """
        Assign members to teams.
        This won't work for the server owner.
        Usage: assign @member1 @member2 @team-01...
        """
        if not "QM" in [role.name for role in ctx.author.roles] and not ctx.author == ctx.guild.owner:
            return
        edited = []
        higher_roles = []
        for member in members:
            await asyncio.sleep(1)
            try:
                await member.edit(roles=[discord.utils.get(ctx.guild.roles, name='Approved'), team])
                edited.append(member.mention)
            except discord.Forbidden:
                await ctx.send(f"Couldn't edit `{member.display_name}#{member.discriminator}`. Trying to add to team without removing other roles...")
                try:
                    await member.add_roles(team)
                    edited.append(member.mention)
                    higher_roles.append(member.mention)
                except discord.Forbidden:
                    await ctx.send(f"Couldn't add `{member.display_name}#{member.discriminator}` to `{team.name}`. Contact the server owner to resolve permissions")

        to_send = f"{', '.join(edited)} assigned to {team.mention}."
        if higher_roles:
            to_send += f"\n{', '.join(higher_roles)} still {'have' if len(higher_roles) > 1 else 'has'} other roles."
        await ctx.send(to_send)

    @commands.command(name="cleanup", aliases=['clean'])
    @commands.guild_only()
    async def cleanup_teams(self, ctx):
        """Clears all team and spectator roles. Has a cooldown in place to avoid hitting rate limits."""
        if not "QM" in [role.name for role in ctx.author.roles]:
            return
        teams = [role for role in guild.roles if role.name.lower().startswith('team')]
        teams.append(discord.utils.get(guild.roles, name="Spectator"))
        for team in teams:
            await (bot.get_command("purgeroles"))(ctx, role)
            await asyncio.sleep(1)
            await ctx.send(f"Purged {team}")
        await ctx.send("Cleanup complete.")

    @commands.command(usage="points [<points> <team | member>...]")
    @commands.guild_only()
    async def points(self, ctx, *, args):
        """
        Award points by mentioning a team role or member
        e.g points 10 @team-01 10 @team-02 20 @team-03 etc
        """
        if not "QM" in [role.name for role in ctx.author.roles]:
            return await ctx.send("Only QM is Gwad")
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
            await ctx.send(random.choice(["Gotcha :+1:", "Roger That!", "Aye Aye, Cap'n!", "Done and done."]))

    @points.error
    async def points_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            pass
        else:
            await ctx.send("Mismatch between teams and points entered. Please try again.")

    @commands.command()
    @commands.guild_only()
    async def reset(self, ctx):
        """Resets the buzzers during buzzer round."""
        if self.in_play[ctx.guild.id]:
            if not "QM" in [role.name for role in ctx.author.roles]:
                return
            self.buzz_dict[ctx.guild.id] = False
            await ctx.message.add_reaction("👍")

    @commands.command()
    @commands.guild_only()
    async def pounces(self, ctx):
        """Displays pounces till the moment of invoking. Does not close pounce"""
        if not "QM" in [role.name for role in ctx.author.roles]:
            return
        msg = ""
        for team, pounce in self.pounce_dict[ctx.guild.id].items():
            msg += f"{team.name} : {pounce}\n"
        await ctx.send(msg.rstrip())

    @commands.command()
    @commands.guild_only()
    async def podium(self, ctx):
        """Displays current standings in the current channel (Honestly not so different from lb, I'm just lazy)"""
        if not "QM" in [role.name for role in ctx.author.roles]:
            return
        lb = [(team, score) for score, team in sorted([(score, team) for team, score in self.score_dict[ctx.guild.id].items()], reverse=True)]
        idx = 0
        pod = []
        while idx < 3:
            if len(lb) < 2:
                break
            if lb[0][1] == lb[1][1]:
                idx -= 1
            pod.append(lb.pop(0))
            idx += 1
        msg = "Final podium:\n\n"
        for (team, score) in pod:
            msg += f"{team.mention} : {score}\n"
        msg += "\n"
        for team, score in lb:
            msg += f"{team.mention} : {score}\n"
        await ctx.send(msg.rstrip())

    @commands.command()
    @commands.guild_only()
    async def announcewin(self, ctx):
        """Displays the final scores in the questions channel and ends the quiz"""
        if not "QM" in [role.name for role in ctx.author.roles]:
            return
        lb = [(team, score) for score, team in sorted([(score, team) for team, score in self.score_dict[ctx.guild.id].items()], reverse=True)]
        idx = 0
        pod = []
        while idx < 3:
            if len(lb) < 2:
                break
            if lb[0][1] == lb[1][1]:
                idx -= 1
            pod.append(lb.pop(0))
            idx += 1
        msg = "Final standings\n\n"
        pod_idx = 0
        for (team, score) in pod:
            msg += f"{team.mention} : {score}\n"
        msg += "\n"
        for team, score in lb:
            msg += f"{team.mention} : {score}\n"
        self.score_dict.pop(ctx.guild.id)
        self.mode_dict.pop(ctx.guild.id)
        self.pounce_dict.pop(ctx.guild.id)
        self.pounce_open[ctx.guild.id] = False
        self.in_play[ctx.guild.id] = False
        try:
            react_to = await self.bot.get_channel(self.bot.qchannels[ctx.guild.id]).send(msg.rstrip())
        except KeyError:
            if not ctx.guild.system_channel is None:
                react_to = await ctx.guild.system_channel.send(msg.rstrip())
            else:
                react_to = await ctx.send(msg.rstrip())

        await react_to.add_reaction("🇹")
        await react_to.add_reaction("🇭")
        await react_to.add_reaction("🇦")
        await react_to.add_reaction("🇳")
        await react_to.add_reaction("🇰")
        await react_to.add_reaction("🇾")
        await react_to.add_reaction("🇴")
        await react_to.add_reaction("🇺")

    @commands.command()
    @commands.guild_only()
    async def close(self, ctx):
        """Closes pounce for a question."""
        if not "QM" in [role.name for role in ctx.author.roles]:
            return
        self.pounce_open[ctx.guild.id] = False
        if ctx.channel.id == self.bot.pchannels.get(ctx.guild.id):
            msg = "Pounce closed. Final pounces:\n\n"
            for team, pounce in self.pounce_dict[ctx.guild.id].items():
                msg += f"{team.name} : {pounce}\n"
            await ctx.send(msg.rstrip())
        else:
            await ctx.message.delete()
            await ctx.send("Pounce closed.")
        #self.pounce_dict[ctx.guild.id] = dict()

    @commands.command()
    @commands.guild_only()
    async def open(self, ctx):
        """Open pounces for a question. This must be done if you are using the bot to track pounces."""
        if not "QM" in [role.name for role in ctx.author.roles]:
            return
        self.pounce_open[ctx.guild.id] = True
        await ctx.message.delete()
        await ctx.send("Pounces open now.")
        self.pounce_dict[ctx.guild.id] = dict()

    @commands.command()
    @commands.guild_only()
    async def DMpounces(self, ctx, toggle=None):
        """Toggle whether pounces are sent to the QMs via DM.
        If there is a dedicated guild channel, then that is used instead, regardless of this setting."""
        if "QM" not in [role.name for role in ctx.author.roles]:
            return
        if toggle:
            if toggle.lower() not in ["on", "off"]:
                await ctx.send("Please enter a valid option `on` or `off`")
                return
            self.dm_pounces[ctx.guild.id] = toggle
            await ctx.send(f"Pounce DMs to QMs has been turned {toggle}.")
        else:
            await ctx.send(f"Pounce DMs to QMs is {self.dm_pounces.get(ctx.guild.id, 'on')}")

    @commands.command()
    @commands.guild_only()
    async def newquiz(self, ctx, mode=None):
        """
        Start a new quiz
        """
        if "QM" not in [role.name for role in ctx.author.roles]:
            await ctx.send(f"Ask {ctx.guild.owner.mention} to make you QM")
            return
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

    @commands.command(hidden=True, aliases=['in_play', 'safety', 'safe', 'state'])
    async def game_state(self, ctx):
        if ctx.author.id != 411166117084528640:
            return
        stateinfo = PrettyTable()
        stateinfo.field_names = ['Guild', 'Owner', 'in_play']
        for guild in self.bot.guilds:
            stateinfo.add_row([guild.name, f'{guild.owner.name}#{guild.owner.discriminator}', self.in_play.get(str(guild.id), False)])
        res = f"```{stateinfo}```"
        if len(res) > 2000:
            fp = io.BytesIO(res.encode('utf-8'))
            await ctx.send("Too many results...", file=discord.File(fp, 'results.txt'))
        else:
            await ctx.send(f"```{stateinfo}```")

    @commands.command()
    @commands.guild_only()
    async def endquiz(self, ctx):
        """Ends quiz and resets scores and that's about it. No bells and whistles"""
        if not "QM" in [role.name for role in ctx.author.roles]:
            return
        self.score_dict.pop(ctx.guild.id)
        self.mode_dict.pop(ctx.guild.id)
        self.pounce_dict.pop(ctx.guild.id)
        self.pounce_open[ctx.guild.id] = False
        self.in_play[ctx.guild.id] = False
        await ctx.send("Quiz conluded. Scores reset.")

def setup(bot):
    bot.add_cog(Quiz(bot))
    bot.add_cog(QMOnly(bot))
