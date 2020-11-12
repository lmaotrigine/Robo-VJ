import asyncio
import datetime
import enum
import random
import typing
import re
import discord
import wavelink
from discord.ext import commands
from .utils.context import Context

URL_REGEX = re.compile(r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))")

def to_emoji(c):
    base = 0x1F1E6
    return chr(base + c)

class MusicBaseException(commands.CommandError):
    pass

class AlreadyConnectedToChannel(MusicBaseException):
    pass

class NoVoiceChannel(MusicBaseException):
    pass

class QueueIsEmpty(MusicBaseException):
    pass

class NoTracksFound(MusicBaseException):
    pass

class PlayerIsAlreadyPaused(MusicBaseException):
    pass

class NoMoreTracks(MusicBaseException):
    pass

class NoPreviousTracks(MusicBaseException):
    pass

class RepeatMode(enum.Enum):
    NONE = 0
    SONG = 1
    ALL = 2

class Queue:
    def __init__(self):
        self._queue = []
        self.position = 0
        self.repeat_mode = RepeatMode.NONE

    @property
    def is_empty(self):
        return not self._queue
    
    @property
    def current_track(self):
        if not self._queue:
            raise QueueIsEmpty('No more tracks queued.')
        if self.position < len(self._queue):
            return self._queue[self.position]
    
    @property
    def upcoming(self):
        if not self._queue:
            raise QueueIsEmpty('This is the final track in queue.')
        return self._queue[self.position + 1:]

    @property
    def history(self):
        if not self._queue:
            raise QueueIsEmpty('Queue is empty.')
        return self._queue[:self.position]

    @property
    def length(self):
        return len(self._queue)

    def __len__(self):
        return len(self._queue)

    def add(self, *args):
        self._queue.extend(args)
    
    def get_next_track(self):
        if not self._queue:
            raise QueueIsEmpty('No tracks queued.')

        self.position += 1
        if self.position < 0:
            return None
        elif self.position >= len(self._queue):
            if self.repeat_mode == RepeatMode.ALL:
                self.position = 0
            else:
                return None
        
        return self._queue[self.position]

    def shuffle(self):
        if not self._queue:
            raise QueueIsEmpty('The queue is currently empty.')
        
        upcoming = self.upcoming
        random.shuffle(upcoming)
        self._queue = self._queue[:self.position + 1]
        self._queue.extend(upcoming)

    def set_repeat_mode(self, mode):
        self.repeat_mode = mode

    def empty(self):
        self._queue.clear()
        self.position = 0
        self.repeat_mode = RepeatMode.NONE

class Player(wavelink.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = Queue()

    async def connect(self, ctx, channel=None):
        if self.is_connected:
            raise AlreadyConnectedToChannel('Already connected to a channel in this guild.')

        if (channel := getattr(ctx.author.voice, 'channel', channel)) is None:
            raise NoVoiceChannel('No valid voice channel provided.')

        await super().connect(channel_id=channel.id)
        return channel

    async def teardown(self):
        try:
            await self.destroy()
        except KeyError:
            pass

    async def add_tracks(self, ctx, tracks):
        if not tracks:
            raise NoTracksFound('No tracks found matching your query.')
        
        if isinstance(tracks, wavelink.TrackPlaylist):
            self.queue.add(*tracks.tracks)
        
        elif len(tracks) == 1:
            self.queue.add(tracks[0])
            await ctx.send(f'Added {tracks[0].title} to the queue.')
        
        else:
            if (track := await self.choose_track(ctx, tracks)) is not None:
                self.queue.add(track)
                await ctx.send(f'Added {track.title} to the queue.')

        if not self.is_playing and not self.queue.is_empty:
            await self.start_playback()

    async def choose_track(self, ctx, tracks):
        def _check(r, u):
            return r.emoji in opts and u == ctx.author and r.message.id == msg.id

        embed = discord.Embed(title='Choose a song', colour=ctx.author.colour, timestamp=datetime.datetime.utcnow())
        embed.set_author(name='Query Results')
        embed.set_footer(text=f'Requested by {ctx.author.display_name}', icon_url=ctx.author.avatar_url)
        embed.description = '\n'.join(f'**{to_emoji(i)}.** {t.title} ({t.length // 60000}:{str(t.length % 60).zfill(2)})' for i, t in enumerate(tracks[:5]))
        msg = await ctx.send(embed=embed)
        opts = {to_emoji(i): i for i in range(min(len(tracks), 5))}
        for emoji in opts.keys():
            await msg.add_reaction(emoji)
        
        try:
            reaction, _ = await self.bot.wait_for('reaction_add', check=_check, timeout=60.0)
        except asyncio.TimeoutError:
            await msg.delete()
        else:
            return tracks[opts[reaction.emoji]]

    async def start_playback(self):
        await self.play(self.queue.current_track)

    async def advance(self):
        try:
            if (track := self.queue.get_next_track()) is not None:
                await self.play(track)
        except QueueIsEmpty:
            pass

    async def repeat_track(self):
        await self.play(self.queue.current_track)

class Music(commands.Cog, wavelink.WavelinkMixin):
    """Music Playback (beta)
    
    No fancy embeds, etc. No position viewing.
    Lot of TODOs, but none will be implemented anytime soon.
    
    Currently, the player is functional, as long as the singular node isn't overloaded.
    """

    def __init__(self, bot):
        self.bot = bot
        self.wavelink = wavelink.Client(bot=bot)
        self.bot.loop.create_task(self.start_nodes())

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.bot and after.channel is None:

            if not [m for m in before.channel.members if not m.bot]:
                await self.get_player(member.guild).teardown()

    async def cog_command_error(self, ctx, error):
        if isinstance(error, MusicBaseException):
            await ctx.send(error)

    @wavelink.WavelinkMixin.listener()
    async def on_node_ready(self, node):
        print(f'Wavlelink node `{node.identifier}` is ready.')

    @wavelink.WavelinkMixin.listener('on_track_stuck')
    @wavelink.WavelinkMixin.listener('on_track_end')
    @wavelink.WavelinkMixin.listener('on_track_exception')
    async def on_player_stop(self, node, payload):
        if payload.player.queue.repeat_mode == RepeatMode.SONG:
            await payload.player.repeat_track()
        else:
            await payload.player.advance()

    async def cog_check(self, ctx):
        return ctx.guild is not None

    async def start_nodes(self):
        await self.bot.wait_until_ready()
        nodes = {
            'MAIN': {
                'host': self.bot.config.lavalink_ip,
                'port': 2333,
                'rest_uri': f'http://{self.bot.config.lavalink_ip}:2333',
                'password': 'youshallnotpass',
                'identifier': 'MAIN',
                'region': 'europe',
            }
        }

        for node in nodes.values():
            await self.wavelink.initiate_node(**node)
    
    def get_player(self, obj):
        if isinstance(obj, commands.Context):
            return self.wavelink.get_player(obj.guild.id, cls=Player, context=obj)
        elif isinstance(obj, discord.Guild):
            return self.wavelink.get_player(obj.id, cls=Player)
        
    @commands.command(name='connect', aliases=['c', 'j'])
    async def _connect(self, ctx, *, channel: discord.VoiceChannel=None):
        """Connects to a voice channel. If none is provided, try to connect to the voice channel you are currently in."""
        player = self.get_player(ctx)
        channel = await player.connect(ctx, channel)
        await ctx.send(f'Connected to `{channel.name}`')
    
    @commands.command(name='disconnect', aliases=['leave', 'dc'])
    async def _disconnect(self, ctx):
        """Disconnect from a voice channel."""
        player = self.get_player(ctx)
        await player.teardown()
        await ctx.send('Disconnect.')

    @commands.command(name='play')
    async def _play(self, ctx, *, query: str=None):
        """Play a song in the current channel, or add it to queue.
        
        If no query is given, tryies to resume previously paused playback.
        """
        player = self.get_player(ctx)
        if not player.is_connected:
            await player.connect(ctx)

        if query is None:
            if player.queue.is_empty:
                raise QueueIsEmpty('No songs in queue.')
            await player.set_pause(False)
        else:
            query = query.strip('<>')

            if not URL_REGEX.match(query):
                query = f'ytsearch:{query}'

            await player.add_tracks(ctx, await self.wavelink.get_tracks(query))

    @commands.command(name='pause')
    async def _pause(self, ctx):
        """Pauses playback in the current channel."""
        player = self.get_player(ctx)
        if player.is_paused:
            raise PlayerIsAlreadyPaused('Player is already paused.')

        await player.set_pause(True)
        await ctx.send('Playback paused.')

    @commands.command(name='stop')
    async def _stop(self, ctx):
        """Stops playback completely and also clears the queue."""
        player = self.get_player(ctx)
        player.queue.empty()
        await player.stop()
        await ctx.send('Stopped playback and cleared queue.')

    @commands.command(name='next', aliases=['skip'])
    async def _next(self, ctx):
        """Skips current track in the queue."""
        player = self.get_player(ctx)

        if not player.queue.upcoming:
            raise NoMoreTracks('No more tracks in queue.')
        await player.stop()
        await ctx.send('Skipping current track.')

    @commands.command(name='previous')
    async def _previous(self, ctx):
        """Plays the previous track in queue."""
        player = self.get_player(ctx)

        if not player.queue.history:
            raise NoPreviousTracks('No previous tracks in queue.')
        player.queue.position -= 2  # hacky
        await player.stop()
        await ctx.send('Playing previous track.')
    
    @commands.command(name='shuffle')
    async def _shuffle(self, ctx):
        """Shuffles the queue. Original order not preserved."""
        player = self.get_player(ctx)
        player.queue.shuffle()
        await ctx.send('Queue shuffled.')

    @commands.group(name='repeat', aliases=['loop'], invoke_without_command=True, ignore_extra=False)
    async def _repeat(self, ctx):
        """Set repeat mode for the current queue."""
        if ctx.invoked_subcommand is None:
            player = self.get_player(ctx)
            mode = ['none', 'song', 'all'][player.queue.repeat_mode.value]
            await ctx.send(f'Current repeat mode is `{mode}`')

    @_repeat.command(name='song', aliases=['current', 'one', 'single', '1'])
    async def repeat_song(self, ctx):
        """Repeat current song."""
        player = self.get_player(ctx)
        player.queue.set_repeat_mode(RepeatMode.SONG)
        await ctx.send('Repeat mode set to `song`')

    @_repeat.command(name='all', aliases=['list', 'queue'])
    async def repeat_all(self, ctx):
        """Repeat entire queue."""
        player = self.get_player(ctx)
        player.queue.set_repeat_mode(RepeatMode.ALL)
        await ctx.send('Repeat mode set to `list`.')

    @_repeat.command(name='none', aliases=['off'])
    async def repeat_none(self, ctx):
        """Turn off repeat."""
        player = self.get_player(ctx)
        player.queue.set_repeat_mode(RepeatMode.NONE)
        await ctx.send('Repeat mode has been set to `none`.')

    @_repeat.error
    async def repeat_error(self, ctx, error):
        if isinstance(error, commands.TooManyArguments):
            await ctx.send_help(ctx.command)

    @commands.command(name='queue')
    async def _queue(self, ctx, *, show: int=10):
        """Shows the current queue."""
        player = self.get_player(ctx)
        if player.queue.is_empty:
            raise QueueIsEmpty('No tracks queued.')

        embed = discord.Embed(title='Queue', colour=ctx.author.colour, timestamp=datetime.datetime.utcnow())
        embed.set_author(name='Query Results')
        embed.description = f'Showing up to next {show:,} tracks'
        embed.set_footer(text=f'Requested by {ctx.author.display_name}', icon_url=ctx.author.avatar_url)
        embed.add_field(name='Currently Playing', value=getattr(player.queue.current_track, 'title', 'No tracks currently playing.'), inline=False)
        if player.queue.upcoming:
            embed.add_field(name='Upcoming tracks', value='\n'.join(t.title for t in player.queue.upcoming[:show]))
        await ctx.send(embed=embed)

    @commands.command(name='nowplaying', aliases=['np', 'now_playing'])
    async def _nowplaying(self, ctx):
        """Shows currently playing track."""
        player = self.get_player(ctx)
        if player.queue.is_empty:
            raise QueueIsEmpty('Nothing playing right now.')
        embed = discord.Embed(title='Now Playing', colour=ctx.author.colour, timestamp=datetime.datetime.utcnow())
        embed.set_author(name='Query Results')
        embed.set_footer(text=f'Requested by {ctx.author.display_name}', icon_url=ctx.author.avatar_url)
        embed.add_field(name='Currently Playing', value=player.queue.current_track.title, inline=False)
        await ctx.send(embed=embed)
    
def setup(bot):
    bot.add_cog(Music(bot))
