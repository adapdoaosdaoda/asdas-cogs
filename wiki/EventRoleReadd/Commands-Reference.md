# EventRoleReadd - Commands Reference

All commands for configuring EventRoleReadd.

## Setup Commands

### setchannel

**Usage:** `[p]rolereadd setchannel <channel>`

Set the channel to monitor for log messages.

**Example:**
```
[p]rolereadd setchannel #event-logs
[p]rolereadd setchannel #raid-helper-logs
```

## Keyword Management

### addkeyword

**Usage:** `[p]rolereadd addkeyword <keyword>`

Add a keyword that triggers role re-adding. Keywords are case-insensitive.

**Example:**
```
[p]rolereadd addkeyword signed up
[p]rolereadd addkeyword Tank
[p]rolereadd addkeyword Support
[p]rolereadd addkeyword Absence
```

### removekeyword

**Usage:** `[p]rolereadd removekeyword <keyword>`

Remove a keyword from the trigger list.

**Example:**
```
[p]rolereadd removekeyword Tank
```

### listkeywords

**Usage:** `[p]rolereadd listkeywords`

List all configured keywords.

**Example:**
```
[p]rolereadd listkeywords
```

**Output:**
```
Configured keywords:
- signed up
- Tank
- Support
- Absence
```

### clearkeywords

**Usage:** `[p]rolereadd clearkeywords`

Clear all keywords (disables the feature).

**Example:**
```
[p]rolereadd clearkeywords
```

## View Configuration

### settings

**Usage:** `[p]rolereadd settings`

View current EventRoleReadd settings.

**Example:**
```
[p]rolereadd settings
```

**Output:**
```
EventRoleReadd Settings:
Log Channel: #event-logs
Keywords: signed up, Tank, Support, Absence
```

## Complete Setup Example

```bash
# Set log channel
[p]rolereadd setchannel #raid-helper-logs

# Add keywords for different scenarios
[p]rolereadd addkeyword signed up
[p]rolereadd addkeyword changed role to
[p]rolereadd addkeyword Tank
[p]rolereadd addkeyword Healer
[p]rolereadd addkeyword DPS

# Verify configuration
[p]rolereadd settings
```

## How It Works

When a message is posted in the log channel:

1. Bot checks if message contains any configured keywords
2. Bot searches for user ID in format `(123456789012345678)`
3. Bot fetches event roles from EventChannels cog
4. Bot re-adds any missing roles to the user

## Troubleshooting

### Roles Not Being Re-added

**Check:**
- Is the log channel set correctly?
- Does the message contain a configured keyword?
- Is the user ID in the correct format `(123456789012345678)`?
- Does EventChannels cog have active event roles?
- Does bot have "Manage Roles" permission?

### Wrong Roles Being Added

The cog only re-adds roles tracked by EventChannels. It doesn't create or add arbitrary roles.

### Bot Not Responding to Messages

**Check:**
- Is the keyword spelled exactly as configured?
- Keywords are case-insensitive but must match
- Bot ignores its own messages to prevent loops

[← Back to Overview](Overview) | [Home](../Home)
