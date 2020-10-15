import discord
from discord.ext import commands, tasks
import datetime
import asyncio

GUILD_ID = 718378271800033318
NO_MIC_BOUNCE_ID = 758217695748554802
BOUNCE_VOICE_ID = 718378272337166396
INTRO_ID = 744131093568946229
SPECTATOR_ROLE = 720192447900286996
QM_ROLE = 718379489503215736
TEAMS = {
    718379776280231959,
    718379819498209290,
    718379874217230337,
    718380135727759421,
    718380171190599740,
    718380202907926569,
    718380238328954940,
    718380278527295510,
    718380316024242206,
    718380354339340358
}
REGISTRATION_CHANNEL_ID = 766223209938419712

def is_qm():
    def predicate(ctx):
        return ctx.author._roles.has(QM_ROLE)
    return commands.check(predicate)

def is_in_registration():
    def predicate(ctx):
        return ctx.channel.id == REGISTRATION_CHANNEL_ID
    return commands.check(predicate)

class PubQuiz(commands.Cog, name="Pub Quiz", command_attrs=dict(hidden=True)):
    """Commands exclusive to VJ's Pub Quiz Server"""
    def __init__(self, bot):
        self.bot = bot
        self.reg_open = False
        self.max_per_team = None
        
    def is_in_bounce(self, state):
        return state.channel is not None and state.channel.id == BOUNCE_VOICE_ID

    def is_out_of_bounce(self, state):
        return state.channel is None or state.channel.id != BOUNCE_VOICE_ID

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild and message.guild.id == GUILD_ID:
            if message.channel == message.guild.get_channel(INTRO_ID):
                if not message.author.guild_permissions.manage_guild:
                    await message.channel.set_permissions(message.author, send_messages=False)

    def cog_check(self, ctx):
        return ctx.guild and ctx.guild.id == GUILD_ID

    @commands.command(hidden=True)
    @commands.guild_only()
    async def resetintro(self, ctx, member: discord.Member):
        if not ctx.author == ctx.guild.owner:
            return
        await ctx.guild.get_channel(INTRO_ID).set_permissions(member, send_messages=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.guild.id != GUILD_ID:
            return

        no_mic_bounce_channel = member.guild.get_channel(NO_MIC_BOUNCE_ID)
        if self.is_out_of_bounce(before) and self.is_in_bounce(after):
            # joined bounce
            await no_mic_bounce_channel.set_permissions(member, read_messages=True)
        elif self.is_in_bounce(before) and self.is_out_of_bounce(after):
            # left bounce
            await no_mic_bounce_channel.set_permissions(member, read_messages=None)

    async def toggle_role(self, ctx, role_id):
        if any(r.id == role_id for r in ctx.author.roles):
            try:
                await ctx.author.remove_roles(discord.Object(id=role_id))
            except:
                await ctx.message.add_reaction('\N{NO ENTRY SIGN}')
            else:
                await ctx.message.add_reaction('\N{HEAVY MINUS SIGN}')
            finally:
                return

        try:
            await ctx.author.add_roles(discord.Object(id=role_id))
        except:
            await ctx.message.add_reaction('\N{NO ENTRY SIGN}')
        else:
            await ctx.message.add_reaction('\N{HEAVY PLUS SIGN}')

    @commands.command()
    @commands.guild_only()
    @is_in_registration()
    async def spectate(self, ctx):
        """Toggle the spectator role for yourself for a quiz."""
        if self.reg_open:
            await self.toggle_role(SPECTATOR_ROLE)
    
    @commands.command()
    @commands.guild_only()
    @is_qm()
    async def openregs(self, ctx, max_members_per_team: int=None):
        """Open registrations for a quiz with optional maximum members per team"""
        self.reg_open = True
        self.max_per_team = max_members_per_team or ctx.guild.member_count
        text = f'\nMax. members per team = **{max_members_per_team}**' if max_members_per_team else ''
        await ctx.send(f"Registrations now open.{text}")

    @commands.command()
    @commands.guild_only()
    @is_qm()
    async def closeregs(self, ctx):
        """Closes registrations for a quiz"""
        self.reg_open = False
        self.max_per_team = None
        await ctx.send("Registrations now closed.")

    @commands.command()
    @commands.guild_only()
    @is_in_registration()
    async def participate(self, ctx, *teammates):
        """Use to assign yourself and some optional teammates to a team.
        Teams are assigned on a first come first served basis.
        You will be given a chance to confirm your team if you have a choice."""
        if not self.reg_open:
            return
        
        all_teams = {ctx.guild.get_role(id) for id in TEAMS}
        partial_teams = {team for team in all_teams if 0 < len(team.members) < self.max_per_team}
        empty_teams = {team for team in all_teams if len(team.members) == 0}
        participants = {ctx.author}
        for arg in teammates:
            try:
                member = await commands.MemberConverter().convert(arg)
            except commands.BadArgument:
                return await ctx.send("Member not found: {}".format(arg))
            else:
                participants.add(member)

        if len(participants) > self.max_per_team:
            return await ctx.send(f"You can only participate as a team of {self.max_per_team} or less.")

        for participant in participants:
            if any([participant._roles.has(team) for team in TEAMS]):
                if participant != ctx.author:
                    return await ctx.send(f"{participant.mention} is already in a team.\nThey will first have to withdraw from their current team using `{ctx.prefix}withdraw` before joining another.")
                else:
                    return await ctx.send("You are already in a team.")
            if participant._roles.has(SPECTATOR_ROLE):
                if participant != ctx.author:
                    return await ctx.send(f"{participant.mention} has chosen to spectate.")
                else:
                    return await ctx.send("You have chosen to spectate.")
        
        def confirm_check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        available_partial_teams = {team for team in partial_teams if len(team.members) + len(participants) <= self.max_per_team}

        if len(available_partial_teams) + len(empty_teams) > 0:
            desc = f"Assigning a team to {', '.join([participant.mention for participant in participants])}.\nMention one of the available teams to assign."
            embed = discord.Embed(title="Available Teams", description=desc, colour=discord.Colour.blurple())
            empty = '\n'.join([f"{team.mention} : {len(team.members)} / {self.max_per_team}" for team in sorted(empty_teams)])
            partial = '\n'.join([f"{team.mention} : {len(team.members)} / {self.max_per_team}" for team in sorted(available_partial_teams)])
            if empty_teams:
                embed.add_field(name='Empty teams', value=empty)
            if available_partial_teams:
                embed.add_field(name='Partially filled teams', value=partial)
            embed.set_footer("Timeout in 60s")
            embed.timestamp = datetime.datetime.utcnow()
            await ctx.send(embed=embed)
            try:
                message = await self.bot.wait_for('message', timeout=60.0, check=confirm_check)
            except asyncio.TimeoutError:
                return await ctx.send("Timeout!\nCancelling operation...", delete_after=30.0)
            else:
                try:
                    role = await commands.RoleConverter().convert(ctx, message.content.split()[0])
                except commands.BadArgument:
                    return await ctx.send("Invalid Role {}".format(message.content.split()[0]))
                else:
                    if role in available_partial_teams or role in empty_teams:
                        for participant in participants:
                            await participant.add_roles(role)
                        await ctx.send(f"Assigned {', '.join(participant.mention for participant in participants)} to {role.mention}")
                    else:
                        await ctx.send(f"**{role.name}** is not available.")

        else:
            if len(partial_teams) > 0:
                embed = discord.Embed(title='No teams available to accommodate {} members', colour=discord.Colour.orange())
                embed.add_field(name="Current partially filled teams", value='\n'.join([f"{team.mention} : {len(team.members)} / {self.max_per_team}" for team in sorted(partial_teams)]))
                embed.timestamp = datetime.datetime.utcnow()
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(title='All teams full', description='All teams are currently filled up. You may still spectate for this quiz. Sorry!', colour=0xFF0000)
                embed.timestamp = datetime.datetime.utcnow()
                await ctx.send(f"<@&{QM_ROLE}> teams are filled. Please cross-check and close regs.", embed=embed)
                
    @commands.command()
    @commands.guild_only()
    @is_in_registration()
    async def withdraw(self, ctx):
        if not any([ctx.author._roles.has(team) for team in TEAMS]):
            return await ctx.send("You are not in any team.")
        for role in ctx.author.roles:
            if role.id in TEAMS:
                await ctx.author.remove_roles(role)
                break # Only one team per person.
        await ctx.send(f"Removed {ctx.author.mention} from {role.mention}")

def setup(bot):
    bot.add_cog(PubQuiz(bot))