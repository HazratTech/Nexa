from datetime import datetime

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict


class EmbedField(BaseModel):
    name: str = Field(..., description="Name of the embed field")
    value: str = Field(..., description="Value of the embed field")
    inline: bool = Field(default=True, description="Whether the field is inline")


class WelcomeEmbed(BaseModel):
    title: Optional[str] = "Welcome!"
    description: Optional[str] = "Glad to have you here!"
    color: Optional[str] = None  # Hex color code as a string (e.g., "#FF5733")
    thumbnail_url: Optional[str] = None
    image_url: Optional[str] = None
    footer: Optional[str] = None
    fields: List[EmbedField] = Field(default_factory=list)

    @validator("color")
    def validate_color(cls, value):
        if value and not value.startswith("#"):
            raise ValueError("Color must be a hex string starting with '#'")
        return value


class Roles(BaseModel):
    mute_role_id: Optional[int] = int

class LogChannel(BaseModel):
    log_channel_id: Optional[int] = None
    mod_log_channel_id: Optional[int] = None
    message_log_channel_id: Optional[int] = None
    join_leave_logs: Optional[int] = None
    command_logs: Optional[int] = None


class GuildSettings(BaseModel):
    guild_id: int
    prefix: str = "!"

    # Welcome settings
    welcome_enabled: bool = True
    welcome_channel_id: Optional[str] = None
    welcome_embed: Optional[WelcomeEmbed] = None 


    # Logging settings
    logging_enabled: bool = True
    log_channel: Optional[LogChannel] = None

    roles: Optional[Roles] = None

    # Leveling settings
    leveling_enabled: bool = False
    leveling_channel_id: Optional[str] = None
    level_roles: Dict[int, str] = Field(default_factory=dict)

    # Economy settings
    economy_enabled: bool = False
    economy_channel_id: Optional[str] = None
    starting_balance: int = 100

    # Notification settings
    notify_channel_id: Optional[str] = None
    notify_role_id: Optional[str] = None

    # Miscellaneous
    timezone: Optional[str] = None
    language: Optional[str] = None

    #Roles
    new_member_join_role: Optional[str] = None  # Role to assign to new members
    bot_role: Optional[str] = None  # Role for the bot itself
    
    is_premium: bool = Field(default=False)

class AutoModGlobal(BaseModel):
    is_enabled: bool = True
    ignored_channels: List[str] = Field(default_factory=list)
    ignored_roles: List[str] = Field(default_factory=list)
    media_only_channels: List[str] = Field(default_factory=list)
    youtube_only_channels: List[str] = Field(default_factory=list)
    twitch_only_channels: List[str] = Field(default_factory=list)

class FilterConfig(BaseModel):
    enabled: bool = False
    actions: List[str] = Field(default_factory=list)
    timeout_duration: int = 60
    ignored_roles: List[str] = Field(default_factory=list)
    ignored_channels: List[str] = Field(default_factory=list)
    custom_config: Dict = Field(default_factory=dict)

class AutoModFilters(BaseModel):
    spam: FilterConfig = Field(default_factory=FilterConfig)
    bad_words: FilterConfig = Field(default_factory=FilterConfig)
    duplicate_text: FilterConfig = Field(default_factory=FilterConfig)
    repeated_messages: FilterConfig = Field(default_factory=FilterConfig)
    discord_invites: FilterConfig = Field(default_factory=FilterConfig)
    links: FilterConfig = Field(default_factory=FilterConfig)
    spammed_caps: FilterConfig = Field(default_factory=FilterConfig)
    emoji_spam: FilterConfig = Field(default_factory=FilterConfig)
    mass_mention: FilterConfig = Field(default_factory=FilterConfig)
    ai_moderation: FilterConfig = Field(default_factory=FilterConfig)

class AutoModRule(BaseModel):
    threshold: int
    action: str
    duration: Optional[int] = None

class AutoModSettings(BaseModel):
    guild_id: str
    global_settings: AutoModGlobal = Field(alias="global", default_factory=AutoModGlobal)
    filters: AutoModFilters = Field(default_factory=AutoModFilters)
    automod_rules: List[AutoModRule] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class ModerationSettings(BaseModel):
    is_moderation_settings_enabled: bool = Field(default=True)
    guild_id: int
    mode_roles : List[Dict[str, str]] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class AntiSpamAction(BaseModel):
    violation_count: int
    action: str
    duration: int = 300


class AntiSpamSettings(BaseModel):
    guild_id: int
    enabled: bool = False
    message_rate_limit: int = 5
    message_rate_window: int = 5
    duplicate_threshold: int = 3
    duplicate_window: int = 30
    max_mentions_per_message: int = 5
    max_mentions_per_window: int = 10
    mention_window: int = 15
    max_emojis_per_message: int = 15
    max_newlines: int = 20
    max_stickers_per_window: int = 5
    sticker_window: int = 10
    max_attachments_per_window: int = 5
    attachment_window: int = 10
    actions: List[AntiSpamAction] = Field(default_factory=lambda: [
        AntiSpamAction(violation_count=1, action="delete"),
        AntiSpamAction(violation_count=2, action="delete+warn"),
        AntiSpamAction(violation_count=3, action="timeout", duration=300),
        AntiSpamAction(violation_count=5, action="kick"),
    ])
    ignored_channels: List[str] = Field(default_factory=list)
    ignored_roles: List[str] = Field(default_factory=list)
    whitelisted_users: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class AntiRaidSettings(BaseModel):
    guild_id: int
    enabled: bool = False
    join_rate_limit: int = 10
    join_rate_window: int = 10
    min_account_age_days: int = 7
    account_age_action: str = "kick"
    no_avatar_action: str = "alert"
    raid_mode_action: str = "lockdown"
    raid_lockdown_duration: int = 300
    auto_verify_escalation: bool = True
    dm_on_kick: bool = True
    dm_message: str = "You were kicked due to a raid detection. Please rejoin later."
    log_channel_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


