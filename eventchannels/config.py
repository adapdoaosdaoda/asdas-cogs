"""Configuration defaults for EventChannels cog."""

# Default configuration values
DEFAULT_CONFIG = {
    "event_channels": {},
    "category_id": None,
    "timezone": "UTC",
    "role_format": "{name} {day_abbrev} {day}. {month_abbrev} {time}",
    "channel_format": "{name}᲼{type}",
    "space_replacer": "᲼",
    "creation_minutes": 15,
    "deletion_hours": 4,
    "announcement_message": "{role} The event is starting soon!",
    "event_start_message": "{role} The event is starting now!",
    "deletion_warning_message": "⚠️ These channels will be deleted in 15 minutes.",
    "divider_enabled": True,
    "divider_name": "━━━━━━ EVENT CHANNELS ━━━━━━",
    "divider_channel_id": None,
    "divider_roles": [],
    "channel_name_limit": 100,
    "channel_name_limit_char": "",
    "voice_multipliers": {},
    "voice_minimum_roles": {},
    "minimum_retry_intervals": [10, 5, 2],
    "whitelisted_roles": [],
}

# Configuration identifier for Red Config
CONFIG_IDENTIFIER = 817263540
