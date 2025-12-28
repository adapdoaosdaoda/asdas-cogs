# EventChannels - Channel Customization

Customize how event channels are named and formatted.

## Channel Name Format

### Setting the Format

```
[p]eventchannels setchannelformat <format>
```

**Placeholders:**
- `{name}` - Event name (lowercase, spaces replaced)
- `{type}` - Channel type ("text" or "voice")

### Format Examples

**Default:** `{name}᲼{type}`
```
Event: "Weekly Raid Night"
Channels:
- weekly᲼raid᲼night᲼text
- weekly᲼raid᲼night᲼voice
```

**Hyphen separator:** `{name}-{type}`
```
Event: "Weekly Raid Night"
Channels:
- weekly-raid-night-text
- weekly-raid-night-voice
```

**Prefix:** `event-{name}-{type}`
```
Event: "Weekly Raid Night"
Channels:
- event-weekly-raid-night-text
- event-weekly-raid-night-voice
```

## Channel Name Limits

### Numeric Limiting

Limit channel names to a specific number of characters:

```
[p]eventchannels setchannelnamelimit 50
```

Limits the `{name}` portion to 50 characters before adding type.

### Character-Based Limiting

Truncate at a specific character:

```
[p]eventchannels setchannelnamelimit ﹕
```

**How it works:**
- Searches for first occurrence of the character
- Truncates at that character (inclusive)
- Falls back to numeric limit if character not found

**Example:**
```
Event: "Sunday﹒Hero's Realm﹒POST RESET﹕10 man"
Limit: ﹕
Result: "sunday﹒hero's᲼realm﹒post᲼reset﹕᲼text"
```

## Space Replacement

By default, spaces are replaced with `᲼` (special Unicode character).

This is controlled by the `space_replacer` config setting (not directly changeable via commands).

## Renaming Existing Channels

**Important:** The `setchannelformat` command **automatically renames all existing event channels** to match the new format.

```
[p]eventchannels setchannelformat {name}-{type}
```

All active event channels will be renamed immediately.

## Role Name Format

Configure how the bot matches event roles:

```
[p]eventchannels setroleformat <format>
```

**Placeholders:**
- `{name}` - Event name
- `{day_abbrev}` - Day (Mon, Tue, Wed, etc.)
- `{day}` - Day number (1-31)
- `{month_abbrev}` - Month (Jan, Feb, etc.)
- `{time}` - Time (HH:MM)

**Example:**
```
[p]eventchannels setroleformat {name} {day_abbrev} {day}. {month_abbrev} {time}
```

**Result:** `Raid Night Wed 25. Dec 21:00`

## Best Practices

### Keep Names Short

Discord's 100-character limit applies:
- Use short format strings
- Set appropriate character limits
- Consider character-based truncation for consistency

### Use Clear Separators

Choose separators that are easy to read:
- ✅ Hyphen: `raid-night-text`
- ✅ Underscore: `raid_night_text`
- ✅ Unicode: `raid᲼night᲼text`
- ❌ None: `raidnighttext` (hard to read)

### Test Before Going Live

Use `[p]eventchannels stresstest` to test your format with temporary channels.

[← Back to Overview](Overview) | [Home](../Home)
