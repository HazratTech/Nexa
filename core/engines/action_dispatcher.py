import asyncio
import datetime
from typing import Optional, Union, List, Dict
import discord
from loguru import logger
from core.redis import RedisManager
from core.database import Database
from core.models.antispam_models import AntiSpamLog
from modules.antispam.services import AntiSpamService
from modules.moderation.services import ModerationService
from modules.guild.services import GuildService

class ActionDispatcher:
    def __init__(self, bot):
        self.bot = bot
        self._semaphore = asyncio.Semaphore(5)  # Max 5 concurrent Discord API calls

    def _get_redis(self):
        return RedisManager.get_client()

    def _can_act_on(self, target: discord.Member, guild: discord.Guild, action_type: str) -> bool:
        """Checks if the bot can moderate the target based on role hierarchy."""
        # Cannot moderate bot itself
        if target.id == guild.me.id:
            return False
            
        # Cannot moderate guild owner
        if target.id == guild.owner_id:
            return False

        # Cannot moderate administrator or higher top role
        if target.guild_permissions.administrator:
            # We still might want to moderate admins if configuration explicitly doesn't bypass them,
            # but standard hierarchy safety says we shouldn't. Let's block bot from doing actions on admins.
            return False

        if target.top_role >= guild.me.top_role:
            logger.warning(f"Hierarchy block: Cannot {action_type} user {target} (equal or higher role than bot).")
            return False

        return True

    async def execute(
        self,
        action: str,
        target: discord.Member,
        guild: discord.Guild,
        reason: str,
        source: str,  # "antispam" or "antiraid"
        duration: int = 300,  # for timeout
        message: Optional[discord.Message] = None,
        violation_score: int = 0,
        violation_type: Optional[str] = None
    ) -> bool:
        """Executes a single moderation action with hierarchy checks, rate-limiting and deduplication."""
        
        # 1. Base check for target member validity
        if not target or not guild:
            return False
            
        # 2. Check if we need deletion (deletion doesn't require role hierarchy checks on target)
        if "delete" in action and message:
            try:
                await message.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                logger.error(f"Missing permissions to delete spam message in {message.channel}")
            except Exception as e:
                logger.error(f"Failed to delete message: {e}")
            
            # If the action is ONLY delete, we can return early
            if action == "delete":
                return True

        # 3. For member actions (timeout, kick, ban), verify hierarchy safety
        member_action = action.replace("delete+", "")
        if member_action not in ["warn", "timeout", "kick", "ban"]:
            return True # If it was just delete, we are done.

        if not self._can_act_on(target, guild, member_action):
            return False

        # 4. Action deduplication using Redis to prevent hammering the same user
        redis = self._get_redis()
        dedup_key = f"action:dedup:{guild.id}:{target.id}:{member_action}"
        if await redis.get(dedup_key):
            # Recently actioned with this type, skip
            return False
        
        # Mark as actioned for 5 seconds
        await redis.setex(dedup_key, 5, "1")

        # 5. Acquire semaphore to respect API rate limits
        async with self._semaphore:
            success = await self._perform_member_action(
                action=member_action,
                target=target,
                guild=guild,
                reason=reason,
                duration=duration,
                source=source,
                violation_score=violation_score,
                violation_type=violation_type,
                channel_id=message.channel.id if message else 0
            )
            return success

    async def _perform_member_action(
        self,
        action: str,
        target: discord.Member,
        guild: discord.Guild,
        reason: str,
        duration: int,
        source: str,
        violation_score: int,
        violation_type: Optional[str],
        channel_id: int
    ) -> bool:
        try:
            mod_reason = f"[{source.upper()}] {reason}"

            if action == "warn":
                try:
                    embed = discord.Embed(
                        title=f"⚠️ Warning from {guild.name}",
                        description=f"You have been warned for: **{reason}**",
                        color=discord.Color.gold(),
                        timestamp=datetime.datetime.now(datetime.timezone.utc)
                    )
                    await target.send(embed=embed)
                except discord.Forbidden:
                    pass # User has DMs closed
                
                # Warn does not have a native discord API action other than tracking, 
                # but we log it and send message. We also increment warnings in our DB.
                await ModerationService.record_moderation_logs(
                    guild_id=guild.id,
                    offender_id=target.id,
                    moderator_id=guild.me.id,
                    action_type="Warn",
                    reason=mod_reason
                )

            elif action == "timeout":
                timeout_until = discord.utils.utcnow() + datetime.timedelta(seconds=duration)
                await target.timeout(timeout_until, reason=mod_reason)
                await ModerationService.record_moderation_logs(
                    guild_id=guild.id,
                    offender_id=target.id,
                    moderator_id=guild.me.id,
                    action_type="Timeout",
                    reason=mod_reason
                )

            elif action == "kick":
                try:
                    embed = discord.Embed(
                        title=f"👢 Kicked from {guild.name}",
                        description=f"You have been kicked for: **{reason}**",
                        color=discord.Color.orange(),
                        timestamp=datetime.datetime.now(datetime.timezone.utc)
                    )
                    await target.send(embed=embed)
                except discord.Forbidden:
                    pass
                await target.kick(reason=mod_reason)
                await ModerationService.record_moderation_logs(
                    guild_id=guild.id,
                    offender_id=target.id,
                    moderator_id=guild.me.id,
                    action_type="Kick",
                    reason=mod_reason
                )

            elif action == "ban":
                try:
                    embed = discord.Embed(
                        title=f"🔨 Banned from {guild.name}",
                        description=f"You have been banned for: **{reason}**",
                        color=discord.Color.red(),
                        timestamp=datetime.datetime.now(datetime.timezone.utc)
                    )
                    await target.send(embed=embed)
                except discord.Forbidden:
                    pass
                await target.ban(reason=mod_reason, delete_message_seconds=86400)
                await ModerationService.record_moderation_logs(
                    guild_id=guild.id,
                    offender_id=target.id,
                    moderator_id=guild.me.id,
                    action_type="Ban",
                    reason=mod_reason
                )
            
            # Send alert to the mod log channel
            asyncio.create_task(self.send_mod_channel_log(
                guild=guild,
                action=action.capitalize(),
                target=target,
                reason=reason,
                source=source
            ))

            # Persistent MongoDB Log if antispam
            if source == "antispam":
                log_model = AntiSpamLog(
                    guild_id=guild.id,
                    user_id=target.id,
                    violation_type=violation_type or "unknown",
                    action_taken=action,
                    reason=reason,
                    channel_id=channel_id,
                    violation_score=violation_score
                )
                await AntiSpamService.log_action(log_model)

            return True

        except discord.Forbidden:
            logger.error(f"Discord Forbidden error performing {action} on {target} in {guild.name}.")
            return False
        except Exception as e:
            logger.error(f"Error performing {action} on {target}: {e}")
            return False

    async def execute_bulk(self, actions: List[Dict]) -> List[bool]:
        """Execute multiple actions concurrently respecting semaphore limit."""
        tasks = []
        for act in actions:
            tasks.append(self.execute(
                action=act["action"],
                target=act["target"],
                guild=act["guild"],
                reason=act["reason"],
                source=act["source"],
                duration=act.get("duration", 300),
                message=act.get("message"),
                violation_score=act.get("violation_score", 0),
                violation_type=act.get("violation_type")
            ))
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def send_mod_channel_log(
        self,
        guild: discord.Guild,
        action: str,
        target: discord.Member,
        reason: str,
        source: str
    ):
        """Sends a beautiful moderation alert to the guild's configured mod log channel."""
        guild_setting = await GuildService.get_guild_setting(guild_id=guild.id)
        if not guild_setting or not guild_setting.log_channel:
            return
        
        mod_log_channel_id = guild_setting.log_channel.mod_log_channel_id
        if not mod_log_channel_id:
            return

        channel = guild.get_channel(mod_log_channel_id)
        if not channel:
            return

        color_map = {
            "Warn": discord.Color.gold(),
            "Timeout": discord.Color.orange(),
            "Kick": discord.Color.red(),
            "Ban": discord.Color.purple()
        }

        embed = discord.Embed(
            title=f"🛡️ Nexa Security Alert: {action}",
            color=color_map.get(action, discord.Color.red()),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_author(name=f"{target.name} ({target.id})", icon_url=target.display_avatar.url)
        embed.add_field(name="User", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Detector", value=f"Nexa {source.capitalize()} Engine", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Nexa Protection System")

        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send mod channel log: {e}")

    async def lockdown_channel(self, channel: Union[discord.TextChannel, discord.VoiceChannel, discord.Thread], lock: bool):
        """Overwrites send_messages / connect permissions for the default role to lock/unlock a channel."""
        guild = channel.guild
        default_role = guild.default_role
        
        overwrites = channel.overwrites_for(default_role)
        if lock:
            if isinstance(channel, discord.TextChannel):
                overwrites.send_messages = False
                overwrites.add_reactions = False
                overwrites.create_public_threads = False
                overwrites.create_private_threads = False
            elif isinstance(channel, discord.VoiceChannel):
                overwrites.connect = False
                overwrites.speak = False
        else:
            if isinstance(channel, discord.TextChannel):
                overwrites.send_messages = None
                overwrites.add_reactions = None
                overwrites.create_public_threads = None
                overwrites.create_private_threads = None
            elif isinstance(channel, discord.VoiceChannel):
                overwrites.connect = None
                overwrites.speak = None
                
        try:
            await channel.set_permissions(default_role, overwrite=overwrites, reason="Nexa Anti-Raid Action")
        except discord.Forbidden:
            logger.error(f"Missing permissions to manage permissions on channel {channel.name}.")
        except Exception as e:
            logger.error(f"Failed to lockdown channel {channel.name}: {e}")
