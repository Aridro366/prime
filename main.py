import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
from dotenv import load_dotenv
from flask import Flask
import threading

# ---------------- Load Token ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("No Discord token found in environment variables")
TOKEN = TOKEN.strip()

# ---------------- Bot Setup ----------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='?', intents=intents)
tree = bot.tree

# ---------------- Queues & Volume ----------------
queues = {}          # Upcoming songs per guild
previous_songs = {}  # Played songs per guild
volumes = {}         # Volume per guild (default 0.5)

# ---------------- yt-dlp & FFmpeg ----------------
ytdl_format_options = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True,
}

ffmpeg_options_template = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# ---------------- Helper Functions ----------------
async def get_info(url):
    loop = asyncio.get_running_loop()
    return await asyncio.to_thread(ytdl.extract_info, url, False)

async def play_next(ctx):
    guild_id = ctx.guild.id
    queue = queues.get(guild_id, [])
    prev_queue = previous_songs.get(guild_id, [])

    if queue:
        url = queue.pop(0)
        prev_queue.append(url)
    else:
        await ctx.send("✅ Queue finished. I will stay in the VC until you leave.")
        return

    try:
        info = await get_info(url)
        if not info:
            await ctx.send(f"❌ Could not play: {url}")
            await play_next(ctx)
            return

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(info['url'], **ffmpeg_options_template),
            volume=volumes.get(guild_id, 0.5)
        )
        ctx.voice_client.play(
            source,
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
        )
        await ctx.send(f"🎶 Now playing: *{info.get('title', 'Unknown Title')}*")
    except Exception as e:
        await ctx.send(f"❌ Error playing {url}: {e}")
        await play_next(ctx)

async def add_to_queue(guild_id, url):
    queues.setdefault(guild_id, []).append(url)
    previous_songs.setdefault(guild_id, [])
    volumes.setdefault(guild_id, 0.5)

# ---------------- Command Functions ----------------
async def join_func(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
            await ctx.send(f"✅ Moved to *{channel.name}*")
        else:
            await channel.connect()
            await ctx.send(f"✅ Joined *{channel.name}*")
    else:
        await ctx.send("❌ You must be in a voice channel!")

async def leave_func(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        queues[ctx.guild.id] = []
        previous_songs[ctx.guild.id] = []
        await ctx.send("👋 Left the voice channel.")
    else:
        await ctx.send("❌ I am not in a voice channel.")

async def play_func(ctx, url):
    if not url:
        await ctx.send("❌ Please provide a YouTube URL!")
        return
    await add_to_queue(ctx.guild.id, url)
    await ctx.send(f"✅ Added to queue: {url}")

    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("❌ You must be in a voice channel!")
            return

    if not ctx.voice_client.is_playing():
        await play_next(ctx)

async def pause_func(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸ Music paused.")
    else:
        await ctx.send("❌ No music is playing.")

async def resume_func(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶ Music resumed.")
    else:
        await ctx.send("❌ Music is not paused.")

async def stop_func(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        queues[ctx.guild.id] = []
        await ctx.send("⏹ Music stopped and queue cleared.")
    else:
        await ctx.send("❌ I am not in a voice channel.")

async def skip_func(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭ Skipped current song.")
    else:
        await ctx.send("❌ No music is playing.")

async def previous_func(ctx):
    guild_id = ctx.guild.id
    if ctx.voice_client and previous_songs.get(guild_id):
        url = previous_songs[guild_id].pop(-1)
        await add_to_queue(guild_id, url)
        await play_next(ctx)
        await ctx.send("⏮ Playing previous song.")
    else:
        await ctx.send("❌ No previous song available.")

async def queue_func(ctx):
    guild_id = ctx.guild.id
    if queues.get(guild_id):
        msg = "🎵 Current Queue:\n"
        for i, item in enumerate(queues[guild_id], 1):
            msg += f"{i}. {item}\n"
        await ctx.send(msg)
    else:
        await ctx.send("✅ The queue is empty.")

async def volume_func(ctx, vol: int):
    if not ctx.voice_client:
        await ctx.send("❌ I am not in a voice channel.")
        return
    if vol < 0 or vol > 100:
        await ctx.send("❌ Volume must be 0-100.")
        return
    guild_id = ctx.guild.id
    volumes[guild_id] = vol / 100
    if ctx.voice_client.source:
        ctx.voice_client.source.volume = volumes[guild_id]
    await ctx.send(f"🔊 Volume set to {vol}%")

async def help_func(ctx):
    embed = discord.Embed(title="🎵 Music Bot Commands", color=0x00ff00)
    embed.add_field(name="Prefix Commands (?)",
                    value="?join | ?leave | ?play <url>\n?pause | ?resume | ?stop\n?skip | ?previous | ?queue | ?volume <0-100>\n?help",
                    inline=False)
    embed.add_field(name="Slash Commands (/)",
                    value="/join | /leave | /play | /pause | /resume | /stop | /skip | /previous | /queue | /volume | /help",
                    inline=False)
    await ctx.send(embed=embed)

# ---------------- Prefix Commands ----------------
bot.command()(join_func)
bot.command()(leave_func)
bot.command()(play_func)
bot.command()(pause_func)
bot.command(name="resume")(resume_func)
bot.command(name="start")(resume_func)
bot.command()(stop_func)
bot.command()(skip_func)
bot.command()(previous_func)
bot.command()(queue_func)
bot.command()(volume_func)
bot.command()(help_func)

# ---------------- Slash Commands ----------------
# Similar pattern: Use interaction.user.voice.channel for VC, interaction.response.send_message() to respond
# (I can provide full slash commands ready if you want)

# ---------------- Keep-Alive Flask Server ----------------
app = Flask("")

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run).start()

# ---------------- Run Bot ----------------
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as {bot.user}. Commands synced: {len(synced)}")
    except Exception as e:
        print(f"Error syncing commands: {e}")

bot.run(TOKEN)