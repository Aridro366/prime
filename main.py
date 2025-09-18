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
bot = commands.Bot(command_prefix="!", intents=intents)  # prefix only needed for internal, not used
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

async def play_next(vc, guild_id):
    queue = queues.get(guild_id, [])
    prev_queue = previous_songs.get(guild_id, [])

    if queue:
        url = queue.pop(0)
        prev_queue.append(url)
    else:
        return

    try:
        info = await get_info(url)
        if not info:
            await play_next(vc, guild_id)
            return

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(info['url'], **ffmpeg_options_template),
            volume=volumes.get(guild_id, 0.5)
        )
        vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(vc, guild_id), bot.loop))
    except:
        await play_next(vc, guild_id)

# ---------------- Slash Command Functions ----------------
async def join_vc(interaction: discord.Interaction):
    if interaction.user.voice:
        channel = interaction.user.voice.channel
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
            await interaction.response.send_message(f"✅ Moved to *{channel.name}*", ephemeral=True)
        else:
            await channel.connect()
            await interaction.response.send_message(f"✅ Joined *{channel.name}*", ephemeral=True)
    else:
        await interaction.response.send_message("❌ You must be in a voice channel!", ephemeral=True)

async def leave_vc(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        queues[interaction.guild.id] = []
        previous_songs[interaction.guild.id] = []
        await interaction.response.send_message("👋 Left the voice channel.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ I am not in a voice channel.", ephemeral=True)

async def play_song(interaction: discord.Interaction, url: str):
    guild_id = interaction.guild.id
    queues.setdefault(guild_id, []).append(url)
    previous_songs.setdefault(guild_id, [])
    volumes.setdefault(guild_id, 0.5)

    vc = interaction.guild.voice_client
    if not vc:
        if interaction.user.voice:
            vc = await interaction.user.voice.channel.connect()
        else:
            await interaction.response.send_message("❌ You must be in a voice channel!", ephemeral=True)
            return

    await interaction.response.send_message(f"✅ Added to queue: {url}", ephemeral=True)

    if not vc.is_playing():
        await play_next(vc, guild_id)

async def pause_song(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸ Music paused.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ No music is playing.", ephemeral=True)

async def resume_song(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶ Music resumed.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Music is not paused.", ephemeral=True)

async def stop_song(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        vc.stop()
        queues[interaction.guild.id] = []
        await interaction.response.send_message("⏹ Music stopped and queue cleared.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ I am not in a voice channel.", ephemeral=True)

async def skip_song(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("⏭ Skipped current song.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ No music is playing.", ephemeral=True)

async def previous_song(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    vc = interaction.guild.voice_client
    if vc and previous_songs.get(guild_id):
        url = previous_songs[guild_id].pop(-1)
        queues[guild_id].insert(0, url)
        if not vc.is_playing():
            await play_next(vc, guild_id)
        await interaction.response.send_message("⏮ Playing previous song.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ No previous song available.", ephemeral=True)

async def show_queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if queues.get(guild_id):
        msg = "🎵 Current Queue:\n"
        for i, item in enumerate(queues[guild_id], 1):
            msg += f"{i}. {item}\n"
        await interaction.response.send_message(msg, ephemeral=False)
    else:
        await interaction.response.send_message("✅ The queue is empty.", ephemeral=True)

async def set_volume(interaction: discord.Interaction, vol: int):
    if vol < 0 or vol > 100:
        await interaction.response.send_message("❌ Volume must be between 0-100.", ephemeral=True)
        return
    guild_id = interaction.guild.id
    volumes[guild_id] = vol / 100
    vc = interaction.guild.voice_client
    if vc and vc.source:
        vc.source.volume = volumes[guild_id]
    await interaction.response.send_message(f"🔊 Volume set to {vol}%", ephemeral=True)

async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🎵 Music Bot Commands", color=0x00ff00)
    embed.add_field(name="Voice Commands", value="/join | /leave", inline=False)
    embed.add_field(name="Music Commands", value="/play <url> | /pause | /resume | /stop | /skip | /previous | /queue | /volume <0-100>", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------------- Register Slash Commands ----------------
tree.add_command(app_commands.Command(name="join", description="Join your voice channel", callback=join_vc))
tree.add_command(app_commands.Command(name="leave", description="Leave the voice channel", callback=leave_vc))
tree.add_command(app_commands.Command(name="play", description="Play a YouTube URL", callback=play_song,
                                      parameters=[app_commands.Parameter(name="url", description="YouTube video URL", type=str)]))
tree.add_command(app_commands.Command(name="pause", description="Pause the music", callback=pause_song))
tree.add_command(app_commands.Command(name="resume", description="Resume the music", callback=resume_song))
tree.add_command(app_commands.Command(name="stop", description="Stop the music and clear queue", callback=stop_song))
tree.add_command(app_commands.Command(name="skip", description="Skip the current song", callback=skip_song))
tree.add_command(app_commands.Command(name="previous", description="Play previous song", callback=previous_song))
tree.add_command(app_commands.Command(name="queue", description="Show the current queue", callback=show_queue))
tree.add_command(app_commands.Command(name="volume", description="Set volume 0-100", callback=set_volume,
                                      parameters=[app_commands.Parameter(name="vol", description="Volume percent", type=int)]))
tree.add_command(app_commands.Command(name="help", description="Show help", callback=help_cmd))

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