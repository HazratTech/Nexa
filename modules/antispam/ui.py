import discord
from discord.ui import TextInput, Modal
from typing import List, Optional
from core.models.guild_models import AntiSpamSettings, AntiSpamAction
from modules.antispam.services import AntiSpamService


class MessageRateModal(Modal, title="Configure Message Rate Limit"):
    messages = TextInput(label="Message Limit", placeholder="e.g. 5", min_length=1, max_length=4)
    seconds = TextInput(label="Window (seconds)", placeholder="e.g. 5", min_length=1, max_length=4)

    def __init__(self, settings: AntiSpamSettings, view: "AntiSpamDashboardView"):
        super().__init__()
        self.settings = settings
        self.view = view
        self.messages.default = str(settings.message_rate_limit)
        self.seconds.default = str(settings.message_rate_window)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            msgs = int(self.messages.value)
            secs = int(self.seconds.value)
            if msgs <= 0 or secs <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Invalid numbers. Please enter positive integers.", ephemeral=True)
            return

        await AntiSpamService.update_settings(interaction.guild_id, message_rate_limit=msgs, message_rate_window=secs)
        await self.view.refresh_dashboard(interaction)


class DuplicateFilterModal(Modal, title="Configure Duplicate Filter"):
    threshold = TextInput(label="Duplicate Count Threshold", placeholder="e.g. 3", min_length=1, max_length=4)
    seconds = TextInput(label="Window (seconds)", placeholder="e.g. 30", min_length=1, max_length=4)

    def __init__(self, settings: AntiSpamSettings, view: "AntiSpamDashboardView"):
        super().__init__()
        self.settings = settings
        self.view = view
        self.threshold.default = str(settings.duplicate_threshold)
        self.seconds.default = str(settings.duplicate_window)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.threshold.value)
            secs = int(self.seconds.value)
            if val <= 0 or secs <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Invalid numbers. Please enter positive integers.", ephemeral=True)
            return

        await AntiSpamService.update_settings(interaction.guild_id, duplicate_threshold=val, duplicate_window=secs)
        await self.view.refresh_dashboard(interaction)


class MentionLimitModal(Modal, title="Configure Mention Limits"):
    per_message = TextInput(label="Max Mentions Per Message", placeholder="e.g. 5", min_length=1, max_length=4)
    per_window = TextInput(label="Max Mentions In Window", placeholder="e.g. 10", min_length=1, max_length=4)
    window = TextInput(label="Window (seconds)", placeholder="e.g. 15", min_length=1, max_length=4)

    def __init__(self, settings: AntiSpamSettings, view: "AntiSpamDashboardView"):
        super().__init__()
        self.settings = settings
        self.view = view
        self.per_message.default = str(settings.max_mentions_per_message)
        self.per_window.default = str(settings.max_mentions_per_window)
        self.window.default = str(settings.mention_window)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            per_msg = int(self.per_message.value)
            per_win = int(self.per_window.value)
            win = int(self.window.value)
            if per_msg <= 0 or per_win <= 0 or win <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Invalid numbers. Please enter positive integers.", ephemeral=True)
            return

        await AntiSpamService.update_settings(
            interaction.guild_id,
            max_mentions_per_message=per_msg,
            max_mentions_per_window=per_win,
            mention_window=win
        )
        await self.view.refresh_dashboard(interaction)


class EmojiNewlineModal(Modal, title="Configure Emoji & Newline Limits"):
    emojis = TextInput(label="Max Emojis Per Message", placeholder="e.g. 15", min_length=1, max_length=4)
    newlines = TextInput(label="Max Newlines Per Message", placeholder="e.g. 20", min_length=1, max_length=4)

    def __init__(self, settings: AntiSpamSettings, view: "AntiSpamDashboardView"):
        super().__init__()
        self.settings = settings
        self.view = view
        self.emojis.default = str(settings.max_emojis_per_message)
        self.newlines.default = str(settings.max_newlines)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            emo = int(self.emojis.value)
            nl = int(self.newlines.value)
            if emo <= 0 or nl <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Invalid numbers. Please enter positive integers.", ephemeral=True)
            return

        await AntiSpamService.update_settings(interaction.guild_id, max_emojis_per_message=emo, max_newlines=nl)
        await self.view.refresh_dashboard(interaction)


class StickerAttachmentModal(Modal, title="Stickers & Attachments"):
    stickers = TextInput(label="Max Stickers In Window", placeholder="e.g. 5", min_length=1, max_length=4)
    sticker_win = TextInput(label="Stickers Window (seconds)", placeholder="e.g. 10", min_length=1, max_length=4)
    attachments = TextInput(label="Max Attachments In Window", placeholder="e.g. 5", min_length=1, max_length=4)
    attachment_win = TextInput(label="Attachments Window (sec)", placeholder="e.g. 10", min_length=1, max_length=4)

    def __init__(self, settings: AntiSpamSettings, view: "AntiSpamDashboardView"):
        super().__init__()
        self.settings = settings
        self.view = view
        self.stickers.default = str(settings.max_stickers_per_window)
        self.sticker_win.default = str(settings.sticker_window)
        self.attachments.default = str(settings.max_attachments_per_window)
        self.attachment_win.default = str(settings.attachment_window)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            stk = int(self.stickers.value)
            stk_w = int(self.sticker_win.value)
            att = int(self.attachments.value)
            att_w = int(self.attachment_win.value)
            if stk <= 0 or stk_w <= 0 or att <= 0 or att_w <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Invalid numbers. Please enter positive integers.", ephemeral=True)
            return

        await AntiSpamService.update_settings(
            interaction.guild_id,
            max_stickers_per_window=stk,
            sticker_window=stk_w,
            max_attachments_per_window=att,
            attachment_window=att_w
        )
        await self.view.refresh_dashboard(interaction)


class ActionEscalationModal(Modal, title="Manage Escalating Action"):
    violation_count = TextInput(label="Violation Count Trigger", placeholder="e.g. 3", min_length=1, max_length=4)
    action_type = TextInput(label="Action (delete / timeout / kick / ban)", placeholder="delete | delete+warn | timeout | kick | ban", min_length=4, max_length=15)
    duration = TextInput(label="Timeout Duration (seconds)", placeholder="e.g. 300 (Only for timeout action)", required=False)

    def __init__(self, settings: AntiSpamSettings, view: "AntiSpamDashboardView"):
        super().__init__()
        self.settings = settings
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            count = int(self.violation_count.value)
            action = self.action_type.value.strip().lower()
            if count <= 0:
                raise ValueError()
            if action not in ["delete", "delete+warn", "timeout", "kick", "ban", "none"]:
                await interaction.response.send_message("❌ Action must be one of: `delete`, `delete+warn`, `timeout`, `kick`, `ban`, or `none` to remove.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Violation count must be a positive integer.", ephemeral=True)
            return

        dur = 300
        if self.duration.value:
            try:
                dur = int(self.duration.value)
            except ValueError:
                pass

        updated_actions = [a for a in self.settings.actions if a.violation_count != count]
        if action != "none":
            new_action = AntiSpamAction(violation_count=count, action=action, duration=dur)
            updated_actions.append(new_action)

        serialized_actions = [a.model_dump() for a in updated_actions]
        await AntiSpamService.update_settings(interaction.guild_id, actions=serialized_actions)
        await self.view.refresh_dashboard(interaction)


class AntiSpamDashboardView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, settings: AntiSpamSettings):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.selected_category: Optional[str] = None
        self._rebuild(settings)

    def _rebuild(self, settings: AntiSpamSettings):
        self.clear_items()

        # Build Container
        container = discord.ui.Container(accent_color=discord.Color.blue())

        # Header Title
        container.add_item(discord.ui.TextDisplay("### 🛡️ Nexa Anti-Spam Setup Dashboard"))
        container.add_item(discord.ui.TextDisplay("Configure real-time message moderation controls using purely native Discord components below."))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Status and Core Metrics
        status_emoji = "🟢" if settings.enabled else "🔴"
        status_text = "ENABLED & ACTIVELY SECURING CHANNELS" if settings.enabled else "DISABLED"

        details = (
            f"### Current State: {status_emoji} {status_text}\n"
            f"- **Message Rate Limit:** `{settings.message_rate_limit}` messages per `{settings.message_rate_window}` seconds\n"
            f"- **Duplicate Content Filter:** `{settings.duplicate_threshold}` identical per `{settings.duplicate_window}` seconds\n"
            f"- **Mention Limit:** Max `{settings.max_mentions_per_message}` per message | `{settings.max_mentions_per_window}` per `{settings.mention_window}` seconds\n"
            f"- **Emoji Limit:** Max `{settings.max_emojis_per_message}` emojis per message\n"
            f"- **Newlines Wall Limit:** Max `{settings.max_newlines}` newlines per message\n"
            f"- **Sticker Limit:** `{settings.max_stickers_per_window}` stickers / `{settings.sticker_window}` seconds\n"
            f"- **Attachment Limit:** `{settings.max_attachments_per_window}` files / `{settings.attachment_window}` seconds"
        )
        container.add_item(discord.ui.TextDisplay(details))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Escalating Actions
        actions_str = ""
        sorted_actions = sorted(settings.actions, key=lambda a: a.violation_count)
        for act in sorted_actions:
            duration_str = f" ({act.duration}s timeout)" if act.action == "timeout" else ""
            actions_str += f"• `{act.violation_count} Violation(s)` → **{act.action.upper()}**{duration_str}\n"

        punishments = f"### 🔨 Escalating Punishments\n{actions_str or 'No active actions. (Deletes spam by default)'}"
        container.add_item(discord.ui.TextDisplay(punishments))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Exemptions Summary
        exemptions = (
            f"### 🛡️ Exemptions Summary\n"
            f"- Ignored channels count: `{len(settings.ignored_channels)}`\n"
            f"- Ignored roles count: `{len(settings.ignored_roles)}`\n"
            f"- Whitelisted users count: `{len(settings.whitelisted_users)}`"
        )
        container.add_item(discord.ui.TextDisplay(exemptions))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Category Dropdown Menu Options
        select_options = [
            discord.SelectOption(label="Message Rate Limit", value="rate_limit", description="Configure message speed controls", emoji="⏱️", default=(self.selected_category == "rate_limit")),
            discord.SelectOption(label="Duplicate Content Filter", value="duplicate", description="Configure repeated text blocking", emoji="👥", default=(self.selected_category == "duplicate")),
            discord.SelectOption(label="Mention Limits", value="mention", description="Configure mass mention filters", emoji="🆔", default=(self.selected_category == "mention")),
            discord.SelectOption(label="Emoji & Newline Limits", value="emoji_newline", description="Configure emoji and newline rules", emoji="😀", default=(self.selected_category == "emoji_newline")),
            discord.SelectOption(label="Sticker & Attachment Limits", value="sticker_attachment", description="Configure media flooding limits", emoji="📎", default=(self.selected_category == "sticker_attachment")),
            discord.SelectOption(label="Escalating Actions", value="escalation", description="Configure custom timeout/kick/ban thresholds", emoji="🔨", default=(self.selected_category == "escalation")),
            discord.SelectOption(label="Exempt Channels", value="ignored_channels", description="Set channels exempt from checks", emoji="💬", default=(self.selected_category == "ignored_channels")),
            discord.SelectOption(label="Exempt Roles", value="ignored_roles", description="Set roles exempt from checks", emoji="🛡️", default=(self.selected_category == "ignored_roles")),
            discord.SelectOption(label="Whitelisted Users", value="whitelisted_users", description="Set users exempt from checks", emoji="👤", default=(self.selected_category == "whitelisted_users")),
        ]

        category_select = discord.ui.Select(
            placeholder="Select a category to customize...",
            options=select_options,
            min_values=1,
            max_values=1
        )
        category_select.callback = self._on_category_select
        container.add_item(discord.ui.ActionRow(category_select))

        # Dynamic V2 selectors rendered inline
        if self.selected_category == "ignored_channels":
            default_chans = []
            for cid in settings.ignored_channels:
                try:
                    default_chans.append(discord.SelectDefaultValue(id=int(cid), type=discord.SelectDefaultValueType.channel))
                except Exception:
                    pass
            chan_select = discord.ui.ChannelSelect(
                placeholder="Select channels to exempt from anti-spam...",
                min_values=0,
                max_values=10,
                default_values=default_chans
            )
            chan_select.callback = self._on_channels_select
            container.add_item(discord.ui.ActionRow(chan_select))

        elif self.selected_category == "ignored_roles":
            default_roles = []
            for rid in settings.ignored_roles:
                try:
                    default_roles.append(discord.SelectDefaultValue(id=int(rid), type=discord.SelectDefaultValueType.role))
                except Exception:
                    pass
            role_select = discord.ui.RoleSelect(
                placeholder="Select roles to exempt from anti-spam...",
                min_values=0,
                max_values=10,
                default_values=default_roles
            )
            role_select.callback = self._on_roles_select
            container.add_item(discord.ui.ActionRow(role_select))

        elif self.selected_category == "whitelisted_users":
            default_users = []
            for uid in settings.whitelisted_users:
                try:
                    default_users.append(discord.SelectDefaultValue(id=int(uid), type=discord.SelectDefaultValueType.user))
                except Exception:
                    pass
            user_select = discord.ui.UserSelect(
                placeholder="Select users to whitelist from anti-spam...",
                min_values=0,
                max_values=10,
                default_values=default_users
            )
            user_select.callback = self._on_users_select
            container.add_item(discord.ui.ActionRow(user_select))

        # Action Buttons
        toggle_label = "Disable Engine" if settings.enabled else "Enable Engine"
        toggle_style = discord.ButtonStyle.danger if settings.enabled else discord.ButtonStyle.success
        
        toggle_btn = discord.ui.Button(label=toggle_label, style=toggle_style, emoji="🛡️")
        toggle_btn.callback = self._on_toggle_status

        has_select_rendered = self.selected_category in ["ignored_channels", "ignored_roles", "whitelisted_users"]
        edit_btn = discord.ui.Button(
            label="Edit Category",
            style=discord.ButtonStyle.primary,
            emoji="⚙️",
            disabled=(self.selected_category is None or has_select_rendered)
        )
        edit_btn.callback = self._on_edit_category

        refresh_btn = discord.ui.Button(label="Refresh Dashboard", style=discord.ButtonStyle.secondary, emoji="🔄")
        refresh_btn.callback = self._on_refresh

        container.add_item(discord.ui.ActionRow(toggle_btn, edit_btn, refresh_btn))

        # Add Container to LayoutView
        self.add_item(container)

    async def refresh_dashboard(self, interaction: discord.Interaction):
        settings = await AntiSpamService.get_settings(self.guild_id)
        self._rebuild(settings)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def _on_category_select(self, interaction: discord.Interaction):
        self.selected_category = interaction.data["values"][0]
        settings = await AntiSpamService.get_settings(self.guild_id)
        self._rebuild(settings)
        await interaction.response.edit_message(view=self)

    async def _on_toggle_status(self, interaction: discord.Interaction):
        settings = await AntiSpamService.get_settings(self.guild_id)
        new_state = not settings.enabled
        await AntiSpamService.update_settings(self.guild_id, enabled=new_state)
        await self.refresh_dashboard(interaction)

    async def _on_refresh(self, interaction: discord.Interaction):
        await self.refresh_dashboard(interaction)

    async def _on_channels_select(self, interaction: discord.Interaction):
        channel_ids = interaction.data.get("values", [])
        await AntiSpamService.update_settings(interaction.guild_id, ignored_channels=channel_ids)
        await self.refresh_dashboard(interaction)

    async def _on_roles_select(self, interaction: discord.Interaction):
        role_ids = interaction.data.get("values", [])
        await AntiSpamService.update_settings(interaction.guild_id, ignored_roles=role_ids)
        await self.refresh_dashboard(interaction)

    async def _on_users_select(self, interaction: discord.Interaction):
        user_ids = interaction.data.get("values", [])
        await AntiSpamService.update_settings(interaction.guild_id, whitelisted_users=user_ids)
        await self.refresh_dashboard(interaction)

    async def _on_edit_category(self, interaction: discord.Interaction):
        if not self.selected_category:
            return

        settings = await AntiSpamService.get_settings(self.guild_id)

        if self.selected_category == "rate_limit":
            await interaction.response.send_modal(MessageRateModal(settings, self))
        elif self.selected_category == "duplicate":
            await interaction.response.send_modal(DuplicateFilterModal(settings, self))
        elif self.selected_category == "mention":
            await interaction.response.send_modal(MentionLimitModal(settings, self))
        elif self.selected_category == "emoji_newline":
            await interaction.response.send_modal(EmojiNewlineModal(settings, self))
        elif self.selected_category == "sticker_attachment":
            await interaction.response.send_modal(StickerAttachmentModal(settings, self))
        elif self.selected_category == "escalation":
            await interaction.response.send_modal(ActionEscalationModal(settings, self))
