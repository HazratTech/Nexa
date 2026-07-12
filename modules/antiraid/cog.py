import discord
from discord import app_commands
from discord.ext import commands, tasks
from loguru import logger
from typing import Optional, List
import datetime

from core.database import Database
from core.models.guild_models import AntiRaidSettings
from core.engines.antiraid_engine import AntiRaidEngine, RaidMode
from core.engines.action_dispatcher import ActionDispatcher
from modules.antiraid.services import AntiRaidService


class AntiRaidCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.engine = AntiRaidEngine(bot)
        self.dispatcher = ActionDispatcher(bot)
        self.auto_recovery_loop.start()

    def cog_unload(self):
        self.auto_recovery_loop.cancel()

    @app_commands.command(name="antiraid_config", description="Interactive dashboard to customize anti-raid settings")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def antiraid_config_dashboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings = await AntiRaidService.get_settings(interaction.guild_id)
        current_mode = await self.engine.get_raid_mode(interaction.guild_id)
        from modules.antiraid.ui import AntiRaidDashboardView
        view = AntiRaidDashboardView(interaction.guild_id, settings, current_mode)
        view.parent_cog = self
        await interaction.followup.send(view=view)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        guild = member.guild
        settings = await AntiRaidService.get_settings(guild.id)
        if not settings.enabled:
            return

        # 1. Process join through engine checks
        is_raid, mode, reason = await self.engine.process_join(member, settings)
        
        # 2. Check Action Escalations
        if is_raid:
            # Re-read incident ID from Redis if join flood triggered lockdown
            redis = self.engine._get_redis()
            incident_id = await redis.get(f"raid:{guild.id}:incident_id")

            # Perform actions based on current raid mode or suspicious trigger
            if mode >= RaidMode.LOCKDOWN:
                action_type = "kick" if settings.raid_mode_action == "lockdown" else "ban"
                if mode == RaidMode.PANIC:
                    action_type = "ban"

                action_reason = f"Anti-Raid Action: Joined during active raid lockdown. Reason: {reason}"
                
                # DM user if configured
                if settings.dm_on_kick and action_type == "kick":
                    try:
                        await member.send(settings.dm_message)
                    except discord.Forbidden:
                        pass

                # Execute action
                success = await self.dispatcher.execute(
                    action=action_type,
                    target=member,
                    guild=guild,
                    reason=action_reason,
                    source="antiraid"
                )

                if success and incident_id:
                    # Append user ID to incident log
                    db = Database.get_db()
                    from bson import ObjectId
                    try:
                        await db.antiraid_incidents.update_one(
                            {"_id": ObjectId(incident_id)},
                            {"$addToSet": {"accounts_actioned": member.id}}
                        )
                    except Exception:
                        pass
                        
            elif mode == RaidMode.ALERT:
                # Action single account suspensions (account age / no avatar)
                if "age" in reason:
                    action_type = settings.account_age_action
                else:
                    action_type = settings.no_avatar_action

                if action_type in ["kick", "ban"]:
                    action_reason = f"Anti-Raid Filter Triggered: {reason}"
                    
                    if settings.dm_on_kick and action_type == "kick":
                        try:
                            await member.send(settings.dm_message)
                        except discord.Forbidden:
                            pass

                    await self.dispatcher.execute(
                        action=action_type,
                        target=member,
                        guild=guild,
                        reason=action_reason,
                        source="antiraid"
                    )
                elif action_type == "alert":
                    # Send warning report to log channel
                    await self._send_alert_to_log_channel(guild, member, reason, settings)

    async def _send_alert_to_log_channel(self, guild: discord.Guild, member: discord.Member, reason: str, settings: AntiRaidSettings):
        log_channel_id = settings.log_channel_id
        if not log_channel_id:
            # Fall back to general mod logs channel
            guild_setting = await Database.guild_settings().find_one({"guild_id": guild.id})
            if guild_setting and "log_channel" in guild_setting and guild_setting["log_channel"]:
                log_channel_id = guild_setting["log_channel"].get("mod_log_channel_id")

        if not log_channel_id:
            return

        channel = guild.get_channel(int(log_channel_id))
        if not channel:
            return

        embed = discord.Embed(
            title="⚠️ Anti-Raid Alert: Suspicious Account Joined",
            color=discord.Color.gold(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_author(name=f"{member.name} ({member.id})", icon_url=member.display_avatar.url)
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Warning Reason", value=reason, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    async def lock_guild_channels(self, guild: discord.Guild, lock: bool) -> int:
        """Locks/Unlocks all public channels in the guild. Returns count of channels altered."""
        count = 0
        for channel in guild.channels:
            if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                continue
            
            # Smart check: only lock down public channels (viewable by everyone)
            # Do not touch moderator or staff private channels
            overwrites = channel.overwrites_for(guild.default_role)
            if overwrites.view_channel == False:
                continue

            await self.dispatcher.lockdown_channel(channel, lock)
            count += 1
        return count

    async def deescalate_guild(self, guild: discord.Guild, reason: str) -> int:
        """Resets raid mode, triggers auto-unlock, and updates incident log."""
        await self.engine.set_raid_mode(guild.id, RaidMode.DISABLED)
        
        redis = self.engine._get_redis()
        # Clean up timer keys
        await redis.delete(f"raid:{guild.id}:lockdown_timer")
        
        # Revert verification level if changed
        try:
            await guild.edit(verification_level=discord.VerificationLevel.medium)
        except Exception:
            pass

        # Unlock channels
        unlocked_count = await self.lock_guild_channels(guild, False)
        
        # Log to incident
        incident_id = await redis.get(f"raid:{guild.id}:incident_id")
        if incident_id:
            await AntiRaidService.resolve_incident(incident_id, auto_resolved=True)
            await redis.delete(f"raid:{guild.id}:incident_id")
            
        # Send resolution alert to mod logs
        settings = await AntiRaidService.get_settings(guild.id)
        log_channel_id = settings.log_channel_id
        if not log_channel_id:
            guild_setting = await Database.guild_settings().find_one({"guild_id": guild.id})
            if guild_setting and "log_channel" in guild_setting and guild_setting["log_channel"]:
                log_channel_id = guild_setting["log_channel"].get("mod_log_channel_id")

        if log_channel_id:
            channel = guild.get_channel(int(log_channel_id))
            if channel:
                embed = discord.Embed(
                    title="🟢 Nexa Anti-Raid De-escalation",
                    description=f"Server returned to normal. Channels unlocked. Reason: {reason}",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                try:
                    await channel.send(embed=embed)
                except Exception:
                    pass

        return unlocked_count

    @tasks.loop(seconds=15)
    async def auto_recovery_loop(self):
        """Monitors all guilds and automatically de-escalates lockdowns if their timers expired."""
        for guild in self.bot.guilds:
            try:
                mode = await self.engine.get_raid_mode(guild.id)
                if mode >= RaidMode.LOCKDOWN:
                    # Check if timer has expired in Redis
                    lockdown_active = await self.engine.check_lockdown_active(guild.id)
                    if not lockdown_active:
                        logger.info(f"Auto-recovery triggered for guild {guild.name} ({guild.id})")
                        await self.deescalate_guild(guild, reason="Auto-recovery timer expired")
            except Exception as e:
                logger.error(f"Error checking recovery status for guild {guild.id}: {e}")

    @auto_recovery_loop.before_loop
    async def before_auto_recovery(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(AntiRaidCog(bot))
