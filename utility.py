import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime  # ✅ fixed import

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # {user_id: {"reason": str, "since": datetime}}
        self.afk_users = {}

    # ========================
    # 💤 AFK SYSTEM
    # ========================

    @commands.command(name="afk")
    async def afk_prefix(self, ctx, *, reason: str = "AFK"):
        """Set your AFK status (prefix command)."""
        self.afk_users[ctx.author.id] = {
            "reason": reason,
            "since": datetime.utcnow(),
        }
        await ctx.send(f"💤 {ctx.author.mention} is now AFK: **{reason}**")

    @app_commands.command(name="afk", description="Set your AFK status (slash command).")
    async def afk_slash(self, interaction: discord.Interaction, reason: str = "AFK"):
        """Set your AFK status (slash command)."""
        self.afk_users[interaction.user.id] = {
            "reason": reason,
            "since": datetime.utcnow(),
        }
        await interaction.response.send_message(
            f"💤 {interaction.user.mention} is now AFK: **{reason}**", ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Remove AFK when user sends a normal message and alert when someone tags AFK users."""
        if message.author.bot:
            return

        prefixes = ['.']
        if any(message.content.startswith(p) for p in prefixes):
            return

        # ✅ Remove AFK when user returns
        if message.author.id in self.afk_users:
            afk_data = self.afk_users.pop(message.author.id)
            duration = datetime.utcnow() - afk_data["since"]

            # Convert duration to readable format
            seconds = int(duration.total_seconds())
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours > 0:
                time_str = f"{hours}h {minutes}m"
            elif minutes > 0:
                time_str = f"{minutes}m {seconds}s"
            else:
                time_str = f"{seconds}s"

            await message.channel.send(
                f"✅ Welcome back, {message.author.mention}! "
                f"You were AFK for **{time_str}**."
            )

        # 💬 Notify if AFK users are mentioned
        for user in message.mentions:
            if user.id in self.afk_users:
                afk_data = self.afk_users[user.id]
                reason = afk_data["reason"]
                since = afk_data["since"]
                duration = datetime.utcnow() - since

                seconds = int(duration.total_seconds())
                hours, remainder = divmod(seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                if hours > 0:
                    time_str = f"{hours}h {minutes}m"
                elif minutes > 0:
                    time_str = f"{minutes}m {seconds}s"
                else:
                    time_str = f"{seconds}s"

                await message.channel.send(
                    f"💤 {user.mention} is currently AFK: **{reason}** "
                    f"(since {time_str} ago)"
                )

    # ========================
    # 🧰 OTHER UTILITY COMMANDS
    # ========================

    @commands.command(name="ping")
    async def ping(self, ctx):
        """Check the bot's latency."""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Latency: `{latency}ms`")

    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping_slash(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 Pong! Latency: `{latency}ms`")

    @commands.command(name="userinfo")
    async def userinfo(self, ctx, member: discord.Member = None):
        """Get information about a user."""
        member = member or ctx.author
        embed = discord.Embed(title=f"User Info - {member}", color=discord.Color.blue())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=False)
        embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d"), inline=False)
        embed.add_field(name="Created Account", value=member.created_at.strftime("%Y-%m-%d"), inline=False)
        await ctx.send(embed=embed)

    @app_commands.command(name="userinfo", description="Get information about a user.")
    async def userinfo_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        embed = discord.Embed(title=f"User Info - {member}", color=discord.Color.blue())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=False)
        embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d"), inline=False)
        embed.add_field(name="Created Account", value=member.created_at.strftime("%Y-%m-%d"), inline=False)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Utility(bot))
