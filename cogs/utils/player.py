import asyncio
import async_timeout
import copy
import datetime
import discord
import itertools
import wavelink
from discord.ext import buttons, commands

class PlayerSession(buttons.Session):
    def __init__(self):
        super().__init__(timeout=86400)
        self.ctx = None

    def check(self, payload):
        def pred(ctx: commands.Context):
            player = ctx.bot.get_cog('Music').get_player(ctx=ctx)
            vc_id = player.channel_id

            if not self.page:
                return False
            if str(payload.emoji) not in self.buttons:
                return False
            if payload.user_id == ctx.bot.user.id or payload.message_id != self.page.id:
                return False
            if ctx.guild.get_member(payload.user_id) not in ctx.bot.get_channel(int(vc_id)).members:
                return False
            return True
        return pred

    def get_ctx(self, old: commands.Context, member: discord.Member):
        new = copy.copy(old)
        new.author = member
        self.ctx = new
        return new

    @buttons.button(emoji='\u23EF', position=0, try_remove=False)
    async def pause(self, ctx, member):
        new = self.get_ctx(ctx, member)
        command = ctx.bot.get_command('pause')
        new.command = command
        await new.bot.invoke(new)

    @buttons.inverse_button(emoji='\u23EF', position=0, try_remove=False)
    async def resume(self, ctx, member):
        new = self.get_ctx(ctx, member)
        command = ctx.bot.get_command('resume')
        new.command = command
        await new.bot.invoke(new)

    @buttons.button(emoji='\u23EE', position=1)
    async def back(self, ctx, member):
        new = self.get_ctx(ctx, member)
        command = ctx.bot.get_command('back')
        new.command = command
        try:
            await new.bot.invoke(new)
        except Exception as e:
            await new.send(e)

    @buttons.button(emoji='\u23F9', position=2)
    async def stop(self, ctx, member):
        new = self.get_ctx(ctx, member)
        command = ctx.bot.get_command('stop')
        new.command = command
        await new.bot.invoke(new)

    @buttons.button(emoji='\u23ED', position=3)
    async def skip(self, ctx, member):
        new = self.get_ctx(ctx, member)
        command = ctx.bot.get_command('skip')
        new.command = command
        await new.bot.invoke(new)
    
    @buttons.button(emoji='🔀', position=4)  # Invisible emoji...
    async def shuffle(self, ctx, member):
        new = self.get_ctx(ctx, member)
        command = ctx.bot.get_command('shuffle')
        new.command = command
        await new.bot.invoke(new)

    @buttons.button(emoji='🔁', position=5)  # Invisible emoji...
    async def repeat(self, ctx, member):
        new = self.get_ctx(ctx, member)
        command = ctx.bot.get_command('repeat')
        new.command = command
        await new.bot.invoke(new)

    @buttons.button(emoji='➕', position=6)
    async def vol_up(self, ctx, member):
        new = self.get_ctx(ctx, member)
        command = ctx.bot.get_command('vol_up')
        new.command = command
        await new.bot.invoke(new)

    @buttons.button(emoji='➖', position=7)
    async def vol_down(self, ctx, member):
        new = self.get_ctx(ctx, member)
        command = ctx.bot.get_command('vol_down')
        new.command = command
        await new.bot.invoke(new)

    @buttons.button(emoji='🇶', position=8)  # Invisible emoji...
    async def queue(self, ctx, member):
        new = self.get_ctx(ctx, member)
        command = ctx.bot.get_command('queue')
        new.command = command
        await new.bot.invoke(new)

class Track(wavelink.Track):
    __slots__ = ('ctx', 'requester', 'channel', 'message', 'repeats')

    def __init__(self, id_, info, *, ctx=None):
        super(Track, self).__init__(id_, info)

        self.ctx: commands.Context = ctx
        self.requester = ctx.author
        self.channel = ctx.channel
        self.message = ctx.message

        self.repeats = 0
        self.dead = False

    @property
    def is_dead(self):
        return self.dead

class SpotifyTrack:
    __slots__ = ('name', 'title' 'artists', 'ctx', 'client')
    
    def __init__(self, name: str, artists, *, ctx: commands.Context, client: wavelink.Client):
        self.name = name
        self.artists = artists
        self.ctx = ctx
        self.client = client
    
    @property
    def title(self):
        return self.name
        
    async def get_wavelink_track(self):
        tracks = await self.client.get_tracks(f'ytsearch:{" ".join(a.name for a in self.artists)} {self.name}')
        if not tracks:
            return None
        track = tracks[0]
        return Track(track.id, track.info, ctx=self.ctx)
    
class Player(wavelink.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.session = PlayerSession()
        
        self.queue = []
        self.index = 0
        self.waiting = False
        self.updating = False
        
        self.dj = None
        
        self.pause_votes = set()
        self.resume_votes = set()
        self.skip_votes = set()
        self.shuffle_votes = set()
        self.repeat_votes = set()
        self.back_votes = set()
        
        self._current = None
        self.current = None

    async def _play_next(self):
        self.pause_votes.clear()
        self.resume_votes.clear()
        self.skip_votes.clear()
        self.shuffle_votes.clear()
        self.repeat_votes.clear()
        self.back_votes.clear()

        if self.waiting:
            return
        
        try:
            with async_timeout.timeout(300.0):
                self.waiting = True
                while True:
                    try:
                        track = self.queue[self.index]
                        if isinstance(track, Track):
                            break
                        _track = await track.get_wavelink_track()
                        if _track is not None:
                            track = _track
                            break
                        else:
                            self.index += 1
                    except IndexError:
                        await asyncio.sleep(1)
                    
        except asyncio.TimeoutError:
            return await self.teardown()
        
        self.waiting = False
        self._current = track
        await self.play(track)
        await asyncio.sleep(1)
        await self.invoke_session()

    async def invoke_session(self):
        track = self.current
        if not track:
            return
        
        if isinstance(track, SpotifyTrack):
            track = await track.get_wavelink_track()
        
        if self.updating:
            return
        
        self.updating = True

        embed = discord.Embed(title='Music Controller', colour=0xEBB145)

        if self.paused:
            embed.description = f'<:paused:776665714512625674>Paused:\n**`{track.title}`**\n\n'
        else:
            embed.description = f'<a:eq:776665781031010304>Now playing:\n**`{track.title}`**\n\n'
        
        embed.set_thumbnail(url=track.thumb)
        
        if track.is_stream:
            embed.add_field(name='Duration', value='🔴`Streaming`')
        else:
            embed.add_field(name='Duration', value=str(datetime.timedelta(milliseconds=int(track.length))))

        embed.add_field(name='Video URL', value=f'[Click Here!]({track.uri})')
        embed.add_field(name='Requested By', value=track.requester.mention)
        embed.add_field(name='DJ', value=self.dj.mention)
        embed.add_field(name='Queue Length', value=str(len(self.queue[self.index + 1:]) + self._current.repeats))
        embed.add_field(name='Volume', value=f'**`{self.volume}%`**')

        if (len(self.queue) + self._current.repeats) > self.index + 1:
            if self._current.repeats:
                data = f'**-** ({self._current.repeats})x' \
                    f' `{self._current.title[:45]}{"..." if len(self._current.title) > 45 else ""}`\n{"-" * 10}\n'
            else:
                data = ''

            data = data + '\n'.join(f'**-** `{t.title[:45]}{"..." if len(t.title) > 45 else ""}`\n{"-" * 10}'
                                     for t in itertools.islice([e for e in self.queue[self.index + 1:] if not e.is_dead], 0, 3, None))
            
            embed.add_field(name='Coming Up:', value=data, inline=False)

        if not await self.is_current_fresh(track.channel) and self.session.page:
            try:
                await self.destroy_controller()
            except discord.NotFound:
                pass
        
            await self.session.start(ctx=track.ctx, page=await track.ctx.send(embed=embed))
    
        elif not self.session.page:
            await self.session.start(ctx=track.ctx, page=await track.ctx.send(embed=embed))
        
        else:
            await self.session.page.edit(embed=embed, content=None)

        self.updating = False

    async def is_current_fresh(self, chan: discord.TextChannel):
        """Check whether our controller is fresh in message history."""
        try:
            async for m in chan.history(limit=8):
                if m.id == self.session.page.id:
                    return True
        except (discord.HTTPException, AttributeError):
            return False
        return False

    async def destroy_controller(self):
        await self.session.teardown()
        self.session.page = None

    async def teardown(self):
        await self.stop()
        await self.disconnect()
        await self.destroy_controller()

        del self.node.players[self.guild_id]

    def is_playing(self):
        return self.is_connected and self.current is not None

