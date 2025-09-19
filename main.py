import os
import asyncio
import traceback
from threading import Thread
from typing import List, Optional, Dict

from flask import Flask
import yt_dlp as ytdl
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio

# ---------------- Config ----------------
PREFIX = "?"
YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
}
FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin"
FFMPEG_OPTS = "-vn"
COOKIE_PATH = "/tmp/ytdl_cookies.txt"
# ----------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ---------- Cookie handling ----------
cookie_env = os.environ.get("YTDL_COOKIES")
if cookie_env:
    try:
        with open(COOKIE_PATH, "w", encoding="utf-8") as f:
            f.write(cookie_env)
        YTDL_OPTS["cookiefile"] = COOKIE_PATH
        print("Using Netscape cookies from YTDL_COOKIES environment variable.")
    except Exception as e:
        print("Failed to write cookies:", e)
else:
    print("No YTDL_COOKIES provided. Bot will only play public videos.")

ytdl_format = ytdl.YoutubeDL(YTDL_OPTS)

# ---------- Guild music state ----------
class GuildMusic:
    def _init_(self):
        self.queue: List[dict] = []
        self.history: List[dict] = []
        self.current: Optional[dict] = None
        self.volume: float = 0.5
        self.is_playing: bool = False
        self.player_lock = asyncio.Lock()
        self.voice_client = None

guild_states: Dict[int, GuildMusic] = {}

def get_guild_state(guild_id: int) -> GuildMusic:
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildMusic()
    return guild_states[guild_id]

# ---------- helpers ----------
def ytdl_extract_info(query: str):
    return ytdl_format.extract_info(query, download=False)

def create_source(info: dict) -> Optional[str]:
    if not info:
        return None
    if info.get("url"):
        return info["url"]
    if info.get("entries"):
        for e in info["entries"]:
            if e.get("url"):
                return e["url"]
    return info.get("webpage_url")

def canonical_voice_client_for_guild(guild: discord.Guild) -> Optional[discord.VoiceClient]:
    return guild.voice_client

# ---------- voice & playback ----------
async def ensure_voice(ctx: commands.Context) -> discord.VoiceClient:
    if not ctx.author.voice or not ctx.author.voice.channel:
        raise commands.CommandError("You must be in a voice channel to use this command.")
    channel = ctx.author.voice.channel
    state = get_guild_state(ctx.guild.id)
    guild_vc = canonical_voice_client_for_guild(ctx.guild)
    try:
        if guild_vc is None:
            vc = await channel.connect()
            state.voice_client = vc
            return vc
        else:
            if guild_vc.channel.id != channel.id:
                await guild_vc.move_to(channel)
            state.voice_client = guild_vc
            return guild_vc
    except Exception as e:
        print("ensure_voice error:", e)
        traceback.print_exc()
        raise commands.CommandError(f"Failed to join/move to voice channel: {e}")

async def _after_playback(guild_id: int, error):
    state = get_guild_state(guild_id)
    state.is_playing = False
    if state.current:
        state.history.append(state.current)
    state.current = None
    await asyncio.sleep(0.3)
    if state.queue:
        await start_playback(guild_id)

async def start_playback(guild_id: int):
    state = get_guild_state(guild_id)
    guild = bot.get_guild(guild_id)
    if guild is None:
        return

    state.voice_client = canonical_voice_client_for_guild(guild)
    if state.voice_client is None or not state.voice_client.is_connected():
        state.is_playing = False
        return

    async with state.player_lock:
        if state.is_playing and state.voice_client.is_playing():
            return

        if not state.queue:
            state.current = None
            state.is_playing = False
            return

        next_info = state.queue.pop(0)
        state.current = next_info
        source_url = create_source(next_info)
        if not source_url:
            try:
                if next_info.get("webpage_url"):
                    fresh = ytdl_format.extract_info(next_info["webpage_url"], download=False)
                    source_url = create_source(fresh)
            except Exception as e:
                print("Failed re-extracting:", e)

        if not source_url:
            state.history.append(state.current)
            state.current = None
            state.is_playing = False
            await asyncio.sleep(0)
            await start_playback(guild_id)
            return

        try:
            player = FFmpegPCMAudio(source_url, before_options=FFMPEG_BEFORE, options=FFMPEG_OPTS)
            audio = discord.PCMVolumeTransformer(player, volume=state.volume)

            def _after_play_callback(error):
                coro = _after_playback(guild_id, error)
                fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
                try:
                    fut.result()
                except Exception as e:
                    print("after_playback fut error:", e)

            state.voice_client.play(audio, after=_after_play_callback)
            state.is_playing = True
        except Exception as e:
            print("start_playback error:", e)
            traceback.print_exc()
            state.history.append(state.current)
            state.current = None
            state.is_playing = False
            await asyncio.sleep(0.2)
            await start_playback(guild_id)

# ---------------- Commands ----------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

@bot.command(name="join")
async def join(ctx: commands.Context):
    try:
        vc = await ensure_voice(ctx)
        await ctx.reply(f"Joined *{vc.channel.name}* ✅", mention_author=False)
    except commands.CommandError as e:
        await ctx.reply(str(e), mention_author=False)
    except Exception as e:
        await ctx.reply(f"Failed to join: {e}", mention_author=False)

@bot.command(name="leave")
async def leave(ctx: commands.Context):
    state = get_guild_state(ctx.guild.id)
    guild_vc = canonical_voice_client_for_guild(ctx.guild)
    if guild_vc and guild_vc.is_connected():
        try:
            await guild_vc.disconnect()
        except Exception:
            pass
    guild_states.pop(ctx.guild.id, None)
    await ctx.reply("Left the voice channel and cleared the queue.", mention_author=False)

@bot.command(name="play")
async def play(ctx: commands.Context, *, query: str):
    try:
        await ensure_voice(ctx)
    except commands.CommandError as e:
        await ctx.reply(str(e), mention_author=False)
        return

    msg = await ctx.reply("Processing... ⏳", mention_author=False)
    try:
        info = ytdl_extract_info(query)
        if info.get("entries"):
            info = info["entries"][0]
        item = {
            "title": info.get("title"),
            "webpage_url": info.get("webpage_url"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "url": info.get("url"),
        }
        state = get_guild_state(ctx.guild.id)
        state.queue.append(item)
        await msg.edit(content=f"Queued: *{item.get('title')}* ▶")
        if not state.is_playing:
            await start_playback(ctx.guild.id)
    except Exception as e:
        await msg.edit(content=f"Error extracting audio: {e}")

@bot.command(name="stop")
async def stop(ctx: commands.Context):
    state = get_guild_state(ctx.guild.id)
    guild_vc = canonical_voice_client_for_guild(ctx.guild)
    if guild_vc and guild_vc.is_playing():
        guild_vc.stop()
    state.queue.clear()
    state.current = None
    state.is_playing = False
    await ctx.reply("Playback stopped and queue cleared. ⏹", mention_author=False)

@bot.command(name="skip")
async def skip(ctx: commands.Context):
    guild_vc = canonical_voice_client_for_guild(ctx.guild)
    if guild_vc and guild_vc.is_playing():
        guild_vc.stop()
        await ctx.reply("Skipped current track. ⏭", mention_author=False)
    else:
        await ctx.reply("Nothing is playing right now.", mention_author=False)

@bot.command(name="previous")
async def previous(ctx: commands.Context):
    state = get_guild_state(ctx.guild.id)
    if not state.history:
        await ctx.reply("No previous track found.", mention_author=False)
        return
    prev = state.history.pop()
    state.queue.insert(0, prev)
    await ctx.reply(f"Queued previous: *{prev.get('title')}* ⬅", mention_author=False)
    if not state.is_playing:
        await start_playback(ctx.guild.id)

@bot.command(name="volume")
async def volume(ctx: commands.Context, vol: int):
    if vol < 0 or vol > 100:
        await ctx.reply("Volume must be between 0 and 100.", mention_author=False)
        return
    state = get_guild_state(ctx.guild.id)
    state.volume = vol / 100.0
    guild_vc = canonical_voice_client_for_guild(ctx.guild)
    try:
        if guild_vc and guild_vc.source and isinstance(guild_vc.source, discord.PCMVolumeTransformer):
            guild_vc.source.volume = state.volume
    except Exception:
        pass
    await ctx.reply(f"Volume set to *{vol}%* 🔊", mention_author=False)

@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    em = discord.Embed(title="Music Bot — Commands", color=discord.Color.blurple(),
                       description="Use the commands with the ? prefix.")
    em.add_field(name="?join", value="Join your voice channel.", inline=False)
    em.add_field(name="?leave", value="Leave the voice channel and clear queue.", inline=False)
    em.add_field(name="?play <url or search>", value="Play a YouTube link or search term. Adds to queue.", inline=False)
    em.add_field(name="?stop", value="Stop playback and queue cleared.", inline=False)
    em.add_field(name="?skip", value="Skip the current track.", inline=False)
    em.add_field(name="?previous", value="Play the previously played track.", inline=False)
    em.add_field(name="?volume <0-100>", value="Set playback volume (0-100%).", inline=False)
    await ctx.reply(embed=em, mention_author=False)

# ---------------- Keep-alive (Flask) ----------------
app = Flask("music_bot_alive")

@app.route("/")
def index():
    return "Music bot is running."

def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ---------------- Main ----------------
def main():
    Thread(target=run_web, daemon=True).start()
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("ERROR: DISCORD_TOKEN env var not set.")
        return
    bot.run(token)

if __name__ == "__main__":
    main()