import discord
from discord import app_commands
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorCollection

from core.database import Database
from modules.guild.services import GuildService


class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_collection: AsyncIOMotorCollection = Database.guild_settings()

    async def load_log_channels(self, guild_id: int) -> int | None:
        guild_data = await GuildService.get_guild_setting(guild_id=guild_id)
        if not guild_data:
            return None
        log_channel_id = guild_data.log_channel.mod_log_channel_id
        if not log_channel_id:
            return None
        return log_channel_id

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        before_roles = set(before.roles)
        after_roles = set(after.roles)

        added_roles = after_roles - before_roles
        removed_roles = before_roles - after_roles

        if added_roles or removed_roles:
            await self.log_role_changes(before=before, after=after, added_roles=added_roles,
                                        removed_roles=removed_roles)

        if before.nick != after.nick:
            await self.log_nickname_chane(before, after)

    async def log_role_changes(self, before: discord.Member, after: discord.Member, added_roles, removed_roles):
        log_channel_id = await self.load_log_channels(after.guild.id)
        if not log_channel_id:
            print(f'Log channel with ID {log_channel_id} not found.')
            return
        log_channel = self.bot.get_channel(log_channel_id)

        embed = discord.Embed(
            title="Role Changes",
            color=0x00FFFF,
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=after.name, icon_url=after.avatar.url)
        embed.set_footer(text=f"User ID: {after.id}")

        if added_roles:
            embed.add_field(
                name="Roles Added",
                value="\n".join([role.mention for role in added_roles]),
                inline=False
            )
        if removed_roles:
            embed.add_field(
                name="Roles Removed",
                value="\n".join([role.mention for role in removed_roles]),
                inline=False
            )

        await log_channel.send(embed=embed)

    async def log_nickname_chane(self, before: discord.Member, after: discord.Member):
        log_channel_id = await self.load_log_channels(after.guild.id)
        log_channel = self.bot.get_channel(log_channel_id)

        if not log_channel:
            print(f"Log channel with ID {log_channel_id} not found.")
            return

        embed = discord.Embed(title="Nickname Changes", description=None, color=0x00FFFF,
                              timestamp=discord.utils.utcnow())
        embed.set_author(name=after.name, icon_url=after.avatar.url)
        embed.add_field(name="Before", value=before.nick if before.nick else before.name, inline=False)
        embed.add_field(name="After", value=after.nick if after.nick else after.name, inline=False)
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        log_channel_id = await self.load_log_channels(guild.id)
        log_channel = self.bot.get_channel(log_channel_id)

        if not log_channel:
            print(f'Log channel with ID {log_channel_id} not found.')
            return

        embed = discord.Embed(
            title="Member Banned",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=user.name, icon_url=user.avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")

        embed.add_field(
            name="User",
            value=f"{user.name}#{user.discriminator}",
            inline=True
        )

        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        guild_id = guild.id
        log_channel_id = await self.load_log_channels(guild_id)
        if log_channel_id:
            log_channel = self.bot.get_channel(log_channel_id)

            if not log_channel:
                print(f'Log channel with ID {log_channel_id} not found.')
                return

            embed = discord.Embed(
                title="Member Unbanned",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=user.name, icon_url=user.avatar.url)
            embed.set_footer(text=f"User ID: {user.id}")

            embed.add_field(
                name="User",
                value=f"{user.name}#{user.discriminator}",
                inline=True
            )

            await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild_id = member.guild.id
        log_channel_id = await self.load_log_channels(guild_id)
        if log_channel_id:
            log_channel = member.guild.get_channel(log_channel_id)

            if not log_channel:
                print(f'Log channel with ID {log_channel_id} not found.')
                return

            if isinstance(member, discord.Member):
                action = "kicked"
            elif isinstance(member, discord.User):
                action = "left"
            else:
                action = "removed"

            embed = discord.Embed(
                title=f"{member} was {action}",
                color=0x00FFFF,
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"User ID: {member.id}")

            await log_channel.send(embed=embed)

    log = app_commands.Group(
        name="log",
        description="Set log channels",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )

    @log.command(name="mod", description="Set log channel mod actions")
    async def mod_logs(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        await interaction.response.defer(ephemeral=True)
        if not channel:
            channel = interaction.channel
        await GuildService.update_guild_settings(
            guild_id=interaction.guild_id,
            **{"log_channel.mod_log_channel_id": channel.id}
        )
        await interaction.followup.send(f"Log channel set to {channel}")

    @log.command(name="message", description="Set log channel message actions")
    async def message_logs(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        await interaction.response.defer(ephemeral=True)
        if not channel:
            channel = interaction.channel
        await GuildService.update_guild_settings(
            guild_id=interaction.guild_id,
            **{"log_channel.message_log_channel_id": channel.id}
        )
        await interaction.followup.send(f"Message log channel set to {channel}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
