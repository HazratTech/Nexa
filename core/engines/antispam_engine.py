import re
import time
import zlib
from dataclasses import dataclass
from typing import Optional
import discord
from loguru import logger
from core.redis import RedisManager
from core.models.guild_models import AntiSpamSettings

CUSTOM_EMOJI_RE = re.compile(r'<a?:\w+:\d+>')

@dataclass
class SpamVerdict:
    violation_type: str
    reason: str

class AntiSpamEngine:
    def __init__(self):
        pass

    def _get_redis(self):
        return RedisManager.get_client()

    def _count_emojis(self, content: str) -> int:
        if not content:
            return 0
        custom_count = len(CUSTOM_EMOJI_RE.findall(content))
        unicode_count = 0
        for char in content:
            # Common emoji ranges
            o = ord(char)
            if (0x1F300 <= o <= 0x1F9FF or 
                0x2600 <= o <= 0x27BF or 
                0x1F600 <= o <= 0x1F64F or 
                0x1F680 <= o <= 0x1F6FF or 
                0x1F1E0 <= o <= 0x1F1FF or 
                0x1F900 <= o <= 0x1F9FF or 
                0x1F000 <= o <= 0x1F0FF):
                unicode_count += 1
        return custom_count + unicode_count

    async def is_on_cooldown(self, prefix: str) -> bool:
        redis = self._get_redis()
        return await redis.get(f"{prefix}:cooldown") is not None

    async def set_cooldown(self, prefix: str, ttl: int = 5):
        redis = self._get_redis()
        await redis.setex(f"{prefix}:cooldown", ttl, "1")

    async def get_violation_score(self, prefix: str) -> int:
        redis = self._get_redis()
        score = await redis.get(f"{prefix}:score")
        return int(score) if score else 0

    async def increment_violation_score(self, prefix: str, amount: int = 1) -> int:
        redis = self._get_redis()
        score = await redis.incrby(f"{prefix}:score", amount)
        await redis.expire(f"{prefix}:score", 300) # Reset after 5 minutes of good behavior
        return score

    async def reset_violation_score(self, prefix: str):
        redis = self._get_redis()
        await redis.delete(f"{prefix}:score")

    async def process_message(self, message: discord.Message, settings: AntiSpamSettings) -> Optional[SpamVerdict]:
        """
        Process a message through all spam checks.
        Returns a SpamVerdict if spam is detected, or None if clean.
        """
        guild_id = message.guild.id
        user_id = message.author.id
        prefix = f"spam:{guild_id}:{user_id}"

        # 0. Cooldown Check (prevent double-actioning a user who spams multiple lines in a single millisecond)
        if await self.is_on_cooldown(prefix):
            return None

        now = time.time()
        redis = self._get_redis()

        # 1. Message Rate Limit check (Lua script)
        # KEYS[1] = spam:{guild}:{user}:msgs
        # ARGV[1] = timestamp, ARGV[2] = window, ARGV[3] = threshold, ARGV[4] = message_id
        try:
            count = await RedisManager.run_script(
                "antispam_check",
                keys=[f"{prefix}:msgs"],
                args=[str(now), str(settings.message_rate_window), str(settings.message_rate_limit), str(message.id)]
            )
            if count > settings.message_rate_limit:
                return SpamVerdict("rate_limit", f"Sending messages too fast ({count}/{settings.message_rate_limit} in {settings.message_rate_window}s)")
        except Exception as e:
            logger.error(f"Redis Lua script error on message rate check: {e}")

        # 2. Duplicate Content check
        if message.content and len(message.content) > 3:
            content_hash = zlib.crc32(message.content.lower().encode())
            dupe_key = f"{prefix}:dupe:{content_hash}"
            
            pipe = redis.pipeline()
            pipe.zremrangebyscore(dupe_key, "-inf", now - settings.duplicate_window)
            pipe.zadd(dupe_key, {str(message.id): now})
            pipe.zcard(dupe_key)
            pipe.expire(dupe_key, settings.duplicate_window * 2)
            results = await pipe.execute()
            
            dupe_count = results[2]
            if dupe_count > settings.duplicate_threshold:
                return SpamVerdict("duplicate", f"Sending duplicate messages ({dupe_count}/{settings.duplicate_threshold})")

        # 3. Mention Spam check
        if message.mentions or message.role_mentions or message.mention_everyone:
            # Count distinct mentions in this message
            mentions_in_msg = len(message.mentions) + len(message.role_mentions)
            if message.mention_everyone:
                mentions_in_msg += 1

            if mentions_in_msg > settings.max_mentions_per_message:
                return SpamVerdict("mention_spam", f"Too many mentions in a single message ({mentions_in_msg}/{settings.max_mentions_per_message})")

            if mentions_in_msg > 0:
                mention_key = f"{prefix}:mentions"
                pipe = redis.pipeline()
                pipe.zremrangebyscore(mention_key, "-inf", now - settings.mention_window)
                
                # Add each mention as a unique entry to sorted set to aggregate across window
                mapping = {}
                for idx in range(mentions_in_msg):
                    mapping[f"{message.id}:{idx}"] = now
                pipe.zadd(mention_key, mapping)
                pipe.zcard(mention_key)
                pipe.expire(mention_key, settings.mention_window * 2)
                results = await pipe.execute()
                
                mention_total = results[2]
                if mention_total > settings.max_mentions_per_window:
                    return SpamVerdict("mention_spam", f"Too many mentions in time window ({mention_total}/{settings.max_mentions_per_window} in {settings.mention_window}s)")

        # 4. Emoji Spam check
        if message.content:
            emoji_count = self._count_emojis(message.content)
            if emoji_count > settings.max_emojis_per_message:
                return SpamVerdict("emoji_spam", f"Too many emojis ({emoji_count}/{settings.max_emojis_per_message})")

        # 5. Newline / Wall-of-Text check
        if message.content:
            newline_count = message.content.count("\n")
            if newline_count > settings.max_newlines:
                return SpamVerdict("newline_spam", f"Too many newlines ({newline_count}/{settings.max_newlines})")

        # 6. Sticker Spam check
        if message.stickers:
            sticker_key = f"{prefix}:stickers"
            sticker_count = len(message.stickers)
            
            pipe = redis.pipeline()
            pipe.zremrangebyscore(sticker_key, "-inf", now - settings.sticker_window)
            mapping = {}
            for idx in range(sticker_count):
                mapping[f"{message.id}:{idx}"] = now
            pipe.zadd(sticker_key, mapping)
            pipe.zcard(sticker_key)
            pipe.expire(sticker_key, settings.sticker_window * 2)
            results = await pipe.execute()
            
            sticker_total = results[2]
            if sticker_total > settings.max_stickers_per_window:
                return SpamVerdict("sticker_spam", f"Too many stickers ({sticker_total}/{settings.max_stickers_per_window} in {settings.sticker_window}s)")

        # 7. Attachment Spam check
        if message.attachments:
            attachment_key = f"{prefix}:attachments"
            attachment_count = len(message.attachments)
            
            pipe = redis.pipeline()
            pipe.zremrangebyscore(attachment_key, "-inf", now - settings.attachment_window)
            mapping = {}
            for idx in range(attachment_count):
                mapping[f"{message.id}:{idx}"] = now
            pipe.zadd(attachment_key, mapping)
            pipe.zcard(attachment_key)
            pipe.expire(attachment_key, settings.attachment_window * 2)
            results = await pipe.execute()
            
            attachment_total = results[2]
            if attachment_total > settings.max_attachments_per_window:
                return SpamVerdict("attachment_spam", f"Too many attachments ({attachment_total}/{settings.max_attachments_per_window} in {settings.attachment_window}s)")

        return None
