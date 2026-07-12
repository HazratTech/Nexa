from datetime import datetime
from typing import Optional, List
from pydantic import Field
from core.models.base_model import MongoBase

class AntiSpamLog(MongoBase):
    """Logged every time anti-spam takes action on a user."""
    guild_id: int = Field(..., description="Guild ID")
    user_id: int = Field(..., description="User ID")
    violation_type: str = Field(..., description="Type of violation (e.g. rate_limit, duplicate, etc)")
    action_taken: str = Field(..., description="Action taken (e.g. delete, timeout, kick, ban)")
    message_content: Optional[str] = Field(None, description="Spam message content (truncated)")
    channel_id: int = Field(..., description="Channel ID where spam occurred")
    violation_score: int = Field(0, description="Violation score at time of action")

class AntiRaidIncident(MongoBase):
    """Logged when a raid is detected and actions are taken."""
    guild_id: int = Field(..., description="Guild ID")
    raid_level: int = Field(..., description="Raid level triggered (1=ALERT, 2=LOCKDOWN, 3=PANIC)")
    trigger_type: str = Field(..., description="Raid trigger type (e.g. join_flood, account_age)")
    join_count: int = Field(..., description="Number of joins that triggered this incident")
    window_seconds: int = Field(..., description="Time window in seconds")
    accounts_actioned: List[int] = Field(default_factory=list, description="List of user IDs actioned during the raid")
    actions_taken: List[str] = Field(default_factory=list, description="Summary of actions taken")
    auto_resolved: bool = Field(default=False, description="Whether the raid mode auto-resolved/de-escalated")
    resolved_at: Optional[datetime] = Field(None, description="When the incident was resolved")
