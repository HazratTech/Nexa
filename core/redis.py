import redis.asyncio as aioredis
from loguru import logger
from core.config import settings

LUA_ANTISPAM_CHECK = """
-- Remove expired entries
local cutoff = tonumber(ARGV[1]) - tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff)

-- Count current entries
local count = redis.call('ZCARD', KEYS[1])

-- Add new entry
redis.call('ZADD', KEYS[1], tonumber(ARGV[1]), ARGV[4])
redis.call('EXPIRE', KEYS[1], math.ceil(tonumber(ARGV[2]) * 2))

-- Return count
return count + 1
"""

LUA_ANTIRAID_JOIN = """
-- KEYS[1] = raid:{guild}:joins
-- KEYS[2] = raid:{guild}:mode
-- ARGV[1] = timestamp
-- ARGV[2] = window
-- ARGV[3] = threshold
-- ARGV[4] = user_id

-- Prune old joins
local cutoff = tonumber(ARGV[1]) - tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff)

-- Add this join
redis.call('ZADD', KEYS[1], tonumber(ARGV[1]), ARGV[4])
redis.call('EXPIRE', KEYS[1], math.ceil(tonumber(ARGV[2]) * 2))

-- Count joins in window
local count = redis.call('ZCARD', KEYS[1])

-- Check if raid mode should escalate
local current_mode = tonumber(redis.call('GET', KEYS[2]) or '0')

if count >= tonumber(ARGV[3]) and current_mode < 2 then
    redis.call('SET', KEYS[2], '2')  -- LOCKDOWN
    return {count, 2, 1}  -- {join_count, new_mode, escalated}
end

return {count, current_mode, 0}  -- {join_count, current_mode, not_escalated}
"""


class RedisManager:
    _pool: aioredis.ConnectionPool = None
    _client: aioredis.Redis = None
    _scripts: dict[str, str] = {}

    @classmethod
    async def connect(cls):
        """Establish Redis connection pool."""
        try:
            cls._pool = aioredis.ConnectionPool.from_url(
                settings.redis_url,
                max_connections=20,
                decode_responses=True,
            )
            cls._client = aioredis.Redis(connection_pool=cls._pool)
            await cls._client.ping()
            logger.info("Connected to Redis successfully.")
            
            # Pre-load Lua scripts
            await cls._load_scripts()
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise e

    @classmethod
    async def close(cls):
        """Close Redis connection pool."""
        if cls._client:
            await cls._client.aclose()
        if cls._pool:
            await cls._pool.disconnect()
            logger.warning("Closed Redis connection.")

    @classmethod
    def get_client(cls) -> aioredis.Redis:
        """Get the active Redis client."""
        if cls._client is None:
            raise ConnectionError("Redis not initialized. Call connect() first.")
        return cls._client

    @classmethod
    async def _load_scripts(cls):
        """Pre-register Lua scripts for atomic operations."""
        scripts = {
            "antispam_check": LUA_ANTISPAM_CHECK,
            "antiraid_join": LUA_ANTIRAID_JOIN,
        }
        for name, src in scripts.items():
            cls._scripts[name] = await cls._client.script_load(src)
            logger.info(f"Loaded Redis Lua script: {name}")

    @classmethod
    async def run_script(cls, name: str, keys: list, args: list):
        """Execute a loaded Lua script by its name."""
        if name not in cls._scripts:
            raise ValueError(f"Script '{name}' is not loaded.")
        client = cls.get_client()
        return await client.evalsha(cls._scripts[name], len(keys), *keys, *args)
