# EventChannels - Technical Details

Technical information for developers and advanced users.

## Storage Format

Event data is stored per-guild using Red's Config API.

### Event Channels Storage

```python
{
  "event_id_string": {
    "text": text_channel_id,
    "voice": [voice_channel_id_1, voice_channel_id_2, ...],  # List format (new)
    "role": role_id
  }
}
```

### Legacy Format Support

The cog supports the old storage format for backward compatibility:

```python
{
  "event_id_string": {
    "text": text_channel_id,
    "voice": voice_channel_id,  # Single ID (old format)
    "role": role_id
  }
}
```

## Configuration Schema

```python
{
    "category_id": int,
    "timezone": str,
    "creation_minutes": int,
    "deletion_hours": int,
    "role_format": str,
    "channel_format": str,
    "space_replacer": str,
    "announcement_message": str,
    "event_start_message": str,
    "deletion_warning_message": str,
    "divider_enabled": bool,
    "divider_name": str,
    "divider_channel_id": int,
    "divider_roles": list[int],
    "channel_name_limit": int,
    "channel_name_limit_char": str,
    "voice_multipliers": dict[str, int],
    "voice_minimum_roles": dict[str, int],
    "minimum_retry_intervals": list[int]
}
```

## Event Listeners

### on_scheduled_event_create

- Triggered when a Discord scheduled event is created
- Schedules `_handle_event` task
- Stores task in `self.active_tasks`

### on_scheduled_event_delete

- Cancels pending channel creation tasks
- Cleans up stored event data

### on_scheduled_event_update

- Detects event cancellations
- Handles event time changes (reschedules tasks)

### on_guild_channel_delete

- Updates storage when event channels are manually deleted
- Prevents orphaned data

### on_guild_role_delete

- Cleans up event channels when role is deleted
- Updates storage and cancels tasks

## Task Management

### Active Tasks Dictionary

```python
self.active_tasks = {
    event_id: main_task,
    f"{event_id}_retry_1": retry_task_1,
    f"{event_id}_retry_2": retry_task_2,
    f"{event_id}_retry_3": retry_task_3
}
```

### Task Cancellation

The `_cancel_event_tasks(event_id)` helper cancels:
- Main event task
- All associated retry tasks

## Retry Mechanism

### Retry Flow

```python
async def _handle_event(guild, event, retry_count=0):
    # Wait until creation time (adjusted for retry)
    # Check if channels already exist (prevent duplicates)
    # Check minimum roles requirement
    # If not met and retries available: schedule next retry
    # If met: create channels
```

### Retry Intervals

Default: `[10, 5, 2]` minutes before event start

Configurable via `minimum_retry_intervals` config setting.

## Permission Handling

### Channel Permissions

Overwrites applied to event channels:

```python
overwrites = {
    guild.default_role: discord.PermissionOverwrite(read_messages=False),
    event_role: discord.PermissionOverwrite(read_messages=True),
    bot_member: discord.PermissionOverwrite(
        read_messages=True,
        manage_channels=True,
        manage_permissions=True
    )
}
```

### Divider Permissions

Divider channel permissions are dynamically managed:
- Invisible to `@everyone`
- Visible only to members with active event roles
- Updated as events are created/deleted

## Performance Considerations

### Task Limits

No hard limit on concurrent event tasks, but consider:
- Each event creates 1 main task + up to 3 retry tasks
- 100 simultaneous events = ~400 tasks

### Storage Size

Event data is cleaned up after event deletion, keeping storage minimal.

### API Rate Limits

Channel creation respects Discord rate limits:
- Maximum ~50 channels created per event (text + 49 voice)
- Batch permission updates to minimize API calls

## Debugging

### Enable Debug Logging

```python
import logging
logging.getLogger("red.eventchannels").setLevel(logging.DEBUG)
```

### Check Active Tasks

```python
# In bot console
len(bot.get_cog("EventChannels").active_tasks)
```

[← Back to Overview](Overview) | [Home](../Home)
