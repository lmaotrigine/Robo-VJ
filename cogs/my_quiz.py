import discord
from discord.ext import commands, tasks
import datetime
import asyncio
import sys
import traceback
import json
import os
from .utils import checks

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
SOLO_PARTICIPANT_ROLE = 766590219814043648
APPROVED_ROLE = 743891769024053349
REGISTRATION_CHANNEL_ID = 766223209938419712
ANNOUNCEMENT_CHANNEL_ID = 743834763965759499

def is_qm():
    def predicate(ctx):
        return ctx.author._roles.has(QM_ROLE)
    return commands.check(predicate)

def is_in_registration():
    def predicate(ctx):
        return ctx.channel.id == REGISTRATION_CHANNEL_ID
    return commands.check(predicate)


class PubQuiz(commands.Cog, name="Pub Quiz"):
    """Commands exclusive to VJ's Pub Quiz Server"""
    def __init__(self, bot):
        self.bot = bot
        self.reg_open = False
        self.max_per_team = None
        self.AUTOAPPROVE = {}
        if not os.path.isdir('assets'):
            os.mkdir('assets')
        try:
            with open('assets/autoapprove_messages.json', 'r') as file:
                self.messages = json.load(file)
        except:
            open('assets/autoapprove_messages.json', 'w').close()
            self.messages = {}
        
        try:
            with open("assets/server_rules.txt", "r") as file:
                self.title, self.rule_head, self.rules, self.honour_head, self.honour, self.privacy_head, self.privacy = file.read().split('$')
            self.rules = self.rules.split('\n\n')
        except:
            pass
        
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

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if str(payload.emoji) == "✅" and payload.guild_id and payload.user_id != self.bot.user.id:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            if self.messages.get(str(payload.guild_id)) == payload.message_id:
                if not member._roles.has(APPROVED_ROLE):
                    await member.add_roles(guild.get_role(APPROVED_ROLE))               
                channel = self.bot.get_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)
                await message.remove_reaction('✅', member)


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
    async def openregs(self, ctx, max_members_per_team: int):
        """Open registrations for a quiz."""
        self.reg_open = True
        self.max_per_team = max_members_per_team
        text = f'\nMax. members per team = **{max_members_per_team}**' if max_members_per_team else ''
        await ctx.send(f"Registrations now open.{text}")
        announcement = ctx.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        await announcement.send(f"@here\nRegistrations are now open for teams of {max_members_per_team}. Register in {self.bot.get_channel(REGISTRATION_CHANNEL_ID).mention}")

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            pass
        if isinstance(error, commands.MissingRequiredArgument) or isinstance(error, commands.BadArgument):
            await ctx.send(error)
        else:
            error = getattr(error, 'original', error)
            print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    @commands.command()
    @commands.guild_only()
    @is_qm()
    async def closeregs(self, ctx):
        """Closes registrations for a quiz"""
        self.reg_open = False
        self.max_per_team = None
        await ctx.send("Registrations now closed.")
        await self.bot.get_channel(ANNOUNCEMENT_CHANNEL_ID).send("@here\nRegistrations are now closed.")

    @commands.command()
    @commands.guild_only()
    @is_in_registration()
    async def participate(self, ctx, *teammates):
        """Use to assign yourself and some optional teammates to a team.
        Teams are assigned on a first come first served basis.
        You will be given a chance to confirm your team if you have a choice."""
        if not self.reg_open:
            return
        
        if self.max_per_team == 1:
            if ctx.author._roles.has(SOLO_PARTICIPANT_ROLE):
                    return await ctx.send("You are already registered to participate.")
            if teammates:
                await ctx.send("Ignoring arguments as this is a solo quiz...", delete_after=10.0)
            await (ctx.bot.get_command('assign'))(ctx, ctx.author, ctx.guild.get_role(SOLO_PARTICIPANT_ROLE))
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
            empty = '\n'.join([f"{team.mention} : {len(team.members)} / {self.max_per_team}" for team in sorted(empty_teams, key=lambda t: t.name)])
            partial = '\n'.join([f"{team.mention} : {len(team.members)} / {self.max_per_team}" for team in sorted(available_partial_teams, key=lambda t: t.name)])
            if empty_teams:
                embed.add_field(name='Empty teams', value=empty)
            if available_partial_teams:
                embed.add_field(name='Partially filled teams', value=partial)
            embed.set_footer(text="Timeout in 60s", icon_url=ctx.guild.icon_url)
            embed.timestamp = datetime.datetime.utcnow()
            await ctx.send(embed=embed)
            done = False
            while not done:
                try:
                    message = await self.bot.wait_for('message', timeout=60.0, check=confirm_check)
                except asyncio.TimeoutError:
                    return await ctx.send(f"{ctx.author.mention} Timeout!\nCancelling operation...", delete_after=30.0)
                else:
                    try:
                        role = await commands.RoleConverter().convert(ctx, message.content.split()[0])
                    except commands.BadArgument:
                        await ctx.send("Invalid Role {}".format(message.content.split()[0]), delete_after=10.0)
                    else:
                        available_teams = {team for team in all_teams if len(team.members) + len(participants) <= self.max_per_team}
                        if role in available_teams:
                            for participant in participants:
                                await participant.add_roles(role)
                                done = True
                                break
                            await ctx.send(f"Assigned {', '.join(participant.mention for participant in participants)} to {role.mention}")
                        else:
                            await ctx.send(f"**{role.name}** is not available.", delete_after=10.0)

        else:
            if len(partial_teams) > 0:
                embed = discord.Embed(title='No teams available to accommodate {} members', colour=discord.Colour.orange())
                embed.add_field(name="Current partially filled teams", value='\n'.join([f"{team.mention} : {len(team.members)} / {self.max_per_team}" for team in sorted(partial_teams, key=lambda t: t.name)]))
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
        """Withdraw your participation from a quiz."""
        if not self.reg_open:
            return
        if self.max_per_team == 1:
            if not ctx.author._roles.has(SOLO_PARTICIPANT_ROLE):
                return await ctx.send("You are not registered to participate.")
            await ctx.author.remove_roles(ctx.guild.get_role(SOLO_PARTICIPANT_ROLE))
            return await ctx.send(f"{ctx.author.mention} is no longer a participant.")
        if not any([ctx.author._roles.has(team) for team in TEAMS]):
            return await ctx.send("You are not in any team.")
        for role in ctx.author.roles:
            if role.id in TEAMS:
                await ctx.author.remove_roles(role)
                break # Only one team per person.
        await ctx.send(f"Removed {ctx.author.mention} from {role.mention}")

    @commands.command()
    @commands.guild_only()
    @commands.check_any(is_qm(), checks.is_mod())
    async def assign(self, ctx, members: commands.Greedy[discord.Member], role: discord.Role):
        """
        Assign members to roles.
        This won't work for the server owner.
        Usage: assign @member1 @member2 @team-01...

        You must have the manage server permission or be a QM to use this.
        """

        edited = []
        higher_roles = []
        for member in members:
            await asyncio.sleep(1)
            try:
                await member.edit(roles=[ctx.guild.get_role(APPROVED_ROLE), role])
                edited.append(member.mention)
            except discord.Forbidden:
                await ctx.send(f"Couldn't edit `{member.display_name}#{member.discriminator}`. Trying to add roles without removing other roles...")
                try:
                    await member.add_roles(role)
                    edited.append(member.mention)
                    higher_roles.append(member.mention)
                except discord.Forbidden:
                    await ctx.send(f"Couldn't add `{member.display_name}#{member.discriminator}` to `{team.name}`. Contact the server owner to resolve permissions")

        to_send = f"{', '.join(edited)} assigned to {role.mention}."
        if higher_roles:
            to_send += f"\n{', '.join(higher_roles)} still {'have' if len(higher_roles) > 1 else 'has'} other roles."
        await ctx.send(to_send)

    @commands.command(name="cleanroles")
    @commands.guild_only()
    @is_qm()
    async def cleanup_teams(self, ctx):
        """Clears all team and spectator roles. Has a cooldown in place to avoid hitting rate limits."""
        teams = [ctx.guild.get_role(team) for team in TEAMS]
        teams.append(ctx.guild.get_role(SPECTATOR_ROLE))
        teams.append(ctx.guild.get_role(QM_ROLE))
        await bot.get_command('purgeroles')(ctx, *teams)
        await ctx.send("Cleanup complete.")

    @commands.command(hidden=True)
    @commands.guild_only()
    @checks.is_admin()
    async def approve(self, ctx, member:discord.Member):
        """Grants role Approved to the user"""

        approved = ctx.guild.get_role(APPROVED_ROLE)
        if member._roles.has(APPROVED_ROLE):
            await ctx.send(f"{member.mention} is already approved.", delete_after=15.0)
            await ctx.message.delete()
            return
        
        await member.add_roles(approved)
        
        await ctx.message.delete()
        embed = discord.Embed(title=f"Approved {member}", colour=discord.Colour.green(), timestamp=datetime.datetime.utcnow())
        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url, url=f"https://discordapp.com/users/{ctx.author.id}")
        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon_url)
        await ctx.guild.system_channel.send(embed=embed)

    @commands.command(hidden=True)
    @commands.guild_only()
    @checks.is_admin()
    async def unapprove(self, ctx, member: discord.Member):
        """Revokes approval for a member"""
        if not member._roles.has(APPROVED_ROLE):
            await ctx.send(f"{member.mention} has not been approved.", delete_after=15.0)
            await ctx.message.delete()
            return
        
        await member.remove_roles(ctx.guild.get_role(APPROVED_ROLE))
        
        await ctx.message.delete()
        embed=discord.Embed(title=f"Revoked approval for {member}.", colour=0xFF0000, timestamp=datetime.datetime.utcnow())
        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url, url=f"https://discordapp.com/users/{ctx.author.id}")
        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon_url)
        await ctx.guild.system_channel.send(embed=embed)

    @commands.command(hidden=True)
    @commands.guild_only()
    @commands.is_owner()
    async def autoapprove(self, ctx):
        if not discord.utils.get(ctx.guild.roles, name="Approved"):
            await ctx.send("Create role named 'Approved' and try again.")
            return
        Text= "To gain access to the rest of this server, click on :white_check_mark: below\n\n"
        Text += "By doing so, you agree to abide by these rules."
        await ctx.message.delete()
        message = await ctx.send(embed=discord.Embed(title='Confirmation', description=Text, colour = 0xFF0000))
        await message.add_reaction('✅')
        self.messages[str(ctx.guild.id)] = message.id
        with open('assets/autoapprove_messages.json', 'w') as file:
            json.dump(self.messages, file, indent=2)

    @commands.command(hidden=True)
    @commands.guild_only()
    @commands.is_owner()
    async def embedrules(self, ctx):
        await ctx.message.delete()
        embed = discord.Embed(title=self.title, colour=discord.Colour.blurple())
        embed.add_field(name=self.rule_head, value='\n\n'.join(self.rules))
        embed.add_field(name=self.honour_head, value=self.honour)
        embed.add_field(name=self.privacy_head, value=self.privacy)
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.avatar_url, url=f"https://discordapp.com/users/{ctx.author.id}")
        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon_url)
        
        msg = await ctx.send(embed=embed)

    @commands.command(name='rules', aliases=['rule'], hidden=True)
    @commands.guild_only()
    @checks.is_mod()
    @checks.is_in_guilds(GUILD_ID)
    async def _rules(self, ctx, num=None):
        embed = discord.Embed(colour=discord.Colour.blurple())
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon_url)
        if num is None:
            embed.title = self.rule_head
            embed.description = self.rules
            return await ctx.send(embed=embed)
        for rule in self.rules:
            idx, _, text = rule.partition('. ')
            if idx.strip() == num:
                embed.title = f"Rule {idx}"
                embed.description = text
                return await ctx.send(embed=embed)
        await ctx.send('Invalid rule number.')

    @commands.command(name='privacypolicy', aliases=['privacy', 'privacy_policy'], hidden=True)
    @commands.guild_only()
    @checks.is_mod()
    @checks.is_in_guilds(GUILD_ID)
    async def _privacy(self, ctx):
        embed = discord.Embed(colour=discord.Colour.blurple())
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon_url)
        embed.title = self.privacy_head
        embed.description = self.privacy
        await ctx.send(embed=embed)

    @commands.command(name='honourcode', aliases=['honour', 'honour_code'], hidden=True)
    @commands.guild_only()
    @checks.is_mod()
    @checks.is_in_guilds(GUILD_ID)
    async def _honour(self, ctx):
        embed = discord.Embed(colour=discord.Colour.blurple())
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon_url)
        embed.title = self.honour_head
        embed.description = self.honour
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(PubQuiz(bot))
