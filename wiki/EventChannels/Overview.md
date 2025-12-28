# EventChannels - Overview

EventChannels is a powerful cog that automatically creates temporary text and voice channels for Discord scheduled events, with dynamic voice channel scaling, channel name customization, and automatic cleanup.

## What Does It Do?

EventChannels automat automatically creates text and voice channels **15 minutes before** (configurable) a Discord event starts, or immediately if within that timeframe. The cog was designed to complement [Raid-Helper](https://raid-helper.dev/) (premium), which allows automatic event + role creation but not automatic channel creation.

### Key Features

- ✅ **Automatic Channel Creation** - Creates channels when events are about to start
- 👥 **Role-Based Access Control** - Event-specific roles control who can see channels
- 🔊 **Dynamic Voice Scaling** - Creates multiple voice channels based on attendance
- 👤 **Minimum Roles Enforcement** - Prevent channel creation if attendance is too low
- 🔄 **Retry Mechanism** - Rechecks attendance before event if minimum not initially met
- 🎨 **Channel Name Customization** - Supports character limits and custom truncation
- 🗑️ **Automatic Cleanup** - Removes channels/roles after events end
- 📌 **Divider Channel Support** - Organizes event channels visually
- ⚙️ **Configurable Timings** - Customize creation and deletion times
- 💬 **Custom Messages** - Configure announcements and warnings

## How It Works

### Event Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Event Created          │ Bot detects Discord scheduled event │
├─────────────────────────────────────────────────────────────────┤
│ 2. Pre-Event Task         │ Schedules creation T-15 min         │
├─────────────────────────────────────────────────────────────────┤
│ 3. Minimum Check          │ Verifies role has enough members    │
├─────────────────────────────────────────────────────────────────┤
│ 4. Retry (if needed)      │ Rechecks at T-10, T-5, T-2 min      │
├─────────────────────────────────────────────────────────────────┤
│ 5. Channel Creation       │ Creates text + voice channels       │
├─────────────────────────────────────────────────────────────────┤
│ 6. Announcement           │ Posts message in text channel       │
├─────────────────────────────────────────────────────────────────┤
│ 7. Event Start            │ Posts start message                 │
├─────────────────────────────────────────────────────────────────┤
│ 8. Deletion Warning       │ Warns 15 min before cleanup         │
├─────────────────────────────────────────────────────────────────┤
│ 9. Cleanup                │ Deletes channels/roles (T+4 hours) │
└─────────────────────────────────────────────────────────────────┘
```

## Use Cases

### Perfect For:

- **Raid Events** - Automatically create channels for World of Warcraft raids
- **PvP Tournaments** - Scale voice channels based on participants
- **Scheduled Activities** - Any recurring events that need temporary channels
- **Community Events** - Game nights, watch parties, study sessions
- **Guild Operations** - Leadership meetings, planning sessions

### Integrations:

- Works seamlessly with **Raid-Helper** (automatic role creation)
- Compatible with **EventRoleReadd** cog (automatic role management)
- Supports any Discord scheduled event system

## Required Permissions

### Server-Level Permissions

The bot needs these permissions at the server level:

- **Manage Channels** - Create and delete text/voice channels
- **Manage Roles** - Delete event roles after cleanup
- **View Channels** - Access and manage the category

### Category Permissions

If using a specific category for event channels:

- **Manage Channels** - Create channels within the category
- **Manage Permissions** - Set channel permission overwrites

## What's Next?

- [🚀 Getting Started](Getting-Started) - Set up your first event channels
- [⚙️ Commands Reference](Commands-Reference) - Complete list of all commands
- [🔊 Voice Multipliers](Voice-Multipliers) - Scale channels based on attendance
- [👥 Minimum Roles Enforcement](Minimum-Roles-Enforcement) - Prevent low-attendance events
- [💡 Configuration Examples](Configuration-Examples) - See real-world setups

[← Back to Home](../Home)
