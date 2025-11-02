import discord
from discord.ext import commands
from discord import app_commands
import os, asyncio, json
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import sys, io
from keep_alive import keep_alive


keep_alive()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")  # <— Add your Mongo URI here

# === Log Channel IDs ===
BOT_LOG_CHANNEL_ID = 1419004087147561126  # bot status, code errors
CMD_LOG_CHANNEL_ID = 1419004087147561125   # command usage and command errors
SERVER_LOG_CHANNEL_ID = 1419004087147561124  # server join/leave logs


with open("config.json", "r") as f:
    config = json.load(f)

PREFIX = config.get("prefix", ".")
OWNER_ID = int(config.get("owner_id", 0))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
    
class PrimeBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(PREFIX),
            intents=intents,
            owner_id=OWNER_ID,
            help_command=None,
        )
        self.db = None  # will hold Mongo client

    async def setup_hook(self):
        # connect to MongoDB
        mongo_client = AsyncIOMotorClient(MONGO_URI)
        self.db = mongo_client["prime_bot"]

        # load all cogs
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                await self.load_extension(f"cogs.{filename[:-3]}")
                print(f"✅ Loaded cog: {filename}")

        await self.tree.sync()
        print("✅ Slash commands synced globally!")

    async def on_ready(self):
        print(f"\n🤖 Logged in as {self.user} (ID: {self.user.id})")
        print(f"🟢 Prefix: {PREFIX}")
        print(f"🛠️ Connected to {len(self.guilds)} servers")
        print("-----------------------------")
        await self.change_presence(activity=discord.Game(name=f"{PREFIX}help | Prime Bot"))


bot = PrimeBot()


async def send_log(bot, message: str, channel_id: int):
    """Send logs to a specific Discord channel."""
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(message)
    except Exception as e:
        print(f"Failed to send log: {e}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await send_log(bot, f"✅ **Bot is online** — connected as `{bot.user}`", BOT_LOG_CHANNEL_ID)

@bot.event
async def on_guild_join(guild):
    await send_log(bot, f"🟢 **Joined server:** {guild.name} (`{guild.id}`) | Members: {guild.member_count}", SERVER_LOG_CHANNEL_ID)

@bot.event
async def on_guild_remove(guild):
    await send_log(bot, f"🔴 **Left server:** {guild.name} (`{guild.id}`)", SERVER_LOG_CHANNEL_ID)


@bot.event
async def on_command(ctx):
    await send_log(ctx.bot, f"⚙️ Command used: `{ctx.command}` by **{ctx.author}** in **#{ctx.channel}**", CMD_LOG_CHANNEL_ID)

@bot.event
async def on_command_error(ctx, error):
    await send_log(ctx.bot, f"❌ **Command Error:** `{ctx.command}` by {ctx.author}\n```{error}```", CMD_LOG_CHANNEL_ID)
    await ctx.reply(f"❌ Error: {error}")

import traceback

@bot.event
async def on_error(event_method, *args, **kwargs):
    error_info = traceback.format_exc()
    await send_log(bot, f"💥 **Error in `{event_method}`:**\n```py\n{error_info}\n```", BOT_LOG_CHANNEL_ID)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("🚫 You don’t have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply("⚠️ Missing arguments. Please check usage.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        await ctx.reply(f"❌ Error: {error}")
        raise error

bot.run(TOKEN)



