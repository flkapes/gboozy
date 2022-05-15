import json
import math
import re
import traceback
from datetime import timedelta

import discord
import lavalink
from discord.ext import commands

from .log import Log

from .spotifyToYoutube import getSingleTrack, getTracks, getPlaylistTitle

logger = Log()

track_len = {}
debug = True


class LLVoiceClient(discord.VoiceClient):
    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        self.client = client
        self.channel = channel

        if not hasattr(self.client, "lavalink"):
            self.lavalink = self.client.lavalink
        else:
            self.client.lavalink = lavalink.Client(client.user.id)
            with open("config.json", "r") as read:
                server = json.load(read)['servers'][str(0)]
                try:
                    self.client.lavalink.add_node(
                        server["host"],
                        server["port"],
                        server["password"],
                        server["region"],
                        server["name"],
                    )
                    self.lavalink = self.client.lavalink
                except (
                    lavalink.NodeException,
                    lavalink.exceptions.Unauthorized,
                ) as ce:
                    if isinstance(ce, lavalink.NodeException):
                        logger.warning(
                            f"Node {server['host']}:{server['port']} is offline or refusing connections."
                        )
                    elif isinstance(ce, lavalink.exceptions.Unauthorized):
                        logger.warning(
                            f"Connections to node {server['host']}:{server['port']}"
                            f" are failing due to incorrect credentials. "
                        )

    async def on_voice_server_update(self, data):
        lavalink_data = {
            't': 'VOICE_SERVER_UPDATE',
            'd': data
        }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def on_voice_state_update(self, data):
        lavalink_data = {
            't': 'VOICE_STATE_UPDATE',
            'd': data
        }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def connect(self, *, timeout: float, reconnect: bool, self_deaf: bool = True, self_mute: bool = False):
        self.lavalink.player_manager.create(guild_id=self.channel.guild.id)
        await self.channel.guild.change_voice_state(channel=self.channel, self_mute=self_mute, self_deaf=self_deaf)

    async def disconnect(self, *, force: bool = False) -> None:
        player = self.lavalink.player_manager.get(self.channel.guild.id)
        if not force and not player.is_connected:
            return
        await self.channel.guild.change_voice_state(channel=None)
        player.channel_id = None
        self.cleanup()


class MusicNew(commands.Cog):
    def __init__(self, bot: discord.ext.commands.Bot):
        self.bot = bot
        self.musicQueue: list = []
        self.looping: bool = False
        self.playingMessage: discord.Message = None
        self.lastQueueCheck: discord.abc.Messageable = None
        if not hasattr(bot, "lavalink"):
            bot.lavalink = lavalink.Client(bot.user.id)

            with open("config.json", "r") as read:
                read = json.load(read)
                read = read["servers"]
                meow = 1 if debug else len(read)
                for i in range(meow):
                    server = read[str(i)]
                    try:
                        self._lavalinkInit(
                            bot,
                            server["host"],
                            server["port"],
                            server["password"],
                            server["region"],
                            server["name"],
                        )
                    except (
                        lavalink.NodeException,
                        lavalink.exceptions.Unauthorized,
                    ) as ce:
                        if isinstance(ce, lavalink.NodeException):
                            logger.warning(
                                f"Node {server['host']}:{server['port']} is offline or refusing connections."
                            )
                            continue
                        elif isinstance(ce, lavalink.exceptions.Unauthorized):
                            logger.warning(
                                f"Connections to node {server['host']}:{server['port']}"
                                f" are failing due to incorrect credentials. "
                            )

        lavalink.add_event_hook(self.onTrackStart)
        lavalink.add_event_hook(self.trackHook)
        lavalink.enable_debug_logging()
        lavalink.add_event_hook(self.onTrackEnd)
        lavalink.add_event_hook(self.onTrackException)

    async def updatePlayingMessage(self, ctx, change):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if self.playingMessage is not None:
            try:
                await self.playingMessage.delete()
                playingMessage = discord.Embed(
                    title="🎶 Now playing",
                    url=f"{player.current.uri}",
                    description=f"{player.current.title} is now playing on the bot!",
                    color=0x00FF11,
                )
                playingMessage.add_field(
                    name="Duration",
                    value=f"{str(timedelta(seconds=player.current.duration/1000))[2:]}",
                    inline=True,
                )
                playingMessage.add_field(
                    name="Shuffle",
                    value=f"**{'On' if player.shuffle else 'Off'}**"
                    if change == "shuffle"
                    else f"{'On' if player.shuffle else 'Off'}",
                    inline=True,
                )
                playingMessage.add_field(
                    name="Loop",
                    value=f"**{'On' if player.repeat else 'Off'}**"
                    if change == "loop"
                    else f"{'On' if player.repeat else 'Off'}",
                    inline=True,
                )
                self.playingMessage = await ctx.send(embed=playingMessage)
            except (discord.NotFound, AttributeError) as error:
                if isinstance(error, discord.NotFound):
                    logger.warning("playingMessage not found")

    @commands.command()
    async def join(self, ctx: commands.Context, *, channel: discord.VoiceChannel = ""):
        """Tells bot to join your voice channel"""

        channel = (
            channel
            if channel != ""
            else (
                ctx.author.voice.channel
                if ctx.author.voice is not None
                else "BadRequest"
            )
        )
        if ctx.voice_client is not None and channel != "BadRequest":
            return await ctx.voice_client.move_to(channel)
        elif channel == "BadRequest":
            logger.info(
                f"User {ctx.message.author} tried to use the join command without being in a voice channel"
            )
            await ctx.message.delete(delay=30)
            return await ctx.send(
                "Oops! You tried to use the join command without being connected to a voice channel."
            )
        await channel.connect()

    @discord.ext.commands.command(name="queue", aliases=["page", "q"])
    async def _queue(self, ctx: commands.Context, page: int = 1):
        """
        This command will display the queue. Add a number to see other pages.
        """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if player is not None:
            ipp = 10
            pages = math.ceil(len(player.queue) / ipp)
            logger.info(
                f"User {ctx.message.author} requested queue. "
                f"Queue length is {math.ceil(len(player.queue) / 10)} pages, "
                f"and the selected page is {page}"
            )
            if len(player.queue) == 0:
                logger.info(f"User {ctx.message.author} tried to query an empty queue!")
                return await ctx.send("Nothing in queue yet!")
            queueList = ""

            if page > pages:
                return await ctx.send(
                    "Invalid page number. The last page is #{}".format(pages)
                )

            start = (page - 1) * ipp
            end = start + ipp
            for index, track in enumerate(player.queue[start:end]):
                queueList += f"`{index + 1}.`**{track.title}** - "
                queueList += (
                    f"`{(str(timedelta(seconds=track_len[track.title] / 1000))[2:])}`\n"
                )
            embed = discord.Embed(
                colour=discord.Color.from_rgb(244, 66, 146),
                description=f"There are **{len(player.queue)} tracks** in queue:\n\n{queueList}",
            )
            if len(player.queue) > ipp:
                embed.set_footer(
                    text=f"Viewing page {page}/{pages}\n\nFor more pages type $page [page_number]"
                )
            else:
                embed.set_footer(text=f"Viewing page {page}/{pages}")
            logger.info("Querying song queue")
            if self.lastQueueCheck is not None:
                try:
                    await self.lastQueueCheck.delete()
                    await ctx.message.delete()
                    self.lastQueueCheck = await ctx.send(embed=embed)
                except discord.NotFound:
                    self.lastQueueCheck = await ctx.send(embed=embed)
            else:
                try:
                    self.lastQueueCheck = await ctx.send(embed=embed)
                    await ctx.message.delete()
                except discord.NotFound:
                    self.lastQueueCheck = await ctx.send(embed=embed)

        else:
            logger.info(
                f"User {ctx.message.author} has requested the queue, "
                f"but the bot is not playing anything and the queue does not exist."
            )
            await ctx.send(
                "The bot is not playing anything so you cannot check the queue."
            )

    @commands.command()
    async def loop(self, ctx: commands.Context):
        """
        Toggles looping for the current song.
        """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if player is not None:
            if player.repeat is False:
                player.repeat = not player.repeat
                # player.set_repeat(not player.repeat)
                # await ctx.send("**Loop has been enabled.**")
                logger.info(f"User {ctx.message.author} has toggled looping on.")
                await self.updatePlayingMessage(ctx, "loop")
            else:
                player.repeat = not player.repeat
                # player.set_repeat(not player.repeat)
                # await ctx.send("**Loop has been disabled.**")
                logger.info(f"User {ctx.message.author} has toggled looping off.")
                await self.updatePlayingMessage(ctx, "loop")
        else:
            logger.info(
                "User {} tried to loop/un-loop the player, but the player is not active.".format(
                    ctx.author.id
                )
            )
            await ctx.send(
                "You can't loop the player while the bot is not playing anything"
            )

    @discord.ext.commands.command(name="pause", aliases=["unpause", "resume"])
    async def _pause(self, ctx: commands.Context):
        """
        This command will pause or unpause the current song
        """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if player is not None:
            if player.paused:
                await player.set_pause(False)
                logger.info(
                    f"User {ctx.message.author} has resumed "
                    f"playback of track {player.current.title}"
                )
                await ctx.send("Resumed playback.")
            elif not player.paused:
                await player.set_pause(True)
                logger.info(
                    f"User {ctx.message.author} has paused playback of track {player.current.title}"
                )
                await ctx.send("Paused playback.")
        else:
            logger.info(
                "User {} tried to pause/resume the player, but the player is not active.".format(
                    ctx.message.author
                )
            )
            await ctx.send(
                "You can't pause or resume while the bot is not playing anything"
            )

    @commands.command()
    async def shuffle(self, ctx: commands.Context):
        """
        Will toggle shuffle on or off for the currently playing playlist
        """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if player is not None:
            if player.shuffle is True:
                player.set_shuffle(False)
                # await ctx.send("**Shuffle disabled**")
                await self.updatePlayingMessage(ctx, "shuffle")
                logger.info(f"User {ctx.message.author} has toggled shuffle off.")
            else:
                player.set_shuffle(True)
                await self.updatePlayingMessage(ctx, "shuffle")
                # await ctx.send(f"**Shuffle enabled for
                # {len(player.queue)} song(s)**")
                logger.info(f"User {ctx.message.author} has toggled shuffle on.")
        else:
            logger.info(
                "User {} tried to shuffle the player, but the player is not active.".format(
                    ctx.message.author
                )
            )
            await ctx.send("You can't shuffle while the bot is not playing")

    @commands.command()
    async def volume(self, ctx: commands.Context):
        player: lavalink.DefaultPlayer = self.bot.lavalink.player_manager.get(
            ctx.guild.id
        )
        if len(re.findall("@volume [0-9]+", ctx.message.content)) == 1:
            split = ctx.message.content.split(" ")
            try:
                if player.is_playing:
                    await player.set_volume(int(split[1]))
            except AttributeError:
                logger.warning(
                    f"User {ctx.message.author} tried to adjust the "
                    f"volume while the player does not exist / is not "
                    f"fully initialized"
                )
                logger.warning(f"Suppressing exception: {traceback.format_exc()}")
        elif len(re.findall("@volume", ctx.message.content)) == 1:
            await ctx.send(f"Current volume is set to {player.volume}")

    @commands.command()
    async def stats(self, ctx: commands.Context):
        guildID = ctx.guild.id
        player = self.bot.lavalink.player_manager.get(guildID)
        title = "The statistics returned by the current node: {}"
        a = False
        if player is None:
            player = self.bot.lavalink.node_manager.find_ideal_node()
            a = True
            title = "The bot is not playing anything. Here are the stats for the best available node: {}"
        try:
            embed = discord.Embed(
                title="Node Statistics",
                description=title.format(player.name if a else player.node.name),
            )
            embed.add_field(
                name="Players", value=f"{player.stats.players}", inline=True
            )
            embed.add_field(
                name="Playing Players",
                value=f"{player.stats.playing_players}",
                inline=True,
            )
            embed.add_field(
                name="Nulled Frames",
                value=f"{player.stats.frames_nulled} Frames",
                inline=True,
            )
            embed.add_field(
                name="Lavalink Load",
                value=f"{player.stats.lavalink_load * 100:.2f}%",
                inline=True,
            )
            embed.add_field(
                name="CPU Load",
                value=f"{player.stats.system_load * 100:.2f}%",
                inline=True,
            )
            uptime = lavalink.parse_time(player.stats.uptime)
            embed.add_field(
                name="Uptime",
                value=f"{int(uptime[0])} Days {int(uptime[1])} Hours {int(uptime[2])} Minutes",
                inline=True,
            )
            await ctx.send(embed=embed, delete_after=120)
        except (AttributeError, ValueError) as error:
            logger.info("No player")
            traceback.print_exc()

    @commands.command()
    async def skip(self, ctx: commands.Context):
        """
        Skips the current song. $skip <number> to skip x times!
        """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        logger.info(
            "User {} called the skip command on song: {}.".format(
                ctx.message.author, player.current.title
            )
        )
        skip = (
            -1
            if len(ctx.message.content.split(" ")) == 1
            else int(ctx.message.content.split(" ")[1])
        )
        if skip == -1:
            if player is not None:
                if len(player.queue) > 0 and player.is_playing:
                    if player.repeat:
                        logger.info(
                            "Loop was enabled, setting repeat to false then skipping."
                        )
                        player.set_repeat(False)
                    await player.skip()
                    logger.info(
                        "Song successfully skipped by user {}!.".format(
                            ctx.message.author
                        )
                    )
                else:
                    await self.stop(ctx)
                    logger.info("Song successfully skipped, queue empty.")
                    await ctx.send("Playback stopped. Queue empty!")
            else:
                await ctx.send(
                    "Nothing is playing and / or bot is not in discord channel."
                )
                logger.info("Bot is not in channel, so skip is ignored")
        else:
            if player is not None:
                if len(player.queue) > skip > 0:
                    if player.repeat:
                        player.set_repeat(False)
                    for i in range(skip - 1):
                        await player.skip()
                else:
                    logger.info(
                        f"Illegal skip value given. User {ctx.message.author} "
                        f"tried to skip {ctx.message.content.split(' ')[1]} times, "
                        f"but queue length is {len(player.queue)}"
                    )
                    await ctx.send(
                        "Illegal skip value given. Try again with a different value."
                    )

    @commands.command()
    async def stop(self, ctx: commands.Context):
        """Stops and disconnects the bot from voice"""
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        try:
            if player.is_playing:
                player.queue.clear()
                await player.stop()
                logger.info(
                    f"User {ctx.message.author} has stopped playback, clearing queue!"
                )
                await self.bot.get_channel(730621077138571358).send(
                    "Playback stopped!. Hope you enjoyed this session."
                )
                guildId = int(ctx.guild.id)
                # noinspection PyTypeChecker
                await self.connectTo(guildId, None)
        except AttributeError:
            logger.info("Player already stopped")
            await ctx.send("Playback already stopped!")

    @commands.command()
    async def play(self, ctx: commands.Context):
        """Plays a song or playlist"""
        await self.ensureVoice(ctx)
        # player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        musicQueue = []
        ytLink = False
        playedFirst = False
        if ctx.message.content.startswith("@play"):
            logger.info("$play command initialized by {}".format(ctx.message.author))
            link = ctx.message.content.split(" ")
            if link[1].startswith("https://open.spotify.com/playlist/"):
                logger.info(
                    "User {} has given a spotify playlist. Link {}. Running getSongs".format(
                        ctx.message.author, link[1]
                    )
                )
                musicQueue += getTracks(link[1])
            elif link[1].startswith("https://open.spotify.com/track/"):
                logger.info(
                    "User {} has given a spotify song. Link {}. Running getSingleTrack".format(
                        ctx.message.author, link[1]
                    )
                )
                search = getSingleTrack(link[1])
                musicQueue.append(search)
            elif (
                not link[1].startswith("https://")
                and not link[1].startswith("http://")
                and not link[1].startswith("www.")
            ):
                logger.info(
                    'User {} has given search query "{}"'.format(
                        ctx.message.author, " ".join(link[1:])
                    )
                )
                musicQueue.append(" ".join(link[1:]))
            else:
                logger.info(
                    "User {} has given a youtube link. Link {}.".format(
                        ctx.message.author, link[1]
                    )
                )
                ytLink = True
                musicQueue.append(link[1])
            await self.addSongsToQueue(playedFirst, musicQueue, ctx, ytLink)

    async def addSongsToQueue(
        self,
        playedFirst: bool,
        musicQueue: list,
        ctx: commands.Context,
        ytLink: bool = False,
    ) -> tuple:
        player: lavalink.DefaultPlayer = self.bot.lavalink.player_manager.get(
            ctx.guild.id
        )
        link = ctx.message.content.split(" ")
        for i, track in enumerate(musicQueue):
            query = f"ytsearch:{track}" if ytLink == False else f"{track}"
            try:
                results = await player.node.get_tracks(query)
            except lavalink.NodeException:
                raise (lavalink.NodeException("Node is broken. Likely IPv6."))
            if len(results) == 0:
                print(len(results))
                logger.info(
                    f"User {ctx.message.author} requested track {track}, but no results were found"
                )
                await ctx.send(
                    "Sorry, there were no results found for that track! Please try again with the addition "
                    "of the musician's name as well as any featured artists on the track"
                )
                return ()
            elif results["loadType"] == "LOAD_FAILED":
                logger.warning("Loading link failed. Please try again")
                await ctx.send("Sorry, there's been an error! Please try again later.")
                break
            resultInfo = results["tracks"][0]["info"]
            player.add(requester=ctx.author.id, track=results["tracks"][0])
            track_len[resultInfo["title"]] = resultInfo["length"]
            if i == 0 and not player.is_playing:
                await player.play()
                playedFirst = True
                logger.info(
                    "Playing song {}, queued by user {}".format(
                        resultInfo["title"],
                        await ctx.bot.fetch_user(player.current.requester),
                    )
                )
                if self.playingMessage is None:
                    print("PlayingMessage set to not none")
                    """self.playingMessage = await ctx.send(
                        f'**Now playing: {resultInfo["title"]}**"'
                        + f' - `{str(timedelta(seconds=resultInfo["length"] / 1000))[2:]}`'
                        + f'\n{resultInfo["uri"]}'
                    )"""
                    playingMessage = discord.Embed(
                        title="🎶 Now playing",
                        url=f"{player.current.uri}",
                        description=f"{player.current.title} is now playing on the bot!",
                        color=0x00FF11,
                    )
                    playingMessage.add_field(
                        name="Duration",
                        value=f"{str(timedelta(seconds=resultInfo['length'] / 1000))[2:]}",
                        inline=True,
                    )
                    playingMessage.add_field(
                        name="Shuffle",
                        value=f"{'On' if player.shuffle else 'Off'}",
                        inline=True,
                    )
                    playingMessage.add_field(
                        name="Loop",
                        value=f"{'On' if player.repeat else 'Off'}",
                        inline=True,
                    )
                    self.playingMessage = await ctx.send(embed=playingMessage)
                else:
                    pass
        if not player.is_playing and playedFirst:
            await player.play()
            await ctx.message.delete()
            logger.info("Empty queue, so play song selected by user")

        elif len(player.queue) >= 1 and player.is_playing:
            deleteAfter = (player.current.duration - player.position) / 1000
            if link[1].startswith("https://open.spotify.com/playlist/"):
                logger.info(
                    "Queue not empty, and spotify playlist selected. "
                    + "Adding songs from playlist to back of existing queue."
                )
                await ctx.send(
                    f"Spotify Playlist "
                    f"**{getPlaylistTitle(link[1])}** "
                    f"has been added to the queue!",
                    delete_after=deleteAfter,
                )
            elif link[1].startswith("https://open.spotify.com/track/"):
                logger.info(
                    "Queue not empty, and spotify song selected. Adding song to back of queue"
                )
                await ctx.send(
                    f"**{player.queue[-1].title}** has been added to the queue!",
                    delete_after=deleteAfter,
                )
            else:
                logger.info(
                    "Queue not empty, and youtube song selected. Adding song to back of queue."
                )
                await ctx.send(
                    f"**{player.queue[-1].title}** has been added to the queue!",
                    delete_after=deleteAfter,
                )
            await ctx.message.delete()

    async def _tryAgain(
        self,
        track: lavalink.AudioTrack,
        player: lavalink.DefaultPlayer,
        attempt: int = 0,
    ):
        if attempt < 3:
            await player.play(track=track)
            return await self._tryAgain(track, player, attempt + 1)
        else:
            logger.warning("Track cannot be played. Maybe restart server?")

    async def ensureVoice(self, ctx: commands.Context):
        """This check ensures that the bot and command author are in the same voice channel.
        :type ctx: commands.Context
        """
        player = self.bot.lavalink.player_manager.create(
            ctx.guild.id, endpoint=str(ctx.guild.region)
        )

        # Create returns a player if one exists, otherwise creates.
        # This line is important because it ensures that a player always exists
        # for a guild.

        # Most people might consider this a waste of resources for guilds that
        # aren't playing, but this is the easiest and simplest way of ensuring
        # players are created.

        # These are commands that require the bot to join a voicechannel (i.e. initiating playback).
        # Commands such as volume/skip etc. don't require the bot to be in a
        # voicechannel so don't need listing here.
        shouldConnect = ctx.command.name in ("play", "join")

        if not ctx.author.voice or not ctx.author.voice.channel:
            # Our cog_command_error handler catches this and sends it to the voicechannel.
            # Exceptions allow us to "short-circuit" command invocation via checks so the
            # execution state of the command goes no further.
            raise commands.CommandInvokeError(
                "You'll have to join a voice channel before I can do that."
            )

        if not player.is_connected:
            if not shouldConnect:
                raise commands.CommandInvokeError("Not connected.")

            permissions = ctx.author.voice.channel.permissions_for(ctx.me)

            if (
                not permissions.connect or not permissions.speak
            ):  # Check user limit too?
                raise commands.CommandInvokeError(
                    "I need the `CONNECT` and `SPEAK` permissions."
                )

            player.store("channel", ctx.channel.id)
            await self.connectTo(ctx.guild.id, str(ctx.author.voice.channel.id))
        else:
            if int(player.channel_id) != ctx.author.voice.channel.id:
                raise commands.CommandInvokeError("You need to be in my voicechannel.")

    async def onTrackStart(self, event: lavalink.TrackStartEvent):
        if isinstance(event, lavalink.events.TrackStartEvent):
            if self.playingMessage is not None and not isinstance(
                self.playingMessage, discord.DeletedReferencedMessage
            ):
                try:
                    # print(self.playingMessage)
                    await self.playingMessage.delete()
                except discord.NotFound:
                    meow = self.bot.get_channel(730621077138571358)
                    meow2 = await meow.history(limit=1).flatten()
                    # print(meow2[0].content)
            """self.playingMessage = await self.bot.get_channel(730621077138571358).send(
                f"**Now playing: {event.player.current.title}** -"
                + f" `{str(timedelta(seconds=event.player.current.duration / 1000))[2:]}`"
                + f"\n{event.player.current.uri}"
            )"""
            player = event.player
            playingMessage = discord.Embed(
                title="🎶 Now playing",
                url=f"{event.track.uri}",
                description=f"{player.current.title} is now playing on the bot!",
                color=0x00FF11,
            )
            playingMessage.add_field(
                name="Duration",
                value=f"{str(timedelta(seconds=track_len[event.track.title] / 1000))[2:]}",
                inline=True,
            )
            playingMessage.add_field(
                name="Shuffle",
                value=f"{'On' if player.shuffle else 'Off'}",
                inline=True,
            )
            playingMessage.add_field(
                name="Loop", value=f"{'On' if player.repeat else 'Off'}", inline=True
            )
            self.playingMessage = await self.bot.get_channel(730621077138571358).send(
                embed=playingMessage
            )

            logger.info(f"Playing next song. {event.player.current.title}")

    async def onTrackEnd(self, event: lavalink.TrackEndEvent):
        if isinstance(event, lavalink.events.TrackEndEvent):
            if (
                event.reason == "FINISHED"
                and event.player.current is None
                and len(event.player.queue) == 0
            ):
                logger.info("Song finished, and queue empty")
                try:
                    await self.playingMessage.delete()
                except discord.NotFound:
                    pass
                await self.bot.get_channel(730621077138571358).send(
                    "Queue empty. Hope you enjoyed!"
                )
                self.playingMessage = None
            elif (
                event.reason == "STOPPED"
                and event.player.is_playing is False
                and len(event.player.queue) == 0
            ):
                try:
                    await self.playingMessage.delete()
                except discord.NotFound:
                    pass
                logger.info("Song skipped by user. Queue empty")
                self.playingMessage = None
            elif event.reason == "LOAD_FAILED":
                await self.bot.get_channel(730621077138571358).send(
                    f"Error encountered playing track! Apologies.", delete_after=15
                )

    async def onTrackException(self, event: lavalink.TrackExceptionEvent):
        if isinstance(event, lavalink.TrackExceptionEvent):
            # await event.player.add(self.bot.owner_id, event.track,
            # index=0)
            await self._tryAgain(event.track, event.player)
            # await event.player.play(event.track)

    async def trackHook(self, event: lavalink.Event):
        if isinstance(event, lavalink.events.QueueEndEvent):
            # When this track_hook receives a "QueueEndEvent" from lavalink.py
            # it indicates that there are no tracks left in the player's queue.
            # To save on resources, we can tell the bot to disconnect from the
            # voicechannel.
            guildId = int(event.player.guild_id)
            # noinspection PyTypeChecker
            await self.connectTo(guildId, None)
            try:
                await self.playingMessage.delete()
            except discord.NotFound:
                pass

    # noinspection PyProtectedMember
    async def connectTo(self, guildId: int, channelId: str):
        """Connects to the given voicechannel ID. A channel_id of `None` means disconnect."""
        webSocket: discord.client.DiscordWebSocket = (
            self.bot._connection._get_websocket(guildId)
        )
        await webSocket.voice_state(str(guildId), channelId)


def setup(bot):
    bot.add_cog(MusicNew(bot))
