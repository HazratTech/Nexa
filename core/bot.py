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
        self.scheduler.shutdown()
        await RedisManager.close()
        await Database.close()
        await super().close()