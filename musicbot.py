import sys
sys.stdout.reconfigure(encoding='utf-8')  # Fix emoji printing

import os
import random
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import tempfile
from dotenv import load_dotenv
from keep_alive import keep_alive
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

keep_alive()
# -------------------- Music Data --------------------
guild_queues = {}
now_playing = {}
loop_mode = {}
autoplay_mode = {}
history_tracks = {}

# -------------------- YouTube Cookies from ENV --------------------
BASE_YDL_OPTIONS = {"format": "bestaudio/best", "noplaylist": True, "quiet": True}
yt_cookie_env = os.getenv("YTC_COOKIE")
if yt_cookie_env:
    temp_cookie = tempfile.NamedTemporaryFile(delete=False)
    temp_cookie.write(yt_cookie_env.encode())
    temp_cookie.flush()
    cookies_file = temp_cookie.name
    YDL_OPTIONS = {**BASE_YDL_OPTIONS, "cookiefile": cookies_file}
else:
    YDL_OPTIONS = BASE_YDL_OPTIONS

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn"
}

# -------------------- Helper Functions --------------------
def extract_info_safe(query, download=False):
    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            return ydl.extract_info(query, download=download)
    except Exception:
        with yt_dlp.YoutubeDL(BASE_YDL_OPTIONS) as ydl:
            return ydl.extract_info(query, download=download)

def is_url(text):
    return text.startswith("http://") or text.startswith("https://")

async def _play_next(interaction: discord.Interaction, guild_id: int):
    vc = interaction.guild.voice_client
    if not vc:
        return

    # Autoplay if queue empty
    if (guild_id not in guild_queues or not guild_queues[guild_id]) and autoplay_mode.get(guild_id, False):
        last_track = now_playing.get(guild_id)
        if last_track:
            query = f"ytsearch1:{last_track['title']} song"
            try:
                info = extract_info_safe(query, download=False)["entries"][0]
                guild_queues.setdefault(guild_id, []).append({"url": info["url"], "title": info["title"]})
                await interaction.followup.send(f"🔁 Autoplay added: **{info['title']}**")
            except Exception as e:
                print(f"[Autoplay failed]: {e}")

    if guild_id not in guild_queues or not guild_queues[guild_id]:
        return

    track = guild_queues[guild_id].pop(0)

    # Loop modes
    if loop_mode.get(guild_id) == "song":
        guild_queues[guild_id].insert(0, track)
    elif loop_mode.get(guild_id) == "queue":
        guild_queues[guild_id].append(track)

    url, title = track["url"], track["title"]

    def after_playing(error):
        if error:
            print(f"[Player error]: {error}")
        fut = asyncio.run_coroutine_threadsafe(_play_next(interaction, guild_id), bot.loop)
        try:
            fut.result()
        except Exception as e:
            print(f"[After playing error]: {e}")

    try:
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS), volume=0.5)
        vc.play(source, after=after_playing)
    except Exception as e:
        print(f"[Playback failed]: {e}")
        return

    now_playing[guild_id] = track
    history_tracks.setdefault(guild_id, []).append(track)
    if len(history_tracks[guild_id]) > 10:
        history_tracks[guild_id].pop(0)

    await interaction.followup.send(f"🎶 Now playing: **{title}**")

# -------------------- Events --------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} is online")

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} is online")

    # Rotating interactive statuses
    statuses = [
        "Use /play to start a jam 🎶",
        "Managing queues 🎵",
        "Skipping silence ⏭️",
        "Paused? /resume ▶️",
        "Adjust volume with /volume 🔊",
        "Clear queue with /clearqueue 🗑️",
        "Made with love for music lovers 💖"
    ]

    async def status_task():
        while True:
            for status in statuses:
                activity = discord.Activity(type=discord.ActivityType.listening, name=status)
                await bot.change_presence(status=discord.Status.online, activity=activity)
                await asyncio.sleep(10)  # Change every 10 seconds

    bot.loop.create_task(status_task())


# -------------------- Join & Leave --------------------
@bot.tree.command(name="join", description="Join your voice channel")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ You must be in a voice channel!")
        return
    vc = interaction.guild.voice_client
    channel = interaction.user.voice.channel
    if vc and vc.channel == channel:
        await interaction.response.send_message("✅ Already in your voice channel!")
        return
    elif vc:
        await vc.move_to(channel)
    else:
        await channel.connect()
    await interaction.response.send_message(f"✅ Joined **{channel.name}**!")

@bot.tree.command(name="leave", description="Leave the voice channel")
async def leave(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("👋 Left the voice channel.")
    else:
        await interaction.response.send_message("❌ Not in a voice channel.")

# -------------------- Play --------------------
@bot.tree.command(name="play", description="Play a song from YouTube")
@app_commands.describe(song="Search query or YouTube link")
async def play(interaction: discord.Interaction, song: str):
    await interaction.response.defer(thinking=True)
    
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("❌ Join a voice channel first.")
        return

    vc = interaction.guild.voice_client
    if not vc:
        vc = await interaction.user.voice.channel.connect()
    elif vc.channel != interaction.user.voice.channel:
        await vc.move_to(interaction.user.voice.channel)

    msg = await interaction.followup.send("🔎 Searching for your song...")

    loop = asyncio.get_event_loop()
    try:
        query = song if is_url(song) else f"ytsearch:{song}"
        info = await loop.run_in_executor(None, lambda: extract_info_safe(query, download=False))
        if "entries" in info:
            info = info["entries"][0]
        url, title = info["url"], info.get("title", "Untitled")
    except Exception as e:
        await msg.edit(content=f"❌ Failed to get the song: {e}")
        return

    guild_queues.setdefault(interaction.guild.id, []).append({"url": url, "title": title})

    if not vc.is_playing():
        try:
            await _play_next(interaction, interaction.guild.id)
            await msg.edit(content=f"🎶 Now playing: **{title}**")
        except Exception as e:
            await msg.edit(content=f"❌ Playback failed: {e}")
    else:
        await msg.edit(content=f"➕ Added to queue: **{title}**")

# -------------------- Music Controls --------------------
@bot.tree.command(name="stop", description="Stop music and clear queue")
async def stop(interaction: discord.Interaction):
    await interaction.response.defer()
    guild_queues[interaction.guild.id] = []
    now_playing.pop(interaction.guild.id, None)
    loop_mode.pop(interaction.guild.id, None)
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
    await interaction.followup.send("🛑 Stopped and cleared queue.")

@bot.tree.command(name="pause", description="Pause music")
async def pause(interaction: discord.Interaction):
    await interaction.response.defer()
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.followup.send("⏸️ Paused.")
    else:
        await interaction.followup.send("❌ Nothing is playing.")

@bot.tree.command(name="resume", description="Resume music")
async def resume(interaction: discord.Interaction):
    await interaction.response.defer()
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.followup.send("▶️ Resumed.")
    else:
        await interaction.followup.send("❌ Nothing to resume.")

@bot.tree.command(name="skip", description="Skip current song")
async def skip(interaction: discord.Interaction):
    await interaction.response.defer()
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.followup.send("⏭️ Skipped.")
    else:
        await interaction.followup.send("❌ Nothing is playing.")

@bot.tree.command(name="skipto", description="Skip to a specific song in queue")
@app_commands.describe(position="Position in queue")
async def skipto(interaction: discord.Interaction, position: int):
    await interaction.response.defer()
    q = guild_queues.get(interaction.guild.id, [])
    if not q or position < 1 or position > len(q):
        await interaction.followup.send("❌ Invalid position.")
        return
    track = q.pop(position-1)
    q.insert(0, track)
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
    await interaction.followup.send(f"⏩ Skipping to **{track['title']}**")

@bot.tree.command(name="previous", description="Play previous track")
async def previous(interaction: discord.Interaction):
    await interaction.response.defer()
    h = history_tracks.get(interaction.guild.id)
    if not h:
        await interaction.followup.send("❌ No previous track.")
        return
    track = h[-1]
    guild_queues.setdefault(interaction.guild.id, []).insert(0, track)
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
    await interaction.followup.send(f"⏮️ Playing previous track: **{track['title']}**")

@bot.tree.command(name="queue", description="Show queue")
async def queue(interaction: discord.Interaction):
    await interaction.response.defer()
    q = guild_queues.get(interaction.guild.id, [])
    now = now_playing.get(interaction.guild.id)
    desc = ""
    if now:
        desc += f"🎶 **Now Playing:** {now['title']}\n\n"
    if q:
        desc += "**Up Next:**\n"
        for i, t in enumerate(q[:10], start=1):
            desc += f"{i}. {t['title']}\n"
        if len(q) > 10:
            desc += f"...and {len(q)-10} more"
    if not desc:
        desc = "❌ Queue empty."
    await interaction.followup.send(embed=discord.Embed(title="📜 Queue", description=desc, color=discord.Color.blue()))

@bot.tree.command(name="clearqueue", description="Clear queue")
async def clearqueue(interaction: discord.Interaction):
    guild_queues[interaction.guild.id] = []
    await interaction.response.send_message("🗑️ Cleared the queue.")

@bot.tree.command(name="remove", description="Remove a song from queue")
@app_commands.describe(position="Position in queue")
async def remove(interaction: discord.Interaction, position: int):
    q = guild_queues.get(interaction.guild.id, [])
    if not q or position < 1 or position > len(q):
        await interaction.response.send_message("❌ Invalid position.")
        return
    removed = q.pop(position-1)
    await interaction.response.send_message(f"🗑️ Removed **{removed['title']}**")

@bot.tree.command(name="loop", description="Loop song or queue")
@app_commands.describe(mode="none, song, queue")
async def loop(interaction: discord.Interaction, mode: str):
    mode = mode.lower()
    if mode not in ["none","song","queue"]:
        await interaction.response.send_message("❌ Invalid mode")
        return
    loop_mode[interaction.guild.id] = None if mode=="none" else mode
    await interaction.response.send_message(f"🔁 Loop mode set to: {mode}")

@bot.tree.command(name="shuffle", description="Shuffle queue")
async def shuffle(interaction: discord.Interaction):
    q = guild_queues.get(interaction.guild.id, [])
    if not q:
        await interaction.response.send_message("❌ Queue empty.")
        return
    random.shuffle(q)
    await interaction.response.send_message("🔀 Queue shuffled!")

@bot.tree.command(name="autoplay", description="Toggle autoplay")
@app_commands.describe(mode="on/off")
async def autoplay(interaction: discord.Interaction, mode: str):
    mode = mode.lower()
    if mode not in ["on","off"]:
        await interaction.response.send_message("❌ Use 'on' or 'off'")
        return
    autoplay_mode[interaction.guild.id] = True if mode=="on" else False
    await interaction.response.send_message(f"🔁 Autoplay set to {mode.upper()}")

@bot.tree.command(name="nowplaying", description="Show now playing song")
async def nowplaying(interaction: discord.Interaction):
    now = now_playing.get(interaction.guild.id)
    if not now:
        await interaction.response.send_message("❌ Nothing is playing.")
        return
    await interaction.response.send_message(f"🎶 Now playing: **{now['title']}**")

@bot.tree.command(name="history", description="Show last 10 played tracks")
async def history(interaction: discord.Interaction):
    h = history_tracks.get(interaction.guild.id, [])
    if not h:
        await interaction.response.send_message("❌ No history.")
        return
    desc = ""
    for i, t in enumerate(h[-10:], start=1):
        desc += f"{i}. {t['title']}\n"
    await interaction.response.send_message(embed=discord.Embed(title="🕘 History", description=desc, color=discord.Color.purple()))

@bot.tree.command(name="volume", description="Set volume 0-100")
@app_commands.describe(level="Volume percent")
async def volume(interaction: discord.Interaction, level: int):
    vc = interaction.guild.voice_client
    if not vc or not vc.source:
        await interaction.response.send_message("❌ Nothing is playing.")
        return
    vc.source.volume = max(0, min(level,100))/100
    await interaction.response.send_message(f"🔊 Volume set to {level}%")

# -------------------- Run Bot --------------------
bot.run(TOKEN)
