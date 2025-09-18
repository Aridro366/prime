import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
from dotenv import load_dotenv
from flask import Flask
import threading

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run).start()
# ---------------- Load Token ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
    TOKEN = TOKEN.strip()
else:
    raise ValueError("No Discord token found in .env")

# ---------------- Bot Setup ----------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
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
    # 'cookiefile': 'cookies.txt'  # Uncomment if using cookies
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

async def play_next(ctx, is_previous=False):
    guild_id = ctx.guild.id
    queue = queues.get(guild_id, [])
    prev_queue = previous_songs.get(guild_id, [])

    if is_previous and prev_queue:
        url = prev_queue.pop(-1)
    elif queue:
        url = queue.pop(0)
        prev_queue.append(url)
    else:
        await ctx.send("✅ Queue finished. I will stay in the VC until you say !leave or /leave.")
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
        await ctx.send(f"🎶 Now playing: {info.get('title', 'Unknown Title')}")
    except Exception as e:
        await ctx.send(f"❌ Error playing {url}: {e}")
        await play_next(ctx)

# ---------------- Commands ----------------
async def join_cmd(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
            await ctx.send(f"✅ Moved to {channel.name}")
        else:
            await channel.connect()
            await ctx.send(f"✅ Joined {channel.name}")
    else:
        await ctx.send("❌ You must be in a voice channel!")

async def leave_cmd(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Left the voice channel.")
        queues[ctx.guild.id] = []
        previous_songs[ctx.guild.id] = []
    else:
        await ctx.send("❌ I am not in a voice channel.")

async def play_cmd(ctx, url):
    if not url:
        await ctx.send("❌ Please provide a YouTube URL!")
        return

    guild_id = ctx.guild.id
    queues.setdefault(guild_id, []).append(url)
    previous_songs.setdefault(guild_id, [])
    volumes.setdefault(guild_id, 0.5)
    await ctx.send(f"✅ Added to queue: {url}")

    if not ctx.voice_client:
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            await channel.connect()
            await ctx.send(f"✅ Joined {channel.name}")
        else:
            await ctx.send("❌ You must be in a voice channel!")
            return

    if not ctx.voice_client.is_playing():
        await play_next(ctx)

async def pause_cmd(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸ Paused the music.")
    else:
        await ctx.send("❌ No music is playing right now.")

async def resume_cmd(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶ Resumed the music.")
    else:
        await ctx.send("❌ Music is not paused.")

async def stop_cmd(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        queues[ctx.guild.id] = []
        await ctx.send("⏹ Stopped the music and cleared the queue.")
    else:
        await ctx.send("❌ I am not in a voice channel.")

async def skip_cmd(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭ Skipped the current song.")
    else:
        await ctx.send("❌ No music is playing right now.")

async def previous_cmd(ctx):
    if ctx.voice_client:
        await play_next(ctx, is_previous=True)
    else:
        await ctx.send("❌ I am not in a voice channel.")

async def queue_cmd(ctx):
    guild_id = ctx.guild.id
    if queues.get(guild_id):
        msg = "🎵 *Current Queue:*\n"
        for i, item in enumerate(queues[guild_id], 1):
            msg += f"{i}. {item}\n"
        await ctx.send(msg)
    else:
        await ctx.send("✅ The queue is empty.")

async def volume_cmd(ctx, vol: int):
    if not ctx.voice_client:
        await ctx.send("❌ I am not in a voice channel.")
        return
    if vol < 0 or vol > 100:
        await ctx.send("❌ Please provide a volume between 0 and 100.")
        return
    guild_id = ctx.guild.id
    volumes[guild_id] = vol / 100
    if ctx.voice_client.source:
        ctx.voice_client.source.volume = volumes[guild_id]
    await ctx.send(f"🔊 Volume set to {vol}%")

async def help_cmd(ctx):
    help_text = """
🎵 *Music Bot Commands* 🎵

*Prefix commands (!):*
!join - Join your VC
!leave - Leave VC
!play <url> - Play music
!pause - Pause current song
!resume / !start - Resume song
!stop - Stop and clear queue
!skip - Skip current song
!previous - Play previous song
!queue - Show current queue
!volume <0-100> - Set volume
!help - Show this message

*Slash commands (/):*
/join, /leave, /play, /pause, /resume, /stop, /skip, /previous, /queue, /volume, /help
"""
    await ctx.send(help_text)

# ---------------- Prefix Commands ----------------
bot.command()(join_cmd)
bot.command()(leave_cmd)
bot.command()(play_cmd)
bot.command()(pause_cmd)
bot.command(name="resume")(resume_cmd)
bot.command(name="start")(resume_cmd)
bot.command()(stop_cmd)
bot.command()(skip_cmd)
bot.command()(previous_cmd)
bot.command()(queue_cmd)
bot.command()(volume_cmd)
bot.command()(help_cmd)

# ---------------- Slash Commands ----------------
@tree.command(name="join", description="Join your voice channel")
async def join_slash(interaction: discord.Interaction):
    ctx = await bot.get_context(interaction)
    await join_cmd(ctx)
    await interaction.response.send_message("✅ Join command executed.", ephemeral=True)

@tree.command(name="leave", description="Leave the voice channel")
async def leave_slash(interaction: discord.Interaction):
    ctx = await bot.get_context(interaction)
    await leave_cmd(ctx)
    await interaction.response.send_message("👋 Leave command executed.", ephemeral=True)

@tree.command(name="play", description="Play a YouTube URL")
@app_commands.describe(url="YouTube video URL")
async def play_slash(interaction: discord.Interaction, url: str):
    ctx = await bot.get_context(interaction)
    await play_cmd(ctx, url)
    await interaction.response.send_message(f"✅ Added to queue: {url}", ephemeral=True)

@tree.command(name="pause", description="Pause the music")
async def pause_slash(interaction: discord.Interaction):
    ctx = await bot.get_context(interaction)
    await pause_cmd(ctx)
    await interaction.response.send_message("⏸ Paused the music.", ephemeral=True)

@tree.command(name="resume", description="Resume the music")
async def resume_slash(interaction: discord.Interaction):
    ctx = await bot.get_context(interaction)
    await resume_cmd(ctx)
    await interaction.response.send_message("▶ Resumed the music.", ephemeral=True)

@tree.command(name="stop", description="Stop the music and clear the queue")
async def stop_slash(interaction: discord.Interaction):
    ctx = await bot.get_context(interaction)
    await stop_cmd(ctx)
    await interaction.response.send_message("⏹ Music stopped.", ephemeral=True)

@tree.command(name="skip", description="Skip the current song")
async def skip_slash(interaction: discord.Interaction):
    ctx = await bot.get_context(interaction)
    await skip_cmd(ctx)
    await interaction.response.send_message("⏭ Skipped the current song.", ephemeral=True)

@tree.command(name="previous", description="Play the previous song")
async def previous_slash(interaction: discord.Interaction):
    ctx = await bot.get_context(interaction)
    await previous_cmd(ctx)
    await interaction.response.send_message("⏮ Playing previous song.", ephemeral=True)

@tree.command(name="queue", description="Show current queue")
async def queue_slash(interaction: discord.Interaction):
    ctx = await bot.get_context(interaction)
    await queue_cmd(ctx)
    await interaction.response.send_message("✅ Queue shown above.", ephemeral=True)

@tree.command(name="volume", description="Set volume 0-100")
@app_commands.describe(vol="Volume percentage")
async def volume_slash(interaction: discord.Interaction, vol: int):
    ctx = await bot.get_context(interaction)
    await volume_cmd(ctx, vol)
    await interaction.response.send_message(f"🔊 Volume set to {vol}%", ephemeral=True)

@tree.command(name="help", description="Show help message")
async def help_slash(interaction: discord.Interaction):
    ctx = await bot.get_context(interaction)
    await help_cmd(ctx)
    await interaction.response.send_message("✅ Help shown above.", ephemeral=True)

# ---------------- On Ready ----------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")

# ---------------- Run Bot ----------------

bot.run(TOKEN)
