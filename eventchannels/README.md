# EventChannels

A Red-Discord bot cog that automatically creates temporary text and voice channels for Discord scheduled events, with dynamic voice channel scaling and channel name customization.

## Features

- **Automatic Channel Creation**: Creates text and voice channels when Discord scheduled events are about to start
- **Role-Based Access Control**: Assigns event-specific roles for channel access
- **Dynamic Voice Scaling**: Creates multiple voice channels based on role member count
- **Channel Name Customization**: Supports character limits and custom truncation
- **Automatic Cleanup**: Removes channels and roles when events end or are cancelled
- **Divider Channel Support**: Organizes event channels with visual separators
- **Permission Management**: Handles channel permissions and role assignments

## Installation

1. Add this cog to your Red-bot cogs folder
2. Load the cog: `[p]load eventchannels`
3. Configure the cog using the commands below

## Commands

All commands are subcommands of `[p]eventchannels`. You can view all available commands by running `[p]eventchannels` or `[p]help eventchannels`.

### Basic Setup

#### `[p]eventchannels setcategory <category>`
Set the category where event channels will be created.

**Example:**
```
!eventchannels setcategory Events
```

#### `[p]eventchannels setchannelformat <format>`
Set the format for channel names. Use `{name}` for the event name and `{type}` for the channel type (text/voice).

**Default:** `{name}᲼{type}`

**Example:**
```
!eventchannels setchannelformat {name}᲼{type}
!eventchannels setchannelformat {type}᲼{name}
```

#### `[p]eventchannels setdivider <enabled> [name]`
Enable/disable divider channel and optionally set its name.

**Example:**
```
!eventchannels setdivider true ━━━━━━━━━━━━
!eventchannels setdivider false
```

### Channel Name Limiting

#### `[p]eventchannels setchannelnamelimit <limit>`
Set the maximum character limit for channel names. Accepts either a number (1-100) or a character/string to truncate at.

**Numeric Limit:**
```
!eventchannels setchannelnamelimit 50
```
This limits the event name to 50 characters before adding type identifiers.

**Character-Based Limit:**
```
!eventchannels setchannelnamelimit ﹕
```
This truncates the event name at the first occurrence of "﹕" (inclusive), keeping everything up to and including that character.

**How It Works:**
- The limit applies **only** to the `{name}` portion from the event, not the entire channel name
- Type identifiers like "text" and "voice" are added after the limit is applied
- If the specified character isn't found, falls back to the numeric limit (default: 100)

**Examples:**

Event: `Sunday﹒Hero's Realm﹒POST RESET﹕10 man`
- Limit: `﹕` → Channel becomes: `Sunday﹒Hero's Realm﹒POST RESET﹕᲼text`
- Limit: `30` → Channel becomes: `Sunday﹒Hero's Realm﹒POST RE᲼text`

### Voice Channel Multiplier

#### `[p]eventchannels setvoicemultiplier <keyword> <multiplier>`
Enable dynamic voice channel creation based on role member count.

**Parameters:**
- `keyword`: Trigger word in the event name (case-insensitive)
- `multiplier`: Max capacity minus 1 per voice channel (1-99)

**Formula:**
- Number of channels = `floor(role_members / multiplier)`, minimum 1
- User limit per channel = `multiplier + 1`

**Example:**
```
!eventchannels setvoicemultiplier hero 9
```

**How It Works:**
1. Event name contains "hero" (case-insensitive)
2. Event role has 25 members
3. Calculation: `25 / 9 = 2.77` → 2 channels created
4. Each channel has user limit of 10 (9 + 1)
5. Channels named: `voice 1`, `voice 2`

**Channel Naming:**
- 1 channel: `voice` (no number)
- 2+ channels: `voice 1`, `voice 2`, etc.

#### `[p]eventchannels disablevoicemultiplier`
Disable the voice channel multiplier feature.

**Example:**
```
!eventchannels disablevoicemultiplier
```

#### `[p]eventchannels listvoicemultipliers`
List all configured voice multipliers.

**Example:**
```
!eventchannels listvoicemultipliers
```

#### `[p]eventchannels removevoicemultiplier <keyword>`
Remove a specific voice multiplier keyword.

**Example:**
```
!eventchannels removevoicemultiplier hero
```

### Event Management

#### `[p]eventchannels viewsettings`
View all current event channel settings.

**Example:**
```
!eventchannels viewsettings
```

#### `[p]eventchannels testchannellock`
Test the channel locking mechanism to verify bot permissions.

**Example:**
```
!eventchannels testchannellock
```

#### `[p]eventchannels testeventroles [role]`
Test command to see how many users have a given role for current events.

**Usage:**
- Without arguments: Shows member counts for all active event roles
- With role: Shows member count for a specific role if it's associated with an event

**Examples:**
```
!eventchannels testeventroles
!eventchannels testeventroles @Event Role
```

**What It Shows:**
- Number of members with each event role
- Associated event names
- Warning if member counts may be incomplete (missing GUILD_MEMBERS intent)

#### `[p]eventchannels stresstest`
Comprehensive stress test of all EventChannels features.

**Example:**
```
!eventchannels stresstest
```

## Configuration Examples

### Example 1: Basic Setup
```
!eventchannels setcategory Events
!eventchannels setchannelformat {name}᲼{type}
!eventchannels setchannelnamelimit 50
```

**Event:** `Weekly Raid Night`
**Channels Created:**
- `Weekly Raid Night᲼text`
- `Weekly Raid Night᲼voice`

### Example 2: Character-Based Limiting
```
!eventchannels setchannelnamelimit ﹕
```

**Event:** `Sunday﹒Hero's Realm﹒POST RESET﹕10 man`
**Channels Created:**
- `Sunday﹒Hero's Realm﹒POST RESET﹕᲼text`
- `Sunday﹒Hero's Realm﹒POST RESET﹕᲼voice`

### Example 3: Voice Multiplier (Small Group)
```
!eventchannels setvoicemultiplier raid 9
```

**Event:** `Weekly Raid Night` (role has 8 members)
**Calculation:** `8 / 9 = 0.88` → 1 channel
**Channels Created:**
- `Weekly Raid Night᲼text`
- `Weekly Raid Night᲼voice` (limit: 10 users)

### Example 4: Voice Multiplier (Medium Group)
```
!eventchannels setvoicemultiplier raid 9
```

**Event:** `Weekly Raid Night` (role has 25 members)
**Calculation:** `25 / 9 = 2.77` → 2 channels
**Channels Created:**
- `Weekly Raid Night᲼text`
- `Weekly Raid Night᲼voice 1` (limit: 10 users)
- `Weekly Raid Night᲼voice 2` (limit: 10 users)

### Example 5: Voice Multiplier (Large Group)
```
!eventchannels setvoicemultiplier pvp 4
```

**Event:** `PvP Tournament` (role has 23 members)
**Calculation:** `23 / 4 = 5.75` → 5 channels
**Channels Created:**
- `PvP Tournament᲼text`
- `PvP Tournament᲼voice 1` (limit: 5 users)
- `PvP Tournament᲼voice 2` (limit: 5 users)
- `PvP Tournament᲼voice 3` (limit: 5 users)
- `PvP Tournament᲼voice 4` (limit: 5 users)
- `PvP Tournament᲼voice 5` (limit: 5 users)

### Example 6: Combined Features
```
!eventchannels setchannelnamelimit ﹕
!eventchannels setvoicemultiplier hero 9
```

**Event:** `Sunday﹒Hero's Realm﹒POST RESET﹕10 man` (role has 40 members)
**Calculation:** `40 / 9 = 4.44` → 4 channels
**Channels Created:**
- `Sunday﹒Hero's Realm﹒POST RESET﹕᲼text`
- `Sunday﹒Hero's Realm﹒POST RESET﹕᲼voice 1` (limit: 10 users)
- `Sunday﹒Hero's Realm﹒POST RESET﹕᲼voice 2` (limit: 10 users)
- `Sunday﹒Hero's Realm﹒POST RESET﹕᲼voice 3` (limit: 10 users)
- `Sunday﹒Hero's Realm﹒POST RESET﹕᲼voice 4` (limit: 10 users)

## How It Works

### Event Lifecycle

1. **Event Created**: Bot detects a new Discord scheduled event
2. **Pre-Event Task**: Schedules channel creation for 5 minutes before event start
3. **Channel Creation**: Creates text channel, voice channel(s), and role
4. **Role Assignment**: Assigns event role to interested/attending members
5. **Event Start**: Channels are active and accessible
6. **Event End**: Schedules cleanup task
7. **Cleanup**: Deletes channels and roles after event ends

### Voice Multiplier Logic

When an event name contains the configured keyword:
1. Counts members in the event role
2. Calculates: `max(1, floor(members / multiplier))`
3. Creates that many voice channels
4. Sets user limit to `multiplier + 1` on each channel
5. Numbers channels if count > 1

### Character Limit Logic

When processing event names:
1. If character-based limit is set, searches for first occurrence
2. Truncates at that character (inclusive) if found
3. Falls back to numeric limit if character not found
4. Applies limit before adding type identifiers

## Troubleshooting

### Channels Not Being Created

- Verify bot has permissions to create channels and roles
- Check that event category is set: `[p]eventchannels viewsettings`
- Ensure event is scheduled (not in the past)
- Check bot has permission to view scheduled events

### Voice Multiplier Not Working

- Event name must contain the configured keyword (case-insensitive)
- Check configuration: `[p]eventchannels viewsettings`
- Verify event role has members assigned
- Multiplier must be between 1-99

### Channel Name Too Long

- Discord limits channel names to 100 characters
- Use `[p]eventchannels setchannelnamelimit` to reduce length
- Consider using shorter channel format
- Use character-based limiting for consistent truncation

### Permissions Issues

- Bot needs these permissions in the event category:
  - Manage Channels
  - Manage Roles
  - View Channels
  - Send Messages
  - Connect to Voice

## Technical Details

### Storage Format

Event data is stored per-guild with the following structure:
```python
{
  "event_id": {
    "text": text_channel_id,
    "voice": [voice_channel_id_1, voice_channel_id_2, ...],
    "role": role_id
  }
}
```

### Backward Compatibility

The cog supports both old storage format (single voice channel ID) and new format (list of voice channel IDs) for seamless upgrades.

### Event Listeners

- `on_scheduled_event_delete`: Cleans up channels when events are cancelled
- `on_guild_channel_delete`: Updates storage when channels are manually deleted
- `on_guild_role_delete`: Updates storage when roles are manually deleted

## Support

For issues, feature requests, or questions, please open an issue on the repository.

## Credits

Developed for Red-Discord Bot framework.
