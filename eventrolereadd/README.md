# EventRoleReadd

Automatically re-adds event roles to users based on keywords found in log channel messages.

## How It Works

This cog monitors a designated Discord channel for log messages containing user IDs and configurable keywords. When a match is found, it automatically re-adds event roles to the mentioned user.

### Expected Log Message Format

The cog parses messages in the following format:

```
Friday﹒Hero's Realm﹕10 man (27 December 2025 17:45)
Lhichi (118057027460268035) signed up as :Tank: Tank.
```

The key elements:
- **User ID in parentheses**: `(118057027460268035)` - Must be a valid Discord user ID (17-19 digits)
- **Keywords**: Any configurable text like "signed up", "Tank", "Support", "Absence", etc.

## Setup

1. **Set the log channel**:
   ```
   [p]rolereadd setchannel #event-logs
   ```

2. **Add keywords to trigger role re-adding**:
   ```
   [p]rolereadd addkeyword signed up
   [p]rolereadd addkeyword Tank
   [p]rolereadd addkeyword Support
   [p]rolereadd addkeyword Absence
   ```

3. **View your configuration**:
   ```
   [p]rolereadd settings
   ```

## Commands

### Configuration Commands

- `[p]rolereadd setchannel <channel>` - Set the channel to monitor for log messages
- `[p]rolereadd addkeyword <keyword>` - Add a keyword to trigger role re-adding
- `[p]rolereadd removekeyword <keyword>` - Remove a keyword
- `[p]rolereadd listkeywords` - List all configured keywords
- `[p]rolereadd clearkeywords` - Clear all keywords (disables the feature)
- `[p]rolereadd settings` - View current settings

## Example Workflow

1. A user signs up for an event in raid-helper
2. Raid-helper posts a log message: `Lhichi (118057027460268035) signed up as :Tank: Tank.`
3. The bot detects the keyword "signed up" (if configured)
4. The bot extracts the user ID `118057027460268035`
5. The bot finds all event roles from the EventChannels cog
6. The bot re-adds any missing event roles to the user

## Integration with EventChannels

This cog works seamlessly with the EventChannels cog:
- It uses EventChannels' stored event data to identify which roles are event-related
- It only re-adds roles that are tracked by EventChannels
- Both cogs can be installed and used independently, but they work best together

## Permissions Required

- **Read Messages**: To monitor the log channel
- **Manage Roles**: To re-add roles to users
- **View Audit Log**: Not required (unlike audit log-based approaches)

## Notes

- The cog only processes messages in the configured log channel
- Bot messages are ignored to prevent loops
- User IDs must be in the format `(123456789012345678)` with parentheses
- Keywords are case-insensitive
- Multiple keywords can be configured for different scenarios
