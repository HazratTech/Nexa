import asyncio
from typing import List, Optional, Union

import discord
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorCollection
from typing_extensions import Literal

from core.database import Database
from core.models.guild_models import ModerationSettings
from modules.error.custom_errors import GenericError
from modules.guild.services import GuildService
from modules.moderation.model import ModerationLogModel
from modules.user.user_service import UserService


class ModerationService:

    @classmethod
    def get_moderation_settings_collection(cls) -> AsyncIOMotorCollection:
        return Database.moderation_settings()

    @classmethod
    def get_moderation_logs_collection(cls) -> AsyncIOMotorCollection:
        return Database.moderation_logs()

    @classmethod
    async def get_mod_settings(cls, guild_id: int) -> ModerationSettings:
        mod_collection = cls.get_moderation_settings_collection()
        data = await mod_collection.find_one({"guild_id": guild_id})
        if data:
            return ModerationSettings(**data)

        # Create default
        new_settings = ModerationSettings(guild_id=guild_id)
        await mod_collection.insert_one(new_settings.model_dump())
        return new_settings

    @classmethod
    async def send_logs(
            cls,
            guild: discord.Guild,
            action: Literal["Kick", "Ban", "Mute", "UnMute", "Timeout", "Remove Timeout", "Unban", "Warn"],
            moderator: discord.Member,
            target: Union[discord.Member, discord.User],
            reason: str = None,
    ):
        guild_setting = await GuildService.get_guild_setting(guild_id=guild.id)
        if not guild_setting:
            return
        mod_log_channel_id = guild_setting.log_channel.mod_log_channel_id if guild_setting.log_channel else None
        if not mod_log_channel_id:
            return

        channel = guild.get_channel(mod_log_channel_id)
        if not channel:
            return

        color_map = {
            "Kick": discord.Color.from_str("#F59E0B"),  # Amber
            "Ban": discord.Color.from_str("#DC2626"),  # Red
            "Warn": discord.Color.from_str("#FACC15"),  # Yellow
            "Mute": discord.Color.from_str("#6366F1"),  # Indigo
            "UnMute": discord.Color.from_str("#22C55E"),  # Green
            "Timeout": discord.Color.from_str("#3B82F6"),  # Blue
            "Remove Timeout": discord.Color.from_str("#10B981"),  # Emerald
            "Unban": discord.Color.from_str("#22C55E"),  # Green
        }

        embed = discord.Embed(
            title=f"🔨 {action}",
            color=color_map.get(action, discord.Color.orange()),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided.", inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)

        await channel.send(embed=embed)

    @classmethod
    async def get_or_create_mute_role(cls, guild: discord.Guild) -> discord.Role:
        """
        Get Mute role by guild
        """
        try:
            guild_setting = await GuildService.get_guild_setting(guild_id=guild.id)
            if not guild_setting:
                logger.error(f"Failed to get guild setting for mute role create or get")
                raise GenericError("Server data not found")

            ## Check role id in guild collection
            mute_role_id = guild_setting.roles.mute_role_id if guild_setting.roles else None
            if not mute_role_id:
                permissions = discord.Permissions(view_channel=False, send_messages=False)
                role = await GuildService.create_role(guild=guild, role_name="Mute", permission=permissions)
                guild_collection = GuildService.get_guild_collection()

                update = await guild_collection.update_one(
                    {"guild_id": guild.id},
                    {"$set": {"roles.mute_role_id": role.id}},
                    upsert=True
                )
                if update.modified_count > 0:
                    task = asyncio.create_task(cls.apply_mute_role_to_channels(mute_role=role, guild=guild))

                    def on_done(task: asyncio.Task):
                        if task.exception():
                            logger.error(f"Failed to apply mute role in channel after mute role create")

                    task.add_done_callback(on_done)
                    return role
                else:
                    raise GenericError(f"Failed to create role {role.name}")

            mute_role = guild.get_role(mute_role_id)
            if not mute_role:
                raise GenericError(f"Failed to create role {mute_role_id}")
            return mute_role
        except discord.Forbidden:
            logger.error(f"Failed to create role")
            raise GenericError(f"I do not have permission to create role")
        except Exception as e:
            logger.error(f"Failed to create role {e}")
            raise GenericError(f"Failed to create role {e}")

    @classmethod
    async def save_member_role(cls, member: discord.Member, guild_id: int, roles: List[discord.Role]) -> bool:
        if not roles:
            return False

        role_ids = [role.id for role in roles]
        user_collection: AsyncIOMotorCollection = Database.user()

        result = await user_collection.update_one(
            {"user_id": member.id, "guild_id": guild_id},
            {
                "$setOnInsert": {"user_id": member.id, "guild_id": guild_id},
                "$addToSet": {"roles": {"$each": role_ids}}
            },
            upsert=True
        )
        return result.modified_count > 0 or result.upserted_id is not None

    @classmethod
    async def get_user_roles_from_database(cls, user_id: int, guild: discord.Guild) -> Optional[List[discord.Role]]:
        """
        Get user roles from database
        """
        user_doc = await UserService.get_user_data(user_id=user_id, guild_id=guild.id)
        if not user_doc:
            return None
        roles_id = user_doc.roles or []

        roles = [
            role for role_id in roles_id
            if (role := guild.get_role(role_id)) is not None
        ]
        return roles

    @classmethod
    async def apply_mute_role_to_channels(cls, mute_role: discord.Role, guild: discord.Guild):
        """
        Apply mute role to channels
        """
        permissions = discord.PermissionOverwrite(
            view_channel=False,
            send_messages=False,
            speak=False,
            connect=False,
            create_public_threads=False,
            send_messages_in_threads=False,
            add_reactions=False,
        )

        appeal_channel = discord.utils.get(guild.text_channels, name="appeal")
        if not appeal_channel:
            try:
                appeal_channel = await GuildService.create_channel(
                    guild=guild,
                    channel_name="appeal",
                    channel_type="text",
                    overwrites={
                        mute_role: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                               read_message_history=True),
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True),
                    },
                    reason=f"For mute role support"
                )
            except Exception as e:
                logger.error(f"Failed to apply mute role to channels: {e}")
                appeal_channel = None

        failed = []
        for channel in guild.channels:
            if appeal_channel and channel.id == appeal_channel.id:
                continue
            try:
                await channel.set_permissions(mute_role, overwrite=permissions)
            except discord.Forbidden:
                failed.append(channel.name)
            except Exception as e:
                logger.error(f"Failed to set permission for the channel {channel.name}: {e}")
                failed.append(channel.name)
        if failed:
            logger.warning(f"Failed to apply mute role to channels {', '.join(failed)}")

    @classmethod
    async def apply_mute_role_to_single_channel(
            cls,
            guild: discord.Guild,
            channel: discord.abc.GuildChannel,
    ):
        """Apply mute role to single channel"""

        if channel.name.lower() == "appeal":
            return

        mod_settings = await ModerationService.get_mod_settings(guild_id=guild.id)
        if not mod_settings:
            logger.warning("Moderation collection is not found")
            return
        if not not mod_settings.is_moderation_settings_enabled:
            logger.warning("Moderation settings disabled or missing")
            return

        guild_settings = await GuildService.get_guild_setting(guild_id=guild.id)
        if not guild_settings or not guild_settings.roles:
            logger.warning("Guild settings or roles missing")
            return

        mute_role_id = guild_settings.roles.mute_role_id
        if not mute_role_id:
            return

        mute_role = guild.get_role(mute_role_id)
        if not mute_role:
            logger.warning("Mute role not found")
            return

        permissions = discord.PermissionOverwrite(
            view_channel=False,  # important fix
            send_messages=False,
            speak=False,
            connect=False,
            create_public_threads=False,
            create_private_threads=False,
            send_messages_in_threads=False,
            add_reactions=False,
        )

        try:
            await channel.set_permissions(mute_role, overwrite=permissions)
        except discord.Forbidden:
            logger.error("Missing permissions to set channel permissions")
        except Exception as e:
            logger.error(f"Failed to apply mute role: {e}")

    @classmethod
    async def record_moderation_logs(
            cls,
            guild_id: int,
            offender_id: int,
            moderator_id: int,
            action_type: Literal['Kick', 'Timeout', 'Warn', 'Mute', 'Ban'],
            reason: Optional[str] = None
    ):
        """
        Record moderation logs
        """

        collection = cls.get_moderation_logs_collection()
        if collection is None:
            return

        moderation_logs = ModerationLogModel(
            guild_id=guild_id,
            offender_id=offender_id,
            action_type=action_type,
            moderator_id=moderator_id,
            reason=reason
        )
        await collection.insert_one(moderation_logs.to_mongo())


    @classmethod
    async def get_offense_count(
            cls,
            guild_id: int,
            offender_id: int,
            action_type: Literal['Kick', 'Timeout', 'Warn', 'Mute', 'Ban']
    ):
        """
        Get moderation logs for an offender
        """
        try:
            collection = cls.get_moderation_logs_collection()
            if collection is None:
                return None
            count = await collection.count_documents(
                {
                    "guild_id": guild_id,
                    "offender_id": offender_id,
                    "action_type": action_type,
                    "resolved": False  # ✅ only active offenses
                }
            )
            return count
        except Exception as e:
            logger.error(f"Failed to get moderation logs for offender: {e}")
            return None

    @classmethod
    async def resolve_offense_logs(
            cls,
            guild_id: int,
            offender_id: int,
            action_type: Literal['Kick', 'Timeout', 'Warn', 'Mute', 'Ban']
    ) -> int:
        """
        Mark moderation logs as resolved after punishment
        """

        try:
            collection = cls.get_moderation_logs_collection()
            if collection is None:
                return 0

            result = await collection.update_many(
                {
                    "guild_id": guild_id,
                    "offender_id": offender_id,
                    "action_type": action_type,
                    "resolved": False
                },
                {
                    "$set": {"resolved": True}
                }
            )

            return result.modified_count  # ✅ useful

        except Exception as e:
            logger.error(f"Failed to resolve moderation logs: {e}")
            return 0

    @classmethod
    async def get_offense_logs(
            cls,
            guild_id: int,
            offender_id: int
    ) -> Optional[List[ModerationLogModel]]:
        try:
            collection = cls.get_moderation_logs_collection()

            if collection is None:
                return None

            moderation_logs = await collection.find(
                {
                    "guild_id": guild_id,
                    "offender_id": offender_id,
                    "action_type": "Warn",
                    "resolved": False
                }
            ).to_list(None)

            if not moderation_logs:
                return None

            return [ ModerationLogModel(**logs) for logs in moderation_logs]
        except Exception as e:
            logger.error(f"Failed to get moderation logs: {e}")



