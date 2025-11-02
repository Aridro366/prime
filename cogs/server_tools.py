import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from pymongo import MongoClient
import os

# MongoDB setup
mongo_uri = os.getenv("MONGO_URI")
cluster = MongoClient(mongo_uri)
db = cluster["primebot"]
settings = db["server_settings"]


class ServerTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Utility: Get or create server document
    def get_guild_config(self, guild_id):
        config = settings.find_one({"_id": guild_id})
        if not config:
            config = {
                "_id": guild_id,
                "welcome_channel": None,
                "welcome_message": "👋 Welcome to {server}, {member}!",
                "goodbye_channel": None,
                "goodbye_message": "😢 {member} has left the server.",
                "auto_role": None
            }
            settings.insert_one(config)
        return config

    # ---------------------------------------------------
    # 🎉 Welcome System
    # ---------------------------------------------------
    @commands.hybrid_command(name="set_welcome_channel", description="Set the welcome channel for new members.")
    @commands.has_permissions(manage_guild=True)
    async def set_welcome_channel(self, ctx, channel: discord.TextChannel):
        settings.update_one({"_id": ctx.guild.id}, {"$set": {"welcome_channel": channel.id}}, upsert=True)
        await ctx.reply(f"✅ Welcome channel set to {channel.mention}")

    @commands.hybrid_command(name="set_welcome_message", description="Set the welcome message.")
    @commands.has_permissions(manage_guild=True)
    async def set_welcome_message(self, ctx, *, message: str):
        settings.update_one({"_id": ctx.guild.id}, {"$set": {"welcome_message": message}}, upsert=True)
        await ctx.reply("✅ Welcome message updated.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = self.get_guild_config(member.guild.id)
        if config.get("welcome_channel"):
            channel = member.guild.get_channel(config["welcome_channel"])
            if channel:
                msg = config["welcome_message"].format(member=member.mention, server=member.guild.name)
                await channel.send(msg)

    # ---------------------------------------------------
    # 🧑 Auto Role System
    # ---------------------------------------------------
    @commands.hybrid_command(name="set_auto_role", description="Set a role to be given automatically to new members.")
    @commands.has_permissions(manage_roles=True)
    async def set_auto_role(self, ctx, role: discord.Role):
        settings.update_one({"_id": ctx.guild.id}, {"$set": {"auto_role": role.id}}, upsert=True)
        await ctx.reply(f"✅ Auto role set to **{role.name}**")

    @commands.hybrid_command(name="remove_auto_role", description="Disable auto-role assignment.")
    @commands.has_permissions(manage_roles=True)
    async def remove_auto_role(self, ctx):
        settings.update_one({"_id": ctx.guild.id}, {"$unset": {"auto_role": ""}}, upsert=True)
        await ctx.reply("✅ Auto role removed.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = self.get_guild_config(member.guild.id)
        role_id = config.get("auto_role")
        if role_id:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Auto role assigned")
                except discord.Forbidden:
                    pass

    # ---------------------------------------------------
    # 🛠 Server Info
    # ---------------------------------------------------
    @commands.hybrid_command(name="server_info", description="Show server information.")
    async def server_info(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(
            title=f"📊 {guild.name} Information",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown")
        embed.add_field(name="🧍 Members", value=guild.member_count)
        embed.add_field(name="💬 Channels", value=len(guild.text_channels))
        embed.add_field(name="📅 Created", value=guild.created_at.strftime("%b %d, %Y"))
        embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
        await ctx.reply(embed=embed)


        # ---------------------------------------------------
    # 🧩 Add / Remove Role
    # ---------------------------------------------------
    @commands.hybrid_command(name="add_role", description="Add a role to a member.")
    @commands.has_permissions(manage_roles=True)
    async def add_role(self, ctx, member: discord.Member, role: discord.Role):
        if role >= ctx.author.top_role:
            await ctx.reply("🚫 You can’t assign a role higher or equal to your top role.")
            return
        try:
            await member.add_roles(role)
            await ctx.reply(f"✅ Added role **{role.name}** to {member.mention}.")
            try:
                await member.send(f"🎉 You were given the role **{role.name}** in **{ctx.guild.name}**.")
            except:
                pass
        except discord.Forbidden:
            await ctx.reply("❌ I don’t have permission to add that role.")

    @commands.hybrid_command(name="remove_role", description="Remove a role from a member.")
    @commands.has_permissions(manage_roles=True)
    async def remove_role(self, ctx, member: discord.Member, role: discord.Role):
        if role >= ctx.author.top_role:
            await ctx.reply("🚫 You can’t remove a role higher or equal to your top role.")
            return
        try:
            await member.remove_roles(role)
            await ctx.reply(f"✅ Removed role **{role.name}** from {member.mention}.")
            try:
                await member.send(f"⚠️ Your role **{role.name}** was removed in **{ctx.guild.name}**.")
            except:
                pass
        except discord.Forbidden:
            await ctx.reply("❌ I don’t have permission to remove that role.")

     # ---------------------------------------------------
    # ⚙️ Owner-only: Set Bot Status
    # ---------------------------------------------------
    @commands.command(name="status", help="Change the bot's activity. Usage: .status <type> <message>")
    @commands.is_owner()
    async def status(self, ctx, activity_type: str, *, message: str):
        """
        Types:
        - playing
        - watching
        - listening
        - competing
        """
        activity_type = activity_type.lower()
        activity = None

        if activity_type == "playing":
            activity = discord.Game(name=message)
        elif activity_type == "watching":
            activity = discord.Activity(type=discord.ActivityType.watching, name=message)
        elif activity_type == "listening":
            activity = discord.Activity(type=discord.ActivityType.listening, name=message)
        elif activity_type == "competing":
            activity = discord.Activity(type=discord.ActivityType.competing, name=message)
        else:
            await ctx.reply("❌ Invalid activity type! Use: `playing`, `watching`, `listening`, or `competing`.")
            return

        await self.bot.change_presence(activity=activity)
        await ctx.reply(f"✅ Bot status updated to **{activity_type.title()} {message}**")

    @status.error
    async def status_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.reply("🚫 Only the bot owner can use this command.")


async def setup(bot):
    await bot.add_cog(ServerTools(bot))

