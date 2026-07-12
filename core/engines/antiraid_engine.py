import datetime
import time
from enum import IntEnum
from typing import Tuple, Optional

import discord
from loguru import logger

from core.models.antispam_models import AntiRaidIncident
from core.models.guild_models import AntiRaidSettings
from core.redis import RedisManager
from modules.antiraid.services import AntiRaidService


class RaidMode(IntEnum):
    DISABLED = 0
    ALERT = 1
    LOCKDOWN = 2
    PANIC = 3

class AntiRaidEngine:
    def __init__(self, bot):
        self.bot = bot

    def _get_redis(self):
        return RedisManager.get_client()

    async def get_raid_mode(self, guild_id: int) -> RaidMode:
        redis = self._get_redis()
        mode_val = await redis.get(f"raid:{guild_id}:mode")
        if mode_val:
            try:
                return RaidMode(int(mode_val))
            except ValueError:
                return RaidMode.DISABLED
        return RaidMode.DISABLED

    async def set_raid_mode(self, guild_id: int, mode: RaidMode):
        redis = self._get_redis()
        await redis.set(f"raid:{guild_id}:mode", str(mode.value))

    async def extend_lockdown_timer(self, guild_id: int, duration: int):
        redis = self._get_redis()
        await redis.setex(f"raid:{guild_id}:lockdown_timer", duration, "1")

    async def check_lockdown_active(self, guild_id: int) -> bool:
        redis = self._get_redis()
        return await redis.exists(f"raid:{guild_id}:lockdown_timer") > 0

    async def process_join(self, member: discord.Member, settings: AntiRaidSettings) -> Tuple[bool, RaidMode, Optional[str]]:
        """
        Processes a member join event.
        Returns (is_raid, current_raid_mode, trigger_reason).
        """
        guild_id = member.guild.id
        now = time.time()
        redis = self._get_redis()

        # 1. Check current raid mode
        current_mode = await self.get_raid_mode(guild_id)

        # 2. Check Join Flood (Lua Script)
        # KEYS[1] = raid:{guild}:joins, KEYS[2] = raid:{guild}:mode
        # ARGV[1] = timestamp, ARGV[2] = window, ARGV[3] = threshold, ARGV[4] = user_id
        join_count = 0
        escalated = 0
        try:
            results = await RedisManager.run_script(
                "antiraid_join",
                keys=[f"raid:{guild_id}:joins", f"raid:{guild_id}:mode"],
                args=[str(now), str(settings.join_rate_window), str(settings.join_rate_limit), str(member.id)]
            )
            join_count, returned_mode, escalated = results
            current_mode = RaidMode(returned_mode)
        except Exception as e:
            logger.error(f"Redis Lua script error on join flood check: {e}")

        # 3. If join flood escalated, record incident and set lockdown timer
        if escalated == 1:
            # Set timer for lockdown auto-recovery
            await self.extend_lockdown_timer(guild_id, settings.raid_lockdown_duration)
            
            # Re-read mode just to be safe
            current_mode = RaidMode.LOCKDOWN
            
            # Log to MongoDB
            incident = AntiRaidIncident(
                guild_id=guild_id,
                raid_level=int(current_mode),
                trigger_type="join_flood",
                join_count=join_count,
                window_seconds=settings.join_rate_window,
                actions_taken=["Escalated server to Lockdown mode"]
            )
            incident_id = await AntiRaidService.log_incident(incident)
            # Cache the incident ID in Redis to resolve it on de-escalation
            await redis.set(f"raid:{guild_id}:incident_id", incident_id)

            return True, current_mode, f"Join flood detected: {join_count} joins in {settings.join_rate_window}s"

        # 4. If raid is active (Lockdown or Panic), any new user triggers action
        if current_mode >= RaidMode.LOCKDOWN:
            # Keep extending the lockdown timer while users continue joining during raid
            await self.extend_lockdown_timer(guild_id, settings.raid_lockdown_duration)
            return True, current_mode, f"Joined during active raid (Mode: {current_mode.name})"

        # 5. Account Age filter
        account_age = datetime.datetime.now(datetime.timezone.utc) - member.created_at
        if account_age.days < settings.min_account_age_days:
            return True, RaidMode.ALERT, f"Suspicious account age: {account_age.days} days old (Threshold: {settings.min_account_age_days}d)"

        # 6. No-Avatar filter
        if not member.avatar:
            return True, RaidMode.ALERT, "Suspicious account: No custom profile avatar"

        return False, RaidMode.DISABLED, None
