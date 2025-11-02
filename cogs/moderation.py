import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta
import datetime, re

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db  # MongoDB client injected from main.py

    # ==================================================
    # Helper functions
    # ==================================================
    async def get_logs_channel(self, guild):
        guild_data = await self.db.guilds.find_one({"guild_id": guild.id})
        if guild_data and "mod_logs_channel" in guild_data:
            return guild.get_channel(guild_data["mod_logs_channel"])
        return None

    async def link_blocker_enabled(self, guild_id: int):
        guild_data = await self.db.guilds.find_one({"guild_id": guild_id})
        return guild_data and guild_data.get("link_blocker", False)

    async def get_warns(self, guild_id: int, user_id: int):
        data = await self.db.warns.find_one({"guild_id": guild_id, "user_id": user_id})
        return data["warns"] if data else []

    async def add_warn(self, guild_id: int, user_id: int, reason: str, moderator_id: int):
        warns = await self.get_warns(guild_id, user_id)
        warn_number = len(warns) + 1
        await self.db.warns.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$push": {"warns": {
                "number": warn_number,
                "reason": reason,
                "moderator": moderator_id,
                "time": datetime.datetime.utcnow()
            }}},
            upsert=True
        )
        return warn_number

    # ==================================================
    # Core moderation commands
    # ==================================================
    @app_commands.command(name="kick", description="Kick a user from the server.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, *, reason: str = "No reason provided"):
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 Kicked {member.mention}. Reason: {reason}", ephemeral=True)
        try:
            await member.send(f"You were kicked from **{interaction.guild.name}**. Reason: {reason}")
        except:
            pass

        log = await self.get_logs_channel(interaction.guild)
        if log:
            await log.send(embed=discord.Embed(
                title="👢 Member Kicked",
                description=f"**User:** {member.mention}\n**Moderator:** {interaction.user.mention}\n**Reason:** {reason}",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.utcnow()
            ))

    @app_commands.command(name="ban", description="Ban a user from the server.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, *, reason: str = "No reason provided"):
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Banned {member.mention}. Reason: {reason}", ephemeral=True)
        try:
            await member.send(f"You were banned from **{interaction.guild.name}**. Reason: {reason}")
        except:
            pass

        log = await self.get_logs_channel(interaction.guild)
        if log:
            await log.send(embed=discord.Embed(
                title="🔨 Member Banned",
                description=f"**User:** {member.mention}\n**Moderator:** {interaction.user.mention}\n**Reason:** {reason}",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            ))

    @app_commands.command(name="unban", description="Unban a user by name#discriminator or ID.")
    @commands.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user: str):
        bans = [ban async for ban in interaction.guild.bans()]
        for entry in bans:
            if str(entry.user) == user or str(entry.user.id) == user:
                await interaction.guild.unban(entry.user)
                await interaction.response.send_message(f"✅ Unbanned {entry.user}", ephemeral=True)

                log = await self.get_logs_channel(interaction.guild)
                if log:
                    await log.send(embed=discord.Embed(
                        title="✅ Member Unbanned",
                        description=f"**User:** {entry.user}\n**Moderator:** {interaction.user.mention}",
                        color=discord.Color.green(),
                        timestamp=datetime.datetime.utcnow()
                    ))
                return
        await interaction.response.send_message("❌ User not found in ban list.", ephemeral=True)

    # ==================================================
    # Mute / Unmute
    # ==================================================
    @app_commands.command(name="mute", description="Timeout a user for a certain number of minutes.")
    @commands.has_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, member: discord.Member, minutes: int, *, reason: str = "No reason provided"):
        duration = timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        await interaction.response.send_message(f"🔇 Muted {member.mention} for {minutes} minutes.", ephemeral=True)
        try:
            await member.send(f"You were muted in **{interaction.guild.name}** for {minutes} minutes.\nReason: {reason}")
        except:
            pass

    @app_commands.command(name="unmute", description="Remove timeout from a user.")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        await member.timeout(None)
        await interaction.response.send_message(f"🔊 Unmuted {member.mention}.", ephemeral=True)
        try:
            await member.send(f"You were unmuted in **{interaction.guild.name}**.")
        except:
            pass

    # ==================================================
    # Warn system
    # ==================================================
    @app_commands.command(name="warn", description="Warn a user manually.")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, *, reason: str):
        warn_number = await self.add_warn(interaction.guild.id, member.id, reason, interaction.user.id)
        await interaction.response.send_message(f"⚠️ Warned {member.mention}. (Warn {warn_number}) Reason: {reason}", ephemeral=True)

        # DM user
        try:
            await member.send(f"⚠️ You received **Warn {warn_number}** in **{interaction.guild.name}**.\nReason: {reason}")
        except:
            pass

        # Auto-timeout after 3 warns
        if warn_number >= 3:
            duration = timedelta(hours=24)
            await member.timeout(duration, reason="Reached 3 warnings")
            await member.send("⏰ You’ve been timed out for **24 hours** due to reaching 3 warnings.")

        # Log
        log = await self.get_logs_channel(interaction.guild)
        if log:
            embed = discord.Embed(
                title="⚠️ User Warned",
                description=f"**User:** {member.mention}\n**Warn #:** {warn_number}\n**Reason:** {reason}\n**Moderator:** {interaction.user.mention}",
                color=discord.Color.yellow(),
                timestamp=datetime.datetime.utcnow()
            )
            await log.send(embed=embed)

    @app_commands.command(name="warnings", description="Check the warnings of a user.")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        warns = await self.get_warns(interaction.guild.id, member.id)
        if not warns:
            await interaction.response.send_message(f"✅ {member.mention} has no warnings.", ephemeral=True)
            return
        msg = "\n".join([f"**{w['number']}**. {w['reason']} - <@{w['moderator']}> ({w['time'].strftime('%Y-%m-%d')})" for w in warns])
        await interaction.response.send_message(embed=discord.Embed(
            title=f"⚠️ Warnings for {member}",
            description=msg,
            color=discord.Color.orange()
        ), ephemeral=True)

    @app_commands.command(name="clear_warns", description="Clear all warnings for a user.")
    @commands.has_permissions(manage_messages=True)
    async def clear_warns(self, interaction: discord.Interaction, member: discord.Member):
        await self.db.warns.delete_one({"guild_id": interaction.guild.id, "user_id": member.id})
        await interaction.response.send_message(f"✅ Cleared all warnings for {member.mention}.", ephemeral=True)

    # ==================================================
    # Link blocker
    # ==================================================
    @app_commands.command(name="link_blocker_on", description="Enable automatic link blocking.")
    @commands.has_permissions(manage_messages=True)
    async def link_blocker_on(self, interaction: discord.Interaction):
        await self.db.guilds.update_one({"guild_id": interaction.guild.id}, {"$set": {"link_blocker": True}}, upsert=True)
        await interaction.response.send_message("🛡️ Link blocker enabled.", ephemeral=True)

    @app_commands.command(name="link_blocker_off", description="Disable link blocking.")
    @commands.has_permissions(manage_messages=True)
    async def link_blocker_off(self, interaction: discord.Interaction):
        await self.db.guilds.update_one({"guild_id": interaction.guild.id}, {"$set": {"link_blocker": False}}, upsert=True)
        await interaction.response.send_message("⚙️ Link blocker disabled.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not await self.link_blocker_enabled(message.guild.id):
            return

        if re.search(r"(https?://|www\.|discord\.gg/)", message.content, re.IGNORECASE):
            try:
                await message.delete()
                reason = "Posted a link while link blocker is active."
                warn_number = await self.add_warn(message.guild.id, message.author.id, reason, message.guild.me.id)
                await message.channel.send(f"🚫 {message.author.mention}, links are not allowed! (Warn {warn_number})", delete_after=5)

                try:
                    await message.author.send(f"⚠️ You’ve received **Warn {warn_number}** in **{message.guild.name}** for posting a link.")
                except:
                    pass

                if warn_number >= 3:
                    await message.author.timeout(timedelta(hours=24), reason="Reached 3 warnings")
                    await message.author.send("⏰ You’ve been timed out for **24 hours** due to reaching 3 warnings.")

                log = await self.get_logs_channel(message.guild)
                if log:
                    await log.send(embed=discord.Embed(
                        title="🚫 Link Blocker Triggered",
                        description=f"**User:** {message.author.mention}\n**Warn #:** {warn_number}\n**Reason:** {reason}",
                        color=discord.Color.orange(),
                        timestamp=datetime.datetime.utcnow()
                    ))
            except:
                pass

    # ==================================================
    # Purge
    # ==================================================
    @app_commands.command(name="purge", description="Delete a number of messages.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount + 1)
        await interaction.followup.send(f"🧹 Deleted {len(deleted) - 1} messages.", ephemeral=True)

        log = await self.get_logs_channel(interaction.guild)
        if log:
            await log.send(embed=discord.Embed(
                title="🧹 Messages Purged",
                description=f"**Moderator:** {interaction.user.mention}\n**Deleted:** {len(deleted) - 1} in {interaction.channel.mention}",
                color=discord.Color.blurple(),
                timestamp=datetime.datetime.utcnow()
            ))

    # ==================================================
    # Mod log channel
    # ==================================================
    @app_commands.command(name="mod_logs_channel", description="Set the moderation logs channel.")
    @commands.has_permissions(manage_guild=True)
    async def mod_logs_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.db.guilds.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {"mod_logs_channel": channel.id}},
            upsert=True
        )
        await interaction.response.send_message(f"✅ Set mod logs channel to {channel.mention}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
