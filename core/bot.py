import os

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands
from discord.ext.commands import AutoShardedBot
from loguru import logger

from core.database import Database
from core.redis import RedisManager


class NexaBot(AutoShardedBot):
    def __init__(self):
        intents =  discord.Intents.all()
        super().__init__(
            command_prefix="n!",
            help_command=None,
            intents= intents,
            owner_id=475357995367137282
        )

        self.scheduler = AsyncIOScheduler()


    async def setup_hook(self) -> None:
        """Called when the bot has successfully been initialized."""

        ## Connect to Database
        await Database.connect()
        await RedisManager.connect()

        ## Load Modules
        await self.load_modules()

        ## Sync commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

        # Start background command settings database synchronization
        self.loop.create_task(self.startup_commands_sync())


    async def load_modules(self) -> None:
        """
        Recursively load modules.
        Load core directory extensions if any (e.g., global listeners)
        Load 'module' directory
        """
        if os.path.exists("modules"):
            for root, dirs, files in os.walk("modules"):
                for file in files:
                    if file.endswith(".py") and not file.startswith("_"):
                        """Skip common non-existing files"""
                        if file in ["models.py", "services.py", "ui.py", "__init__.py"]:
                            continue

                        """ Construct module path: modules.category.cog"""
                        rel_path = os.path.relpath(os.path.join(root, file), "")
                        modules_name = rel_path.replace(os.path.sep, ".")[:-3]

                        try:
                            await self.load_extension(modules_name)
                            logger.info(f"Loaded {modules_name}")
                        except commands.NoEntryPointError:
                            pass
                        except Exception as e:
                            logger.error(f"Failed to load {modules_name}: {e}")


    async def on_ready(self):
        logger.info(f"Logged in as {self.user}")

        await self.change_presence(
            activity=discord.Game(name="Moderating Code Circle")
        )

        if not self.scheduler.running:
            self.scheduler.start()


    async def close(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
        await RedisManager.close()
        await Database.close()
        await super().close()

    async def startup_commands_sync(self) -> None:
        await self.wait_until_ready()
        logger.info("Bot is ready. Starting command settings database synchronization...")
        for guild in self.guilds:
            await self.sync_guild_commands(guild.id)

    async def on_guild_join(self, guild: discord.Guild):
        logger.info(f"Joined guild {guild.name} ({guild.id}). Syncing command tree...")
        await self.sync_guild_commands(guild.id)

    async def sync_guild_commands(self, guild_id: int) -> None:
        import yaml
        if not os.path.exists("commands.yaml"):
            logger.warning("commands.yaml not found, skipping command database synchronization.")
            return
        try:
            with open("commands.yaml", "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            categories = config.get("categories", [])
            db = Database.get_db()
            command_collection = db.command_settings

            for cat in categories:
                cat_name = cat.get("name")
                for cmd in cat.get("commands", []):
                    cmd_name = cmd.get("name").lstrip("/")
                    exists = await command_collection.find_one({
                        "guild_id": str(guild_id),
                        "command": cmd_name
                    })
                    
                    cmd_payload = {
                        "description": cmd.get("description", ""),
                        "category": cat_name,
                        "aliases": cmd.get("aliases", []),
                        "usage": cmd.get("usage", ""),
                        "output": cmd.get("output", ""),
                        "args": cmd.get("args", []),
                        "permissions_level": cmd.get("permissions", "everyone")
                    }

                    if exists:
                        await command_collection.update_one(
                            {"_id": exists["_id"]},
                            {"$set": cmd_payload}
                        )
                    else:
                        await command_collection.insert_one({
                            "guild_id": str(guild_id),
                            "command": cmd_name,
                            "is_premium": False,
                            "enabled": True,
                            "enabled_roles": [],
                            "disabled_roles": [],
                            "enabled_channels": [],
                            "disabled_channels": [],
                            "roles_skip_limit": [],
                            "settings": {
                                "max_limit": 4,
                                "auto_delete_invocation": False,
                                "auto_delete_response": False,
                                "auto_delete_with_invocation": False,
                                "response_delete_delay": 5
                            },
                            **cmd_payload
                        })
            logger.info(f"Command database synchronization completed for guild {guild_id}")
        except Exception as e:
            logger.error(f"Failed to sync commands for guild {guild_id}: {e}")