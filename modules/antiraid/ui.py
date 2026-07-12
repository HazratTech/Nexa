import discord
from discord.ui import TextInput, Modal
from typing import Optional
from core.models.guild_models import AntiRaidSettings
from modules.antiraid.services import AntiRaidService
from core.engines.antiraid_engine import RaidMode


class JoinRateModal(Modal, title="Configure Join Flood Limits"):
    joins = TextInput(label="Max Joins", placeholder="e.g. 10", min_length=1, max_length=4)
    seconds = TextInput(label="Window (seconds)", placeholder="e.g. 10", min_length=1, max_length=4)

    def __init__(self, settings: AntiRaidSettings, view: "AntiRaidDashboardView"):
        super().__init__()
        self.settings = settings
        self.view = view
        self.joins.default = str(settings.join_rate_limit)
        self.seconds.default = str(settings.join_rate_window)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            jn = int(self.joins.value)
            sec = int(self.seconds.value)
            if jn <= 0 or sec <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Invalid numbers. Please enter positive integers.", ephemeral=True)
            return

        await AntiRaidService.update_settings(interaction.guild_id, join_rate_limit=jn, join_rate_window=sec)
        await self.view.refresh_dashboard(interaction)


class AccountAgeModal(Modal, title="Configure Account Age Filter"):
    days = TextInput(label="Minimum Account Age (days)", placeholder="e.g. 7", min_length=1, max_length=4)
    action = TextInput(label="Action (kick / ban / alert / none)", placeholder="kick | ban | alert | none", min_length=3, max_length=10)

    def __init__(self, settings: AntiRaidSettings, view: "AntiRaidDashboardView"):
        super().__init__()
        self.settings = settings
        self.view = view
        self.days.default = str(settings.min_account_age_days)
        self.action.default = str(settings.account_age_action)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            dy = int(self.days.value)
            act = self.action.value.strip().lower()
            if dy < 0:
                raise ValueError()
            if act not in ["kick", "ban", "alert", "none"]:
                await interaction.response.send_message("❌ Action must be one of: `kick`, `ban`, `alert`, or `none`.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Days must be a non-negative integer.", ephemeral=True)
            return

        await AntiRaidService.update_settings(interaction.guild_id, min_account_age_days=dy, account_age_action=act)
        await self.view.refresh_dashboard(interaction)


class NoAvatarModal(Modal, title="Configure Default Avatar Filter"):
    action = TextInput(label="Action (kick / ban / alert / none)", placeholder="kick | ban | alert | none", min_length=3, max_length=10)

    def __init__(self, settings: AntiRaidSettings, view: "AntiRaidDashboardView"):
        super().__init__()
        self.settings = settings
        self.view = view
        self.action.default = str(settings.no_avatar_action)

    async def on_submit(self, interaction: discord.Interaction):
        act = self.action.value.strip().lower()
        if act not in ["kick", "ban", "alert", "none"]:
            await interaction.response.send_message("❌ Action must be one of: `kick`, `ban`, `alert`, or `none`.", ephemeral=True)
            return

        await AntiRaidService.update_settings(interaction.guild_id, no_avatar_action=act)
        await self.view.refresh_dashboard(interaction)


class RaidActionModal(Modal, title="Configure Raid Action Settings"):
    action = TextInput(label="Raid Response Action", placeholder="lockdown | panic | alert", min_length=5, max_length=10)
    lockdown_duration = TextInput(label="Lockdown Duration (seconds)", placeholder="e.g. 300", min_length=1, max_length=5)

    def __init__(self, settings: AntiRaidSettings, view: "AntiRaidDashboardView"):
        super().__init__()
        self.settings = settings
        self.view = view
        self.action.default = str(settings.raid_mode_action)
        self.lockdown_duration.default = str(settings.raid_lockdown_duration)

    async def on_submit(self, interaction: discord.Interaction):
        act = self.action.value.strip().lower()
        if act not in ["lockdown", "panic", "alert"]:
            await interaction.response.send_message("❌ Action must be one of: `lockdown`, `panic`, or `alert`.", ephemeral=True)
            return

        try:
            dur = int(self.lockdown_duration.value)
            if dur <= 10:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Duration must be a positive integer greater than 10 seconds.", ephemeral=True)
            return

        await AntiRaidService.update_settings(interaction.guild_id, raid_mode_action=act, raid_lockdown_duration=dur)
        await self.view.refresh_dashboard(interaction)


class DMNoticesModal(Modal, title="DM Notices Setup"):
    dm_on_kick = TextInput(label="Send DM on Kick? (true / false)", placeholder="true | false", min_length=4, max_length=5)
    dm_message = TextInput(label="Custom DM Message Text", placeholder="e.g. Kicked due to active raid", style=discord.TextStyle.paragraph, max_length=200)

    def __init__(self, settings: AntiRaidSettings, view: "AntiRaidDashboardView"):
        super().__init__()
        self.settings = settings
        self.view = view
        self.dm_on_kick.default = "true" if settings.dm_on_kick else "false"
        self.dm_message.default = str(settings.dm_message)

    async def on_submit(self, interaction: discord.Interaction):
        dm = self.dm_on_kick.value.strip().lower()
        if dm not in ["true", "false"]:
            await interaction.response.send_message("❌ Send DM setting must be `true` or `false`.", ephemeral=True)
            return
            
        dm_bool = dm == "true"
        dm_msg = self.dm_message.value

        await AntiRaidService.update_settings(interaction.guild_id, dm_on_kick=dm_bool, dm_message=dm_msg)
        await self.view.refresh_dashboard(interaction)


class AntiRaidDashboardView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, settings: AntiRaidSettings, current_mode: RaidMode):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.selected_category: Optional[str] = None
        self.current_mode = current_mode
        self._rebuild(settings)

    def _rebuild(self, settings: AntiRaidSettings):
        self.clear_items()

        # Build Container
        container = discord.ui.Container(accent_color=discord.Color.red())

        # Header Title
        container.add_item(discord.ui.TextDisplay("### 🚨 Nexa Anti-Raid Setup Dashboard"))
        container.add_item(discord.ui.TextDisplay("Configure join protection filters, default avatar filters, and lockdown/panic responses."))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Status and Live State
        status_emoji = "🟢" if settings.enabled else "🔴"
        status_text = "ENABLED & ACTIVELY SECURING JOINS" if settings.enabled else "DISABLED"
        
        mode_text = f"🛡️ **{self.current_mode.name}**"

        details = (
            f"### General State: {status_emoji} {status_text}\n"
            f"- **Active Server Mode:** {mode_text}\n"
            f"- **Join Rate Flood Limit:** `{settings.join_rate_limit}` joins per `{settings.join_rate_window}` seconds\n"
            f"- **Suspicious Account Age:** Younger than `{settings.min_account_age_days}` days → **{settings.account_age_action.upper()}**\n"
            f"- **Default Avatar Filter:** No profile picture → **{settings.no_avatar_action.upper()}**"
        )
        container.add_item(discord.ui.TextDisplay(details))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Raid Response
        verify_escalation = "Yes" if settings.auto_verify_escalation else "No"
        log_chan = f"<#{settings.log_channel_id}>" if settings.log_channel_id else "General mod log channel"
        
        response_text = (
            f"### ⚡ Coordinated Raid Response\n"
            f"- **Active Raid Action:** **{settings.raid_mode_action.upper()}**\n"
            f"- **Lockdown Duration:** `{settings.raid_lockdown_duration}` seconds before auto-deescalation\n"
            f"- **Escalate Server Verification Level:** `{verify_escalation}`\n"
            f"- **Target Log Channel:** {log_chan}"
        )
        container.add_item(discord.ui.TextDisplay(response_text))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # DM Settings
        dm_notices = "🟢 Enabled" if settings.dm_on_kick else "🔴 Disabled"
        dm_text = (
            f"### ✉️ DM Warnings\n"
            f"- **Send DM notices on action:** {dm_notices}\n"
            f"- **Warning DM Message:** *\"{settings.dm_message}\"*"
        )
        container.add_item(discord.ui.TextDisplay(dm_text))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Category Dropdown Menu Options
        select_options = [
            discord.SelectOption(label="Join Flood Limits", value="join_rate", description="Configure join rate detection limits", emoji="⏱️", default=(self.selected_category == "join_rate")),
            discord.SelectOption(label="Account Age Filter", value="account_age", description="Configure fresh accounts checking", emoji="📅", default=(self.selected_category == "account_age")),
            discord.SelectOption(label="Default Avatar Filter", value="no_avatar", description="Configure avatarless user checking", emoji="😀", default=(self.selected_category == "no_avatar")),
            discord.SelectOption(label="Raid Action Settings", value="raid_action", description="Configure lockdown responses", emoji="⚡", default=(self.selected_category == "raid_action")),
            discord.SelectOption(label="DM warnings", value="dm_notices", description="Configure DM warning notices text", emoji="✉️", default=(self.selected_category == "dm_notices")),
            discord.SelectOption(label="Alerts Log Channel", value="alerts_channel", description="Set custom channel for security alerts", emoji="💬", default=(self.selected_category == "alerts_channel")),
        ]

        category_select = discord.ui.Select(
            placeholder="Select a settings category to customize...",
            options=select_options,
            min_values=1,
            max_values=1
        )
        category_select.callback = self._on_category_select
        container.add_item(discord.ui.ActionRow(category_select))

        # Render V2 ChannelSelect directly on layout dashboard
        if self.selected_category == "alerts_channel":
            default_chans = []
            if settings.log_channel_id:
                try:
                    default_chans.append(discord.SelectDefaultValue(id=int(settings.log_channel_id), type=discord.SelectDefaultValueType.channel))
                except Exception:
                    pass
            alerts_select = discord.ui.ChannelSelect(
                placeholder="Select channel for anti-raid alert logs...",
                min_values=0,
                max_values=1,
                default_values=default_chans
            )
            alerts_select.callback = self._on_alerts_channel_select
            container.add_item(discord.ui.ActionRow(alerts_select))

        # Action Buttons
        toggle_label = "Disable Protection" if settings.enabled else "Enable Protection"
        toggle_style = discord.ButtonStyle.danger if settings.enabled else discord.ButtonStyle.success

        toggle_btn = discord.ui.Button(label=toggle_label, style=toggle_style, emoji="🛡️")
        toggle_btn.callback = self._on_toggle_status

        has_select_rendered = self.selected_category == "alerts_channel"
        edit_btn = discord.ui.Button(
            label="Edit Category",
            style=discord.ButtonStyle.primary,
            emoji="⚙️",
            disabled=(self.selected_category is None or has_select_rendered)
        )
        edit_btn.callback = self._on_edit_category

        refresh_btn = discord.ui.Button(label="Refresh Dashboard", style=discord.ButtonStyle.secondary, emoji="🔄")
        refresh_btn.callback = self._on_refresh

        # Lockdown / Unlock button
        lock_label = "Cancel Lockdown" if self.current_mode >= RaidMode.LOCKDOWN else "Trigger Lockdown"
        lock_style = discord.ButtonStyle.success if self.current_mode >= RaidMode.LOCKDOWN else discord.ButtonStyle.danger
        lock_btn = discord.ui.Button(label=lock_label, style=lock_style, emoji="🚨")
        lock_btn.callback = self._on_lockdown_toggle

        container.add_item(discord.ui.ActionRow(toggle_btn, edit_btn, refresh_btn, lock_btn))

        # Add Container to LayoutView
        self.add_item(container)

    async def refresh_dashboard(self, interaction: discord.Interaction):
        settings = await AntiRaidService.get_settings(self.guild_id)
        if hasattr(self, "parent_cog") and self.parent_cog:
            self.current_mode = await self.parent_cog.engine.get_raid_mode(self.guild_id)
        
        self._rebuild(settings)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def _on_category_select(self, interaction: discord.Interaction):
        self.selected_category = interaction.data["values"][0]
        settings = await AntiRaidService.get_settings(self.guild_id)
        self._rebuild(settings)
        await interaction.response.edit_message(view=self)

    async def _on_toggle_status(self, interaction: discord.Interaction):
        settings = await AntiRaidService.get_settings(self.guild_id)
        new_state = not settings.enabled
        await AntiRaidService.update_settings(self.guild_id, enabled=new_state)
        await self.refresh_dashboard(interaction)

    async def _on_refresh(self, interaction: discord.Interaction):
        await self.refresh_dashboard(interaction)

    async def _on_alerts_channel_select(self, interaction: discord.Interaction):
        vals = interaction.data.get("values", [])
        log_id = str(vals[0]) if vals else None
        await AntiRaidService.update_settings(interaction.guild_id, log_channel_id=log_id)
        await self.refresh_dashboard(interaction)

    async def _on_edit_category(self, interaction: discord.Interaction):
        if not self.selected_category:
            return

        settings = await AntiRaidService.get_settings(self.guild_id)

        if self.selected_category == "join_rate":
            await interaction.response.send_modal(JoinRateModal(settings, self))
        elif self.selected_category == "account_age":
            await interaction.response.send_modal(AccountAgeModal(settings, self))
        elif self.selected_category == "no_avatar":
            await interaction.response.send_modal(NoAvatarModal(settings, self))
        elif self.selected_category == "raid_action":
            await interaction.response.send_modal(RaidActionModal(settings, self))
        elif self.selected_category == "dm_notices":
            await interaction.response.send_modal(DMNoticesModal(settings, self))

    async def _on_lockdown_toggle(self, interaction: discord.Interaction):
        from core.models.antispam_models import AntiRaidIncident
        
        cog = self.parent_cog if hasattr(self, "parent_cog") else None
        if not cog:
            await interaction.response.send_message("❌ Failed to resolve Anti-Raid Cog controller.", ephemeral=True)
            return

        guild = interaction.guild
        settings = await AntiRaidService.get_settings(guild.id)
        
        if self.current_mode >= RaidMode.LOCKDOWN:
            await cog.deescalate_guild(guild, reason=f"Manual unlock from dashboard by {interaction.user.name}")
            await interaction.response.send_message("✅ Lockdown terminated. Channels unlocked.", ephemeral=True)
        else:
            await cog.engine.set_raid_mode(guild.id, RaidMode.LOCKDOWN)
            await cog.engine.extend_lockdown_timer(guild.id, settings.raid_lockdown_duration)
            locked_count = await cog.lock_guild_channels(guild, True)
            
            if settings.auto_verify_escalation:
                try:
                    await guild.edit(verification_level=discord.VerificationLevel.highest)
                except Exception:
                    pass
            
            await AntiRaidService.log_incident(AntiRaidIncident(
                guild_id=guild.id,
                raid_level=int(RaidMode.LOCKDOWN),
                trigger_type="manual",
                join_count=0,
                window_seconds=0,
                actions_taken=[f"Manual Lockdown initiated by {interaction.user.name}"]
            ))
            
            await interaction.response.send_message(f"🚨 Lockdown initiated. Locked down {locked_count} public channels.", ephemeral=True)

        await self.refresh_dashboard(interaction)
