import asyncio
from typing import List, Optional
import discord
from discord.ui import Select, Button
from loguru import logger
from core.constant import Color
from core.database import Database
from modules.guild.services import GuildService
from modules.moderation.model import ModerationLogModel
from modules.moderation.services import ModerationService


async def warning_embed(
        guild: discord.Guild,
        warning_logs: List[ModerationLogModel],
        offender: discord.Member
) -> discord.Embed:
    if warning_logs is None:
        color = discord.Color.from_str(Color.PRIMARY_COLOR)
        warning_embed = discord.Embed(
            color=color,
            timestamp=discord.utils.utcnow(),
            description="🕯️ The scroll remains clean. No warnings have been written.",
        )
    else:
        warning_embed = discord.Embed(
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
            type="rich"
        )
        warning_embed.set_author(
            name=f"{len(warning_logs)} Warnings for {offender.name}({offender.id})",
            icon_url=offender.avatar.url if offender.avatar else None
        )

        for log in warning_logs:
            moderator = guild.get_member(log.moderator_id)
            mod_name = moderator.name if moderator else f"ID: {log.moderator_id}"
            warning_embed.add_field(
                name=f"Moderator: {mod_name}",
                value=f"{log.reason if log.reason is not None else ''} - <t:{int(log.created_at.timestamp())}:R>",
                inline=False
            )
    return warning_embed


class DeleteWarningsLogsUi(discord.ui.View):
    def __init__(self, offender: discord.Member, logs: List[ModerationLogModel]) -> None:
        super().__init__(timeout=300)
        self.offender = offender
        self.logs = logs

        self.delete_warnings_button = discord.ui.Button(
            label="Delete Warnings",
            style=discord.ButtonStyle.danger,
            custom_id="delete_warnings",
            emoji="🗑️"
        )
        self.delete_warnings_button.callback = self.delete_warnings
        if self.logs:
            self.add_item(self.delete_warnings_button)

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.clear_items()

        logs = await ModerationService.get_offense_logs(
            guild_id=interaction.guild.id,
            offender_id=self.offender.id
        )

        embed = await warning_embed(
            guild=interaction.guild,
            warning_logs= logs ,
            offender=self.offender
        )

        if logs:
            self.add_item(self.delete_warnings_button)

        if interaction:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)

    async def delete_warnings(self, interaction: discord.Interaction) -> None:
        resolved = await ModerationService.resolve_offense_logs(
            guild_id= interaction.guild.id,
            offender_id= self.offender.id,
            action_type="Warn"
        )
        if resolved > 0:
            self.delete_warnings_button.disabled = True

        try:
            message = f"The past is buried… but not forgotten. Walk carefully in {interaction.guild.name} from here on."
            await self.offender.send(message)
        except discord.Forbidden:
            pass

        await self.refresh(interaction= interaction)


class ModerationDashboardView(discord.ui.LayoutView):
    def __init__(self, guild_id: int):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.selected_category: Optional[str] = None

    async def initialize(self):
        settings = await ModerationService.get_mod_settings(guild_id=self.guild_id)
        guild_settings = await GuildService.get_guild_setting(guild_id=self.guild_id)
        await self._rebuild(settings, guild_settings)

    async def _rebuild(self, settings, guild_settings):
        self.clear_items()

        # Build Container
        container = discord.ui.Container(accent_color=discord.Color.orange())

        # Header Title
        container.add_item(discord.ui.TextDisplay("### 🛡️ Nexa Moderation System Dashboard"))
        container.add_item(discord.ui.TextDisplay("Centralized command dashboard to customize moderation system status, mute roles, and mod action alerts."))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Status and Core Metrics
        status_emoji = "🟢" if settings.is_moderation_settings_enabled else "🔴"
        status_text = "ENABLED & PROTECTING SERVER" if settings.is_moderation_settings_enabled else "DISABLED"

        mute_role_id = guild_settings.roles.mute_role_id if guild_settings and guild_settings.roles else None
        mute_role_mention = f"<@&{mute_role_id}>" if mute_role_id else "`Not Set`"

        log_channel_id = guild_settings.log_channel.mod_log_channel_id if guild_settings and guild_settings.log_channel else None
        log_channel_mention = f"<#{log_channel_id}>" if log_channel_id else "`Not Set (Defaulting to general)`"

        details = (
            f"### Current State: {status_emoji} {status_text}\n"
            f"- **System Status:** **{'Active' if settings.is_moderation_settings_enabled else 'Inactive'}**\n"
            f"- **Server Mute Role:** {mute_role_mention}\n"
            f"- **Mod Log Alerts Channel:** {log_channel_mention}"
        )
        container.add_item(discord.ui.TextDisplay(details))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Category Dropdown Menu Options
        select_options = [
            discord.SelectOption(label="Mute Role Setup", value="mute_role", description="Assign or change the server mute role", emoji="🤐", default=(self.selected_category == "mute_role")),
            discord.SelectOption(label="Alerts Log Channel", value="alerts_channel", description="Set custom target channel for mod action alerts", emoji="💬", default=(self.selected_category == "alerts_channel")),
        ]

        category_select = discord.ui.Select(
            placeholder="Select a category to customize...",
            options=select_options,
            min_values=1,
            max_values=1
        )
        category_select.callback = self._on_category_select
        container.add_item(discord.ui.ActionRow(category_select))

        # Render V2 dynamic selectors directly on layout dashboard
        if self.selected_category == "mute_role":
            default_roles = []
            if mute_role_id:
                try:
                    default_roles.append(discord.SelectDefaultValue(id=int(mute_role_id), type=discord.SelectDefaultValueType.role))
                except Exception:
                    pass
            role_select = discord.ui.RoleSelect(
                placeholder="Select server mute role...",
                min_values=0,
                max_values=1,
                default_values=default_roles
            )
            role_select.callback = self._on_mute_role_select
            container.add_item(discord.ui.ActionRow(role_select))

        elif self.selected_category == "alerts_channel":
            default_chans = []
            if log_channel_id:
                try:
                    default_chans.append(discord.SelectDefaultValue(id=int(log_channel_id), type=discord.SelectDefaultValueType.channel))
                except Exception:
                    pass
            chan_select = discord.ui.ChannelSelect(
                placeholder="Select channel for moderation alert logs...",
                min_values=0,
                max_values=1,
                default_values=default_chans
            )
            chan_select.callback = self._on_log_channel_select
            container.add_item(discord.ui.ActionRow(chan_select))

        # Action Buttons
        toggle_label = "Disable Moderation" if settings.is_moderation_settings_enabled else "Enable Moderation"
        toggle_style = discord.ButtonStyle.danger if settings.is_moderation_settings_enabled else discord.ButtonStyle.success

        toggle_btn = discord.ui.Button(label=toggle_label, style=toggle_style, emoji="🛡️")
        toggle_btn.callback = self._on_toggle_status

        refresh_btn = discord.ui.Button(label="Refresh Dashboard", style=discord.ButtonStyle.secondary, emoji="🔄")
        refresh_btn.callback = self._on_refresh

        container.add_item(discord.ui.ActionRow(toggle_btn, refresh_btn))

        # Add Container to LayoutView
        self.add_item(container)

    async def refresh_dashboard(self, interaction: discord.Interaction):
        settings = await ModerationService.get_mod_settings(guild_id=self.guild_id)
        guild_settings = await GuildService.get_guild_setting(guild_id=self.guild_id)
        await self._rebuild(settings, guild_settings)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def _on_category_select(self, interaction: discord.Interaction):
        self.selected_category = interaction.data["values"][0]
        settings = await ModerationService.get_mod_settings(guild_id=self.guild_id)
        guild_settings = await GuildService.get_guild_setting(guild_id=self.guild_id)
        await self._rebuild(settings, guild_settings)
        await interaction.response.edit_message(view=self)

    async def _on_toggle_status(self, interaction: discord.Interaction):
        settings = await ModerationService.get_mod_settings(guild_id=self.guild_id)
        new_state = not settings.is_moderation_settings_enabled
        await Database.moderation_settings().update_one(
            {"guild_id": self.guild_id},
            {"$set": {"is_moderation_settings_enabled": new_state}},
            upsert=True
        )
        await self.refresh_dashboard(interaction)

    async def _on_refresh(self, interaction: discord.Interaction):
        await self.refresh_dashboard(interaction)

    async def _on_mute_role_select(self, interaction: discord.Interaction):
        vals = interaction.data.get("values", [])
        role_id = int(vals[0]) if vals else None
        
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                if role >= interaction.guild.me.top_role:
                    await interaction.response.send_message("❌ I cannot manage this role due to role hierarchy.", ephemeral=True)
                    return
                await GuildService.update_guild_settings(guild_id=self.guild_id, **{"roles.mute_role_id": role_id})
                # Apply mute overrides in background
                task = asyncio.create_task(
                    ModerationService.apply_mute_role_to_channels(mute_role=role, guild=interaction.guild)
                )
                def on_done(t):
                    if t.exception():
                        logger.error(f"Failed to apply mute role: {t.exception()}")
                task.add_done_callback(on_done)
        else:
            await GuildService.update_guild_settings(guild_id=self.guild_id, **{"roles.mute_role_id": None})

        await interaction.response.send_message("✅ Mute role settings updated.", ephemeral=True)
        await self.refresh_dashboard(interaction)

    async def _on_log_channel_select(self, interaction: discord.Interaction):
        vals = interaction.data.get("values", [])
        channel_id = int(vals[0]) if vals else None
        
        await GuildService.update_guild_settings(guild_id=self.guild_id, **{"log_channel.mod_log_channel_id": channel_id})
        await interaction.response.send_message("✅ Mod log alerts channel updated.", ephemeral=True)
        await self.refresh_dashboard(interaction)
