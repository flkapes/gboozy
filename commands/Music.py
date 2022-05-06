import asyncio
import queue
from collections import deque
import discord
import youtube_dl
from discord.ext import commands
from datetime import timedelta

import client.gboozy_client
from .spotifyToYoutube import getSongs, getSingleTrack

import logging

logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(
    filename='discord.log',
    encoding='utf-8',
    mode='w')
handler.setFormatter(logging.Formatter(
    '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    # bind to ipv4 since ipv6 addresses cause issues sometimes
    'source_address': '0.0.0.0',
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class Music(commands.Cog, name="MusicModule"):
    def __init__(self, bot):
        self.bot: discord.ext.commands.Bot = bot
        self.musicQueue = deque()
        self.loop = False
        self.lastLoopedSong = None
        self.playingMessage: discord.Message

    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    @commands.command()
    async def playNext(self, ctx: discord.ext.commands.Context, *, url=""):
        info = ""
        if self.loop:
            vc = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
            player = await Music.from_url(self, ctx=ctx, url=self.lastLoopedSong, loop=None, stream=True)
            self.musicQueue.appendleft(self.lastLoopedSong)
            vc.play(
                player,
                after=lambda e: asyncio.run(
                    self.playNext(
                        ctx)))
            logger.info("Song looped")
        elif len(self.musicQueue) > 1:
            meow = self.musicQueue.popleft()
            vc = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
            player = await Music.from_url(self, ctx=ctx, url=meow, loop=None, stream=True)
            logger.info("Next song playing - 1.")
            vc.pause()
            await asyncio.sleep(0.5)
            vc.resume()
            info = ytdl.extract_info(meow, download=False)
            #playingMessage = await Music.updateMessage(self, ctx, meow, self.playingMessage)
            #self.playingMessage = playingMessage
            while vc.is_playing():
                await self.stop()
            vc.play(player, after=lambda e: asyncio.run(self.playNext(ctx)))
        elif len(self.musicQueue) == 1:
            meow = self.musicQueue.popleft()
            vc = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
            player = await Music.from_url(self, ctx=ctx, url=meow, loop=None, stream=True)

            logger.info("Next song playing - 2.")
            """vc.pause()
            await asyncio.sleep(0.5)
            vc.resume()"""
            info = ytdl.extract_info(meow, download=False)
            #playingMessage = await Music.updateMessage(self, ctx, meow, self.playingMessage)
            #self.playingMessage = playingMessage

            while vc.is_playing():
                ctx.voice_client.stop()
            vc.play(player, after=lambda e: print("DONE"))

        else:
            print("Done")
        ytdl.cache.remove()

    async def from_url(self, ctx, url, *, loop=None, stream=False):
        logger.info("YTDL Cache cleared.")
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if data is None:
            logger.warning("Error downloading")
        else:
            logger.info("Successfully retrieved song information from youtube")

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        logger.info("Video URL extracted from data")

        logTemp = "FFmpegPCMAudio object for song / video titled {} created and returned.".format(
            data['title'])
        logger.info(logTemp)
        return discord.FFmpegPCMAudio(
            executable="C:\\ffmpeg\\bin\\ffmpeg.exe",
            source=filename,
            options=ffmpeg_options)

    @commands.command()
    async def stream(self, ctx: discord.ext.commands.Context, *, url):
        """Streams from a url (same as yt, but doesn't predownload)"""

        logger.info(
            "Discord bot typing toggled on while code to convert link and play the song executes")
        async with ctx.typing():
            player = await Music.from_url(self, ctx=ctx, url=url, loop=None, stream=True)
            ctx.voice_client.play(
                player, after=lambda e: asyncio.run(
                    self.playNext(ctx)))
            self.lastLoopedSong = self.musicQueue.popleft()
            logger.info("Popped head element from the queue and played it.")
        info = ytdl.extract_info(url=url, download=False)
        meow = "Song {} is being played.".format(info['title'])
        logger.info(meow)
        playingMessage = await ctx.send(f'**Now playing: {info["title"]}** - `{str(timedelta(seconds=info["duration"]))[2:]}`\n{url}', delete_after=info["duration"])
        self.playingMessage = playingMessage

    @commands.command()
    async def queue(self, ctx: discord.ext.commands.Context):
        await ctx.send(f'**There are {len(self.musicQueue)} songs in your queue:**')
        logging.info("Querying song queue")
        for i, num in enumerate(self.musicQueue):
            if i >= 5:
                break
            async with ctx.typing():
                info = ytdl.extract_info(url=num, download=False)
                await ctx.send(f'**{i+1}.** **`{info["title"]}`** - **`{str(timedelta(seconds=info["duration"]))[2:]}`**')

    @commands.command()
    async def loop(self, ctx: commands.Context):
        if self.loop is False:
            self.loop = True
            await ctx.send(f'**Loop has been enabled.**')
            logger.info("Looping on")
        else:
            self.loop = False
            self.musicQueue.popleft()
            logging.info("Head of queue removed")
            await ctx.send(f'**Loop has been disabled.**')
            logger.info("Looping off.")

    @commands.command()
    async def pause(self, ctx):
        ctx.voice_client.pause()
        logger.info("Playback paused.")
        await ctx.send(f'Paused playback.')

    @commands.command()
    async def unpause(self, ctx):
        ctx.voice_client.resume()
        logger.info("Playback resumed.")
        await ctx.send(f'Resumed playback.')

    """async def updateMessage(self, ctx: discord.ext.commands.Context, newURL, message):
        info = ytdl.extract_info(newURL, download=False)
        await asyncio.get_event_loop().run_in_executor(None, await self.playingMessage.delete())

        await asyncio.get_event_loop().run_in_executor(None, await ctx.send(
            f'**Now playing: {info["title"]}** - `{str(timedelta(seconds=info["duration"]))[2:]}`\n{newURL}'))"""

    @commands.command()
    async def skip(self, ctx: commands.Context):
        if len(self.musicQueue) > 0:
            await asyncio.get_running_loop().run_in_executor(None, lambda: ctx.voice_client.stop())
            logger.info("Song skipped!.")
            # ctx.voice_client.source.cleanup()
        else:
            await asyncio.get_running_loop().run_in_executor(None, lambda: ctx.voice_client.stop())
            logger.info("Song skipped, queue empty.")
            await ctx.send("Queue empty!")
        # await self.playNext(ctx)

    @commands.command()
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""
        voice: discord.VoiceClient = discord.utils.get(
            ctx.bot.voice_clients, guild=ctx.guild)
        voice.stop()
        logger.info("Playback stopped!")

    @stream.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError(
                    "Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()

    @discord.ext.commands.command(name="play")
    async def on_message(self, ctx: discord.ext.commands.Context, message):
        if ctx.message.content.startswith('$play'):
            logging.info("$play command initialized")
            to_play = ""
            if len(self.musicQueue) == 0:
                logging.info("Empty queue, so just play song selected by user")
                voice_channel = ctx.message.author.voice.channel
                channel = None
                if voice_channel is not None:
                    channel = voice_channel
                    voice = discord.utils.get(
                        ctx.bot.voice_clients, guild=ctx.guild)
                    if voice is not None:  # test if voice is None
                        if not voice.is_connected():
                            await voice_channel.connect()
                    else:
                        await voice_channel.connect()
                if ctx.message.content.split(" ")[1].startswith(
                        'https://open.spotify.com/playlist/'):
                    logging.info("Spotify playlist given. Running getSongs")
                    to_play, self.musicQueue = getSongs(
                        ctx.message.content.split(" ")[1])
                elif ctx.message.content.split(" ")[1].startswith("https://open.spotify.com/track/"):
                    logging.info("Spotify song given. Running getSingleTrack")
                    search = getSingleTrack(ctx.message.content.split(" ")[1])
                    self.musicQueue.append(search)
                    to_play = search
                else:
                    logging.info("Youtube song selected.")
                    self.musicQueue.append(ctx.message.content.split(" ")[1])
                    to_play = ctx.message.content.split(" ")[1]

                if not ctx.voice_client.is_playing() and voice_channel is not None:
                    await Music.stream(self, ctx=ctx, url=to_play)
                else:
                    self.musicQueue.append(to_play)
                    # ctx.voice_client.pause()
                    # await asyncio.sleep(0.5)
                    # ctx.voice_client.resume()
            else:
                if ctx.message.content.split(" ")[1].startswith(
                        'https://open.spotify.com/playlist/'):
                    logging.info(
                        "Queue not empty, and spotify playlist selected. " +
                        "Adding songs from playlist to back of existing queue.")
                    to_play, newQueue = getSongs(
                        ctx.message.content.split(" ")[1])
                    for i in range(len(newQueue)):
                        self.musicQueue.append(newQueue.popleft())
                elif ctx.message.content.split(" ")[1].startswith("https://open.spotify.com/track/"):
                    logging.info(
                        "Queue not empty, and spotify song selected. Adding song to back of queue")
                    search = getSingleTrack(ctx.message.content.split(" ")[1])
                    self.musicQueue.append(search)
                else:
                    logging.info(
                        "Queue not empty, and youtube song selected. Adding song to back of queue.")
                    self.musicQueue.append(ctx.message.content.split(" ")[1])


class Song:
    def __init__(self, url: str, title: str, youtube: bool):
        self.url = url
        self.title = title
        self.youtube = youtube
