# music_bot.py
import os
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
from dotenv import load_dotenv
from flask import Flask
import yt_dlp
import asyncio

# ---------------- Keep Alive Server ----------------
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    import threading
    t = threading.Thread(target=run)
    t.start()

# ---------------- Load Environment Variables ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ---------------- Bot Setup ----------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# ---------------- Music Setup ----------------
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
}
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# ---------------- Queue System ----------------
guild_queues = {}
guild_previous = {}

async def play_next(ctx, guild_id):
    if guild_queues[guild_id]:
        url = guild_queues[guild_id].pop(0)
        info = ytdl.extract_info(url, download=False)
        source = FFmpegPCMAudio(info['url'], **ffmpeg_options)
        ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx, guild_id), bot.loop))
        guild_previous[guild_id] = url
        await ctx.send(f"Now playing: {info['title']}")

# ---------------- Music Commands ----------------
@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"Joined {channel}!")
    else:
        await ctx.send("You are not in a voice channel!")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Left the voice channel!")
    else:
        await ctx.send("I am not in a voice channel!")

@bot.command()
async def play(ctx, url):
    guild_id = ctx.guild.id
    if guild_id not in guild_queues:
        guild_queues[guild_id] = []
    if guild_id not in guild_previous:
        guild_previous[guild_id] = None

    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You are not in a voice channel!")
            return

    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        guild_queues[guild_id].append(url)
        await ctx.send("Added to queue!")
    else:
        info = ytdl.extract_info(url, download=False)
        source = FFmpegPCMAudio(info['url'], **ffmpeg_options)
        ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx, guild_id), bot.loop))
        guild_previous[guild_id] = url
        await ctx.send(f"Now playing: {info['title']}")

@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("Music stopped!")
    else:
        await ctx.send("Nothing is playing!")

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Music paused!")
    else:
        await ctx.send("Nothing is playing!")

@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Music resumed!")
    else:
        await ctx.send("Nothing is paused!")

@bot.command()
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Skipped!")
    else:
        await ctx.send("Nothing to skip!")

@bot.command()
async def previous(ctx):
    guild_id = ctx.guild.id
    if guild_previous.get(guild_id):
        await play(ctx, guild_previous[guild_id])
    else:
        await ctx.send("No previous song found!")

@bot.command()
async def volume(ctx, vol: int):
    if ctx.voice_client and 0 <= vol <= 100:
        ctx.voice_client.source = FFmpegPCMAudio(ctx.voice_client.source.url, **ffmpeg_options)
        ctx.voice_client.source.volume = vol / 100
        await ctx.send(f"Volume set to {vol}%")
    else:
        await ctx.send("Volume must be 0-100 and bot must be in voice channel!")

@bot.command()
async def help(ctx):
    help_text = """
*Music Bot Commands*
!join - Join your voice channel
!leave - Leave voice channel
!play <URL> - Play a song
!pause - Pause music
!resume - Resume music
!stop - Stop music
!skip - Skip current song
!previous - Play previous song
!volume <0-100> - Set volume
!help - Show this message
"""
    await ctx.send(help_text)

# ---------------- Bot Ready ----------------
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.change_presence(activity=discord.Game(name="!play <url>"))

# ---------------- Keep Alive & Run ----------------
keep_alive()
bot.run(TOKEN)