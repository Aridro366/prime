# -*- coding: utf-8 -*-
import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
import asyncio
import random

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="?", intents=intents)

# app.py
import os
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# ---------------- Music Data ----------------
music_queue = []
now_playing = None

# ---------------- Routes ----------------
@app.route('/')
def home():
    return render_template('index.html', now_playing=now_playing, queue=music_queue)

@app.route('/play', methods=['POST'])
def play():
    global now_playing
    song = request.form.get('song')
    if song:
        music_queue.append(song)
        if not now_playing:
            now_playing = music_queue.pop(0)
    return redirect(url_for('home'))

@app.route('/next')
def next_song():
    global now_playing
    if music_queue:
        now_playing = music_queue.pop(0)
    else:
        now_playing = None
    return redirect(url_for('home'))

@app.route('/clear')
def clear_queue():
    global music_queue
    music_queue = []
    return redirect(url_for('home'))

# Optional: ignore bot-like requests (simple user-agent check)
@app.before_request
def allow_all_user_agents():
    # Render sometimes blocks requests if empty user-agent, allow all
    if 'User-Agent' not in request.headers:
        request.headers['User-Agent'] = 'Mozilla/5.0'

# ---------------- Run App ----------------
if __name__ == "__main__":
    # Use dynamic port for Render deployment
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


# -------------------- Music Data --------------------
guild_queues = {}
now_playing = {}
previous_tracks = {}
loop_mode = {}       # None, "song", "queue"
autoplay_mode = {}   # True/False
history_tracks = {}  # last 10 tracks per guild

YDL_OPTIONS = {"format": "bestaudio/best", "noplaylist": True, "quiet": True}
FFMPEG_OPTIONS = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                  "options": "-vn"}

# -------------------- Helper --------------------
async def _play_next(ctx, guild_id):
    vc = ctx.guild.voice_client
    if not vc:
        return  # Stay in VC until /leave

    # Autoplay if queue is empty and enabled
    if (guild_id not in guild_queues or not guild_queues[guild_id]) and autoplay_mode.get(guild_id, True):
        last_track = now_playing.get(guild_id)
        if last_track:
            query = f"ytsearch1:{last_track['title']} song"
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                try:
                    info = ydl.extract_info(query, download=False)["entries"][0]
                    url, title = info["url"], info.get("title", "Untitled")
                    guild_queues.setdefault(guild_id, []).append({"url": url, "title": title})
                    await ctx.followup.send(f"🔁 Autoplay added: **{title}**")
                except Exception as e:
                    print(f"Autoplay failed: {e}")
                    return

    if guild_id not in guild_queues or not guild_queues[guild_id]:
        return  # No song to play

    track = guild_queues[guild_id].pop(0)
    # Handle loop modes
    if loop_mode.get(guild_id) == "song":
        guild_queues[guild_id].insert(0, track)
    elif loop_mode.get(guild_id) == "queue":
        guild_queues[guild_id].append(track)

    url, title = track["url"], track["title"]
    source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)

    def after_playing(error):
        if error:
            print(f"Error: {error}")
        fut = asyncio.run_coroutine_threadsafe(_play_next(ctx, guild_id), bot.loop)
        try:
            fut.result()
        except Exception as e:
            print(f"Error in after_playing: {e}")

    vc.play(source, after=after_playing)
    now_playing[guild_id] = track

    # Save to history (max 10)
    history_tracks.setdefault(guild_id, []).append(track)
    if len(history_tracks[guild_id]) > 10:
        history_tracks[guild_id].pop(0)

    asyncio.create_task(ctx.followup.send(f"🎶 Now playing: **{title}**"))

# -------------------- Events --------------------
@bot.event
async def on_ready():
    print(f"{bot.user} is online!")

    # Global sync
    await bot.tree.sync()

    # Instant sync for all guilds
    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=guild)
            print(f"Synced commands for guild: {guild.name}")
        except Exception as e:
            print(f"Failed to sync guild {guild.name}: {e}")

    # Rotating interactive statuses
    statuses = [
        "Use /play to start a jam 🎶",
        "Managing queues 🎵",
        "Skipping silence ⏭️",
        "Paused? /resume ▶️",
        "Adjust volume with /volume 🔊",
        "Clear queue with /clearqueue 🗑️",
        "Made with love for music lovers"
    ]

    async def status_task():
        while True:
            for status in statuses:
                activity = discord.Activity(type=discord.ActivityType.listening, name=status)
                await bot.change_presence(status=discord.Status.online, activity=activity)
                await asyncio.sleep(5)

    bot.loop.create_task(status_task())

@bot.event
async def on_guild_join(guild):
    try:
        await bot.tree.sync(guild=guild)
        print(f"Synced commands instantly for new guild: {guild.name}")
    except Exception as e:
        print(f"Failed to sync commands for {guild.name}: {e}")

# -------------------- Music Commands --------------------
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
        await vc.move_to(channel, self_deaf=True)
    else:
        await channel.connect(self_deaf=True)
    await interaction.response.send_message(f"✅ Joined and deafened in **{channel.name}**!")

@bot.tree.command(name="leave", description="Leave the voice channel")
async def leave(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("👋 Left the voice channel.")
    else:
        await interaction.response.send_message("❌ Not in a voice channel.")

@bot.tree.command(name="play", description="Play a song from search or link")
@app_commands.describe(song_query="Search query or YouTube link")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()
    guild_id = interaction.guild.id

    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("❌ You must be in a voice channel to play music!")
        return

    vc = interaction.guild.voice_client
    channel = interaction.user.voice.channel
    if not vc:
        vc = await channel.connect(self_deaf=True)
    elif vc.channel != channel:
        await vc.move_to(channel, self_deaf=True)

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        if "http" in song_query:
            info = ydl.extract_info(song_query, download=False)
        else:
            info = ydl.extract_info(f"ytsearch:{song_query}", download=False)["entries"][0]

    url, title = info["url"], info.get("title", "Untitled")
    guild_queues.setdefault(guild_id, []).append({"url": url, "title": title})

    if not vc.is_playing():
        await _play_next(interaction, guild_id)
    else:
        await interaction.followup.send(f"➕ Added to queue: **{title}**")

@bot.tree.command(name="stop", description="Stop music and clear queue")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        vc.stop()
    guild_queues[interaction.guild.id] = []
    now_playing.pop(interaction.guild.id, None)
    loop_mode.pop(interaction.guild.id, None)
    await interaction.response.send_message("Stopped and cleared queue.")

@bot.tree.command(name="pause", description="Pause the current song")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ Paused.")

@bot.tree.command(name="resume", description="Resume paused song")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ Resumed.")

@bot.tree.command(name="next", description="Skip to the next song")
async def next(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
    await interaction.response.send_message("⏭️ Skipping...")
    await _play_next(interaction, interaction.guild.id)

@bot.tree.command(name="previous", description="Play the previous track")
async def previous(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if history_tracks.get(guild_id):
        track = history_tracks[guild_id][-1]
        guild_queues[guild_id].insert(0, track)
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
        await interaction.response.send_message("⏮️ Playing previous track...")
    else:
        await interaction.response.send_message("❌ No previous track found.")

@bot.tree.command(name="volume", description="Set music volume (0-100)")
@app_commands.describe(level="Volume percentage")
async def volume(interaction: discord.Interaction, level: int):
    vc = interaction.guild.voice_client
    if not vc or not vc.source:
        await interaction.response.send_message("❌ Nothing is playing.")
        return
    volume = max(0, min(level, 100)) / 100
    vc.source.volume = volume
    await interaction.response.send_message(f"🔊 Volume set to {level}%")

@bot.tree.command(name="clearqueue", description="Clear the current queue")
async def clearqueue(interaction: discord.Interaction):
    guild_queues[interaction.guild.id] = []
    await interaction.response.send_message("🗑️ Cleared the queue.")

@bot.tree.command(name="queue", description="Show current music queue")
async def queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    queue_list = guild_queues.get(guild_id, [])
    current = now_playing.get(guild_id)

    if not current and not queue_list:
        await interaction.response.send_message("❌ Queue is empty.")
        return

    desc = ""
    if current:
        desc += f"🎶 **Now Playing:** {current['title']}\n\n"
    if queue_list:
        desc += "**Up Next:**\n"
        for i, track in enumerate(queue_list[:10], start=1):
            desc += f"{i}. {track['title']}\n"
        if len(queue_list) > 10:
            desc += f"...and {len(queue_list) - 10} more"

    embed = discord.Embed(title="📜 Music Queue", description=desc, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

# -------------------- QoL & Fun Commands --------------------
@bot.tree.command(name="loop", description="Loop current song or entire queue")
@app_commands.describe(mode="Choose loop mode: none, song, queue")
async def loop(interaction: discord.Interaction, mode: str):
    mode = mode.lower()
    if mode not in ["none", "song", "queue"]:
        await interaction.response.send_message("❌ Invalid mode! Use: none, song, queue")
        return
    loop_mode[interaction.guild.id] = None if mode=="none" else mode
    await interaction.response.send_message(f"🔁 Loop mode set to: {mode}")

@bot.tree.command(name="shuffle", description="Shuffle the current queue")
async def shuffle(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in guild_queues or not guild_queues[guild_id]:
        await interaction.response.send_message("❌ Queue is empty.")
        return
    random.shuffle(guild_queues[guild_id])
    await interaction.response.send_message("🔀 Queue shuffled!")

@bot.tree.command(name="nowplaying", description="Show currently playing song")
async def nowplaying(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    current = now_playing.get(guild_id)
    if not current:
        await interaction.response.send_message("❌ Nothing is playing.")
        return
    await interaction.response.send_message(f"🎶 Now playing: **{current['title']}**")

@bot.tree.command(name="autoplay", description="Turn autoplay on or off")
@app_commands.describe(mode="Choose: on or off")
async def autoplay(interaction: discord.Interaction, mode: str):
    guild_id = interaction.guild.id
    mode = mode.lower()
    if mode not in ["on", "off"]:
        await interaction.response.send_message("❌ Invalid mode! Use `on` or `off`.")
        return
    autoplay_mode[guild_id] = True if mode == "on" else False
    await interaction.response.send_message(f"🔁 Autoplay is now **{mode.upper()}**")

@bot.tree.command(name="history", description="Show last 10 played tracks")
async def history(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    history = history_tracks.get(guild_id, [])
    if not history:
        await interaction.response.send_message("❌ No history available.")
        return
    desc = ""
    for i, track in enumerate(history[-10:], start=1):
        desc += f"{i}. {track['title']}\n"
    embed = discord.Embed(title="🕘 Music History", description=desc, color=discord.Color.purple())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="skipto", description="Skip to a specific song in the queue")
@app_commands.describe(position="Position in the queue")
async def skipto(interaction: discord.Interaction, position: int):
    guild_id = interaction.guild.id
    queue = guild_queues.get(guild_id, [])
    if not queue or position < 1 or position > len(queue):
        await interaction.response.send_message("❌ Invalid position.")
        return
    # Move selected track to front
    track = queue.pop(position-1)
    queue.insert(0, track)
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
    await interaction.response.send_message(f"⏩ Skipping to **{track['title']}**")
    await _play_next(interaction, guild_id)

@bot.tree.command(name="remove", description="Remove a specific song from the queue")
@app_commands.describe(position="Position in the queue")
async def remove(interaction: discord.Interaction, position: int):
    guild_id = interaction.guild.id
    queue = guild_queues.get(guild_id, [])
    if not queue or position < 1 or position > len(queue):
        await interaction.response.send_message("❌ Invalid position.")
        return
    removed = queue.pop(position-1)
    await interaction.response.send_message(f"🗑️ Removed **{removed['title']}** from the queue.")

# -------------------- Run Bot --------------------
bot.run(TOKEN)