from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient

from core.config import settings


class Database:
    _client:AsyncIOMotorClient = None
    _db = None


    @classmethod
    async def connect(cls):
        """Establish connection to database"""
        try:
            cls._client = AsyncIOMotorClient(settings.mongo_connection)
            cls._db = cls._client[settings.database_name]
            # Verify connection
            await cls._client.admin.command("ping")
            logger.info(f"Connected to database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise e


    @classmethod
    async def close(cls):
        """Close connection to database"""
        if cls._client is not None:
            cls._client.close()
            logger.warning(f"Closed connection to database")

    @classmethod
    def get_db(cls):
        """ Get database collection instants"""
        if cls._db is None:
            raise ConnectionError("Database not initialized. Call connect() first")
        return cls._db

    @classmethod
    def guild_settings(cls):
        return cls.get_db().guild_settings

    @classmethod
    def automod_settings(cls):
        return cls.get_db().automod_settings

    @classmethod
    def user_infractions(cls):
        return cls.get_db().user_infractions

    @classmethod
    def economy(cls):
        return cls.get_db().Economy

    @classmethod
    def command_settings(cls):
        return cls.get_db().command_settings

    @classmethod
    def embeds(cls):
        return cls.get_db().emebeds

    @classmethod
    def last_seen(cls):
        return cls.get_db().last_seen

    @classmethod
    def moderation_settings(cls):
        return cls.get_db().moderation_settings

    @classmethod
    def user(cls):
        return cls.get_db().user

    @classmethod
    def moderation_logs(cls):
        return cls.get_db().moderation_logs

    @classmethod
    def antispam_settings(cls):
        return cls.get_db().antispam_settings

    @classmethod
    def antiraid_settings(cls):
        return cls.get_db().antiraid_settings

    @classmethod
    def antispam_logs(cls):
        return cls.get_db().antispam_logs

    @classmethod
    def antiraid_incidents(cls):
        return cls.get_db().antiraid_incidents


