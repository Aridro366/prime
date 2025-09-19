# main.py
import asyncio
import os
from typing import List, Optional
from flask import Flask
from threading import Thread

import yt_dlp as ytdl
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio

# ------------------ Configuration ------------------
PREFIX = "?"
YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "extract_flat": False,
    "no_warnings": True,
    "default_search": "auto",
}

FFMPEG_OPTIONS = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin"
)
# ----------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True  # required for older discord.py where message content intent needed

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

ytdl_format = ytdl.YoutubeDL(YTDL_OPTS)


# Simple per-guild music player state
class GuildMusic:
    def _init_(self):
        self.queue: List[dict] = []         # list of info dicts returned by yt-dlp
        self.history: List[dict] = []       # previously played
        self.current: Optional[dict] = None
        self.volume: float = 0.5            # 0.0 - 1.0
        self.is_playing = False
        self.voice_client: Optional[discord.VoiceClient] = None
        self.player_lock = asyncio.Lock()

    def enqueue(self, info: dict):
        self.queue.append(info)

    def pop_next(self) -> Optional[dict]:
        if self.queue:
            return self.queue.pop(0)
        return None

guild_states = {}  # guild_id -> GuildMusic


def get_guild_state(guild_id: int) -> GuildMusic:
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildMusic()
    return guild_states[guild_id]


async def ensure_voice(ctx: commands.Context) -> discord.VoiceClient:
    """Make the bot join the author's voice channel if not already connected."""
    state = get_guild_state(ctx.guild.id)
    if ctx.author.voice is None or ctx.author.voice.channel is None:
        raise commands.CommandError("You must be in a voice channel to use this command.")
    channel = ctx.author.voice.channel
    if state.voice_client is None or not state.voice_client.is_connected():
        state.voice_client = await channel.connect()
    else:
        # move if in different channel
        if state.voice_client.channel.id != channel.id:
            await state.voice_client.move_to(channel)
    return state.voice_client


def ytdl_extract_info(url: str):
    """Use yt-dlp to get the info dict (no download)."""
    return ytdl_format.extract_info(url, download=False)


def create_source(info: dict):
    """
    Return the direct audio URL (info['url']) if available.
    We'll feed it to FFmpegPCMAudio.
    """
    if "url" in info:
        return info["url"]
    # fallback: sometimes 'entries' exists
    if "entries" in info and info["entries"]:
        return info["entries"][0].get("url")
    return None


async def start_playback(guild_id: int):
    state = get_guild_state(guild_id)
    async with state.player_lock:
        # If already playing, do nothing
        if state.is_playing or state.voice_client is None:
            return
        next_info = state.pop_next()
        if next_info is None:
            state.current = None
            return
        state.current = next_info
        source_url = create_source(next_info)
        if source_url is None:
            # try to extract again
            try:
                reinfo = ytdl_format.extract_info(next_info.get("webpage_url"), download=False)
                source_url = create_source(reinfo)
            except Exception:
                source_url = None
        if source_url is None:
            # skip if we can't get URL
            await asyncio.sleep(0)  # yield
            state.history.append(next_info)
            await start_playback(guild_id)
            return

        ffmpeg_opts = FFMPEG_OPTIONS
        ffmpeg_args = ffmpeg_opts.split()
        player = FFmpegPCMAudio(source_url, before_options=ffmpeg_opts, options="-vn")
        # apply volume transformer
        audio = discord.PCMVolumeTransformer(player, volume=state.volume)
        def after_play(error):
            # called when a track finishes or errors
            coro = _after_playback(guild_id, error)
            fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            try:
                fut.result()
            except Exception as e:
                print("Error in after_playback:", e)

        state.voice_client.play(audio, after=after_play)
        state.is_playing = True


async def _after_playback(guild_id: int, error):
    state = get_guild_state(guild_id)
    state.is_playing = False
    if state.current:
        state.history.append(state.current)
    state.current = None
    # small delay to avoid race
    await asyncio.sleep(0.5)
    # start next if exists
    if state.queue:
        await start_playback(guild_id)


# ------------------ Commands ------------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")


@bot.command(name="join")
async def join(ctx: commands.Context):
    """Join the caller's voice channel."""
    try:
        vc = await ensure_voice(ctx)
        await ctx.reply(f"Joined *{vc.channel.name}* ✅", mention_author=False)
    except commands.CommandError as e:
        await ctx.reply(str(e), mention_author=False)
    except Exception as e:
        await ctx.reply(f"Failed to join voice channel: {e}", mention_author=False)


@bot.command(name="leave")
async def leave(ctx: commands.Context):
    """Leave voice channel and clear queue."""
    state = get_guild_state(ctx.guild.id)
    if state.voice_client and state.voice_client.is_connected():
        try:
            await state.voice_client.disconnect()
        except Exception:
            pass
    # reset state
    guild_states.pop(ctx.guild.id, None)
    await ctx.reply("Left the voice channel and cleared the queue. 👋", mention_author=False)


@bot.command(name="play")
async def play(ctx: commands.Context, *, query: str):
    """
    Play a YouTube (or other) URL or search term.
    Usage: ?play <url or search term>
    """
    try:
        await ensure_voice(ctx)
    except commands.CommandError as e:
        await ctx.reply(str(e), mention_author=False)
        return
    msg = await ctx.reply("Processing your request... ⏳", mention_author=False)
    try:
        info = ytdl_extract_info(query)
        # If result is a playlist (unlikely since noplaylist=True), pick first
        if "entries" in info and info["entries"]:
            info = info["entries"][0]
        # store minimal helpful fields
        info_item = {
            "title": info.get("title"),
            "webpage_url": info.get("webpage_url"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "url": info.get("url"),  # direct url may be here
        }
        state = get_guild_state(ctx.guild.id)
        state.enqueue(info_item)
        await msg.edit(content=f"Queued: *{info_item.get('title')}* ▶")
        # if nothing is playing, start playback
        if not state.is_playing:
            await start_playback(ctx.guild.id)
    except Exception as e:
        await msg.edit(content=f"Error extracting audio: {e}")


@bot.command(name="stop")
async def stop(ctx: commands.Context):
    """Stop playback and clear queue."""
    state = get_guild_state(ctx.guild.id)
    if state.voice_client and state.voice_client.is_playing():
        state.voice_client.stop()
    state.queue.clear()
    state.current = None
    state.is_playing = False
    await ctx.reply("Playback stopped and queue cleared. ⏹", mention_author=False)


@bot.command(name="skip")
async def skip(ctx: commands.Context):
    """Skip current track."""
    state = get_guild_state(ctx.guild.id)
    if state.voice_client and state.voice_client.is_playing():
        state.voice_client.stop()
        await ctx.reply("Skipped the current track. ⏭", mention_author=False)
    else:
        await ctx.reply("Nothing is playing right now.", mention_author=False)


@bot.command(name="previous")
async def previous(ctx: commands.Context):
    """Play the previous track (if available)."""
    state = get_guild_state(ctx.guild.id)
    if not state.history:
        await ctx.reply("No previous track found.", mention_author=False)
        return
    prev = state.history.pop()  # last played
    state.queue.insert(0, prev)  # put it at front
    await ctx.reply(f"Queued previous: *{prev.get('title')}* ⬅", mention_author=False)
    # if not playing, start
    if not state.is_playing:
        await start_playback(ctx.guild.id)


@bot.command(name="volume")
async def volume(ctx: commands.Context, vol: int):
    """
    Set volume from 0-100.
    Usage: ?volume 75
    """
    if vol < 0 or vol > 100:
        await ctx.reply("Volume must be between 0 and 100.", mention_author=False)
        return
    state = get_guild_state(ctx.guild.id)
    state.volume = vol / 100.0
    # If currently playing, adjust volume transformer if possible
    if state.voice_client and state.voice_client.source and isinstance(state.voice_client.source, discord.PCMVolumeTransformer):
        state.voice_client.source.volume = state.volume
    await ctx.reply(f"Volume set to *{vol}%* 🔊", mention_author=False)


@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    """Show help embed with commands."""
    embed = discord.Embed(
        title="Music Bot — Commands",
        color=discord.Color.blurple(),
        description="Simple music bot. Use these commands with the prefix ?."
    )
    embed.add_field(name="?join", value="Join your voice channel.", inline=False)
    embed.add_field(name="?leave", value="Leave the voice channel and clear queue.", inline=False)
    embed.add_field(name="?play <url or search>", value="Play a YouTube link or search term. Adds to queue.", inline=False)
    embed.add_field(name="?stop", value="Stop playback and clear queue.", inline=False)
    embed.add_field(name="?skip", value="Skip the current track.", inline=False)
    embed.add_field(name="?previous", value="Play the previously played track.", inline=False)
    embed.add_field(name="?volume <0-100>", value="Set playback volume (0-100%).", inline=False)
    embed.set_footer(text="Designed for Render deployment. Keep it simple and stable.")
    await ctx.reply(embed=embed, mention_author=False)


# ------------------ Keep-alive (Flask) ------------------
# Render expects a web service. This tiny web server is just a health check.
app = Flask("bot_alive")

@app.route("/")
def index():
    return "Bot is running."


def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ------------------ Start ------------------
def main():
    # Start web server thread
    web_thread = Thread(target=run_web, daemon=True)
    web_thread.start()

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("ERROR: DISCORD_TOKEN environment variable not set.")
        return

    bot.run(token)


if __name__ == "__main__":
    main()