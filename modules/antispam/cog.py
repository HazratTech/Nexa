import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger
from typing import Optional

from core.database import Database
from core.models.guild_models import AntiSpamSettings, AntiSpamAction
from core.engines.antispam_engine import AntiSpamEngine, SpamVerdict
from core.engines.action_dispatcher import ActionDispatcher
from modules.antispam.services import AntiSpamService


class AntiSpamCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.engine = AntiSpamEngine()
        self.dispatcher = ActionDispatcher(bot)

    @app_commands.command(name="antispam_config", description="Interactive dashboard to customize anti-spam settings")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def antispam_config_dashboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings = await AntiSpamService.get_settings(interaction.guild_id)
        from modules.antispam.ui import AntiSpamDashboardView
        view = AntiSpamDashboardView(interaction.guild_id, settings)
        await interaction.followup.send(view=view)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        settings = await AntiSpamService.get_settings(message.guild.id)
        if not settings.enabled:
            return

        # Ignored Channel check
        if str(message.channel.id) in settings.ignored_channels:
            return

        # Ignored Role check
        user_role_ids = [str(r.id) for r in message.author.roles]
        if any(rid in settings.ignored_roles for rid in user_role_ids):
            return

        # Whitelisted User check
        if str(message.author.id) in settings.whitelisted_users:
            return

        # Bypass Administrators and Server Owner
        if message.author.guild_permissions.administrator or message.author == message.guild.owner:
            return

        # Check spam status
        verdict = await self.engine.process_message(message, settings)
        if verdict:
            await self._handle_spam_verdict(message, verdict, settings)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # Scan edited messages to prevent edit-to-spam bypass
        if after.author.bot or not after.guild:
            return

        settings = await AntiSpamService.get_settings(after.guild.id)
        if not settings.enabled:
            return

        # Ignored filters
        if str(after.channel.id) in settings.ignored_channels:
            return
        user_role_ids = [str(r.id) for r in after.author.roles]
        if any(rid in settings.ignored_roles for rid in user_role_ids):
            return
        if str(after.author.id) in settings.whitelisted_users:
            return
        if after.author.guild_permissions.administrator or after.author == after.guild.owner:
            return

        verdict = await self.engine.process_message(after, settings)
        if verdict:
            await self._handle_spam_verdict(after, verdict, settings)

    async def _handle_spam_verdict(self, message: discord.Message, verdict: SpamVerdict, settings: AntiSpamSettings):
        guild = message.guild
        author = message.author
        prefix = f"spam:{guild.id}:{author.id}"

        # Increment violation score
        score = await self.engine.increment_violation_score(prefix, 1)

        # Set temporary cooldown to prevent double processing in window
        await self.engine.set_cooldown(prefix, 3)

        # Determine target action based on escalating actions configured
        target_action = "delete" # Default fallback
        action_duration = 300
        
        # Sort actions descending to find the highest threshold <= current score
        sorted_actions = sorted(settings.actions, key=lambda a: a.violation_count, reverse=True)
        for act in sorted_actions:
            if score >= act.violation_count:
                target_action = act.action
                action_duration = act.duration
                break

        # Execute action
        reason = f"Spam detected: {verdict.reason} (violation score: {score})"
        await self.dispatcher.execute(
            action=target_action,
            target=author,
            guild=guild,
            reason=reason,
            source="antispam",
            duration=action_duration,
            message=message,
            violation_score=score,
            violation_type=verdict.violation_type
        )

        # Quick warning alert to user in the channel (deleted after 3 seconds)
        try:
            warn_msg = await message.channel.send(
                f"⚠️ {author.mention}, please stop spamming! Action: **{target_action.replace('delete+', '').upper()}**."
            )
            await asyncio.sleep(3)
            await warn_msg.delete()
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(AntiSpamCog(bot))
