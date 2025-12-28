# EventRoleReadd - Overview

Automatically re-adds event roles to users based on keywords found in log channel messages.

## What Does It Do?

EventRoleReadd monitors a designated Discord channel for log messages and automatically re-adds event roles when it detects specific keywords.

### Key Features

- 🔍 **Monitors Log Channels** - Watches for raid-helper logs or similar
- 🔑 **Keyword-Based Triggers** - Configurable keywords activate role re-adding
- 👥 **Role Integration** - Works with EventChannels cog to identify event roles
- ⚡ **Instant Response** - Re-adds roles immediately upon message detection

## How It Works

### Message Flow

```
1. Raid-helper posts log message:
   "Lhichi (118057027460268035) signed up as :Tank: Tank."

2. Bot detects configured keyword (e.g., "signed up")

3. Bot extracts user ID: 118057027460268035

4. Bot finds all event roles from EventChannels cog

5. Bot re-adds any missing event roles to the user
```

### Expected Log Format

The cog parses messages containing:
- **User ID in parentheses**: `(123456789012345678)`
- **Configured keywords**: "signed up", "Tank", "Absence", etc.

**Example:**
```
Friday﹒Hero's Realm﹕10 man (27 December 2025 17:45)
Lhichi (118057027460268035) signed up as :Tank: Tank.
```

## Use Cases

Perfect for:
- **Raid-Helper Integration** - Re-add roles when users sign up/change roles
- **Event Management** - Automatically maintain role assignments
- **Role Recovery** - Restore roles that were accidentally removed

## Required Permissions

- **Read Messages** - Monitor the log channel
- **Manage Roles** - Re-add roles to users

Note: Unlike audit log approaches, this does NOT require "View Audit Log" permission.

## Integration with EventChannels

Works seamlessly together:
- EventRoleReadd uses EventChannels' stored event data
- Only re-adds roles tracked by EventChannels
- Both cogs can be used independently

## Quick Start

See [Commands Reference](Commands-Reference) for setup instructions.

[← Back to Home](../Home)
